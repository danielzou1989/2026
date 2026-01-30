"""
Bitget 交易所适配器实现
实现统一的交易接口，支持限频控制、错误重试、批量操作
"""

import hashlib
import hmac
import time
import requests
import json
from typing import Dict, List, Optional, Tuple
from decimal import Decimal
import sys
import os

# 添加父目录到路径以导入 rate_limiter
sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
from core.rate_limiter import AdaptiveRateLimiter


class BitgetAdapter:
    """Bitget交易所适配器"""

    def __init__(self, api_key: str, api_secret: str, passphrase: str, base_url: str = "https://api.bitget.com"):
        """
        初始化Bitget适配器

        Args:
            api_key: API密钥
            api_secret: API密钥
            passphrase: API密码短语
            base_url: API基础URL
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.base_url = base_url

        # 初始化限频控制器
        self.rate_limiter = AdaptiveRateLimiter({
            'place_order': {'limit': 10, 'window': 1},
            'batch_order': {'limit': 5, 'window': 1},
            'query': {'limit': 20, 'window': 1},
            'cancel_order': {'limit': 10, 'window': 1}
        })

    def _sign_request(self, timestamp: str, method: str, request_path: str, body: str = '') -> str:
        """
        生成签名

        Args:
            timestamp: 时间戳
            method: HTTP方法
            request_path: 请求路径
            body: 请求体

        Returns:
            签名字符串
        """
        message = timestamp + method + request_path + body
        mac = hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        )
        return mac.hexdigest()

    def _request(self, method: str, endpoint: str, params: Optional[Dict] = None,
                 data: Optional[Dict] = None, rate_limit_key: str = 'query',
                 retry_count: int = 3) -> Dict:
        """
        发送HTTP请求，带限频控制和重试机制

        Args:
            method: HTTP方法
            endpoint: API端点
            params: URL参数
            data: 请求体数据
            rate_limit_key: 限频规则键
            retry_count: 重试次数

        Returns:
            API响应
        """
        # 限频检查
        self.rate_limiter.acquire(rate_limit_key)

        timestamp = str(int(time.time() * 1000))
        request_path = endpoint

        if params:
            query_string = '&'.join([f"{k}={v}" for k, v in params.items()])
            request_path += '?' + query_string

        body = json.dumps(data) if data else ''
        signature = self._sign_request(timestamp, method, request_path, body)

        headers = {
            'ACCESS-KEY': self.api_key,
            'ACCESS-SIGN': signature,
            'ACCESS-TIMESTAMP': timestamp,
            'ACCESS-PASSPHRASE': self.passphrase,
            'Content-Type': 'application/json',
            'locale': 'en-US'
        }

        url = self.base_url + endpoint

        for attempt in range(retry_count):
            try:
                response = requests.request(
                    method, url,
                    headers=headers,
                    params=params,
                    json=data,
                    timeout=10
                )

                # 检查HTTP状态码
                if response.status_code == 429:
                    # 限频错误，报告给自适应限频控制器
                    self.rate_limiter.report_error(rate_limit_key, 429)
                    wait_time = (2 ** attempt) * 0.5  # 指数退避
                    time.sleep(wait_time)
                    continue

                response.raise_for_status()
                result = response.json()

                # Bitget API 返回格式: {"code": "00000", "msg": "success", "data": {...}}
                if result.get('code') == '00000':
                    self.rate_limiter.report_success(rate_limit_key)
                    return {'ok': True, 'data': result.get('data'), 'error': None}
                else:
                    # API业务错误
                    error_msg = result.get('msg', 'Unknown error')
                    error_code = result.get('code', '')
                    return {
                        'ok': False,
                        'data': None,
                        'error': {
                            'code': error_code,
                            'message': error_msg,
                            'retryable': self._is_retryable_error(error_code)
                        }
                    }

            except requests.exceptions.Timeout:
                if attempt < retry_count - 1:
                    wait_time = (2 ** attempt) * 0.5
                    time.sleep(wait_time)
                    continue
                return {'ok': False, 'data': None, 'error': {'message': 'Request timeout', 'retryable': True}}

            except requests.exceptions.RequestException as e:
                if attempt < retry_count - 1:
                    wait_time = (2 ** attempt) * 0.5
                    time.sleep(wait_time)
                    continue
                return {'ok': False, 'data': None, 'error': {'message': str(e), 'retryable': False}}

        return {'ok': False, 'data': None, 'error': {'message': 'Max retries exceeded', 'retryable': False}}

    def _is_retryable_error(self, error_code: str) -> bool:
        """判断错误是否可重试"""
        # Bitget错误码：40306是批量订单超过50条，可以分批重试
        retryable_codes = ['40306', '40001']  # 可重试的错误码
        return error_code in retryable_codes

    # ========== 核心接口实现 ==========

    def get_account_info(self, product_type: str = 'USDT-FUTURES') -> Dict:
        """
        获取账户信息

        Args:
            product_type: 产品类型

        Returns:
            标准化的账户信息
        """
        endpoint = '/api/v2/mix/account/accounts'
        params = {'productType': product_type}

        result = self._request('GET', endpoint, params=params, rate_limit_key='query')

        if result['ok']:
            accounts = result['data']
            if not accounts:
                return {'ok': True, 'data': {}, 'error': None}

            account = accounts[0]  # 取第一个账户
            return {
                'ok': True,
                'data': {
                    'asset': 'USDT',
                    'total': float(account.get('equity', 0)),
                    'available': float(account.get('available', 0)),
                    'used': float(account.get('locked', 0)),
                    'unrealized_pnl': float(account.get('unrealizedPL', 0)),
                    'risk_rate': None  # Bitget需要单独计算
                },
                'error': None
            }

        return result

    def get_positions(self, product_type: str = 'USDT-FUTURES', symbol: Optional[str] = None) -> Dict:
        """
        获取持仓信息

        Args:
            product_type: 产品类型
            symbol: 交易对符号，None表示获取所有

        Returns:
            标准化的持仓列表
        """
        endpoint = '/api/v2/mix/position/all-position'
        params = {'productType': product_type}
        if symbol:
            params['symbol'] = symbol

        result = self._request('GET', endpoint, params=params, rate_limit_key='query')

        if result['ok']:
            positions = result['data']
            standardized_positions = []

            for pos in positions:
                # 只返回有持仓的
                if float(pos.get('total', 0)) > 0:
                    side = 'buy' if pos.get('holdSide', '').lower() == 'long' else 'sell'
                    entry_price = float(pos.get('averageOpenPrice', 0))
                    mark_price = float(pos.get('markPrice', 0))
                    qty = float(pos.get('total', 0))

                    standardized_positions.append({
                        'symbol': pos.get('symbol'),
                        'side': side,
                        'qty': qty,
                        'entry_price': entry_price,
                        'mark_price': mark_price,
                        'upl': float(pos.get('unrealizedPL', 0)),
                        'upl_pct': (mark_price - entry_price) / entry_price if entry_price > 0 else 0,
                        'leverage': float(pos.get('leverage', 1)),
                        'margin_mode': pos.get('marginMode', 'crossed')
                    })

            return {'ok': True, 'data': standardized_positions, 'error': None}

        return result

    def place_order(self, symbol: str, side: str, order_type: str, qty: float,
                    price: Optional[float] = None, reduce_only: bool = False,
                    leverage: Optional[int] = None, post_only: bool = False) -> Dict:
        """
        下单

        Args:
            symbol: 交易对符号
            side: buy/sell
            order_type: market/limit
            qty: 数量
            price: 价格（限价单必填）
            reduce_only: 只减仓
            leverage: 杠杆倍数
            post_only: 只做maker

        Returns:
            订单信息
        """
        endpoint = '/api/v2/mix/order/place-order'

        data = {
            'symbol': symbol,
            'productType': 'USDT-FUTURES',
            'marginMode': 'crossed',
            'marginCoin': 'USDT',
            'side': side,
            'orderType': order_type,
            'size': str(qty)
        }

        if price:
            data['price'] = str(price)

        if reduce_only:
            data['reduceOnly'] = 'YES'

        if post_only:
            data['force'] = 'post_only'

        result = self._request('POST', endpoint, data=data, rate_limit_key='place_order')

        if result['ok']:
            order_data = result['data']
            return {
                'ok': True,
                'data': {
                    'order_id': order_data.get('orderId'),
                    'client_order_id': order_data.get('clientOid'),
                    'symbol': symbol,
                    'side': side,
                    'type': order_type,
                    'qty': qty,
                    'price': price,
                    'status': 'open',
                    'filled_qty': 0
                },
                'error': None
            }

        return result

    def cancel_order(self, symbol: str, order_id: str) -> Dict:
        """
        撤单

        Args:
            symbol: 交易对符号
            order_id: 订单ID

        Returns:
            撤单结果
        """
        endpoint = '/api/v2/mix/order/cancel-order'
        data = {
            'symbol': symbol,
            'productType': 'USDT-FUTURES',
            'marginCoin': 'USDT',
            'orderId': order_id
        }

        return self._request('POST', endpoint, data=data, rate_limit_key='cancel_order')

    def get_open_orders(self, symbol: Optional[str] = None) -> Dict:
        """
        查询开放订单

        Args:
            symbol: 交易对符号，None表示查询所有

        Returns:
            开放订单列表
        """
        endpoint = '/api/v2/mix/order/orders-pending'
        params = {'productType': 'USDT-FUTURES'}
        if symbol:
            params['symbol'] = symbol

        return self._request('GET', endpoint, params=params, rate_limit_key='query')

    def get_fills(self, symbol: Optional[str] = None, since: Optional[int] = None) -> Dict:
        """
        查询成交历史

        Args:
            symbol: 交易对符号
            since: 起始时间戳（毫秒）

        Returns:
            成交历史
        """
        endpoint = '/api/v2/mix/order/fills'
        params = {'productType': 'USDT-FUTURES'}
        if symbol:
            params['symbol'] = symbol
        if since:
            params['startTime'] = since

        return self._request('GET', endpoint, params=params, rate_limit_key='query')

    def place_batch_orders(self, orders: List[Dict]) -> Dict:
        """
        批量下单（最多20笔）

        Args:
            orders: 订单列表

        Returns:
            批量下单结果
        """
        if len(orders) > 20:
            return {
                'ok': False,
                'data': None,
                'error': {'message': 'Batch orders limit is 20', 'retryable': False}
            }

        endpoint = '/api/v2/mix/order/batch-place-order'

        order_list = []
        for order in orders:
            order_data = {
                'symbol': order['symbol'],
                'productType': 'USDT-FUTURES',
                'marginMode': 'crossed',
                'marginCoin': 'USDT',
                'side': order['side'],
                'orderType': order.get('type', 'limit'),
                'size': str(order['qty'])
            }

            if 'price' in order:
                order_data['price'] = str(order['price'])

            if order.get('post_only'):
                order_data['force'] = 'post_only'

            order_list.append(order_data)

        data = {'orderDataList': order_list}

        return self._request('POST', endpoint, data=data, rate_limit_key='batch_order')
