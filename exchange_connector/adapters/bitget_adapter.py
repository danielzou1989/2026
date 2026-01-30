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

from exchange_connector.core.rate_limiter import AdaptiveRateLimiter


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
            API响应数据
        """
        # 限频控制
        self.rate_limiter.acquire(rate_limit_key)

        url = self.base_url + endpoint
        timestamp = str(int(time.time() * 1000))

        body = json.dumps(data) if data else ''
        signature = self._sign_request(timestamp, method, endpoint, body)

        headers = {
            'ACCESS-KEY': self.api_key,
            'ACCESS-SIGN': signature,
            'ACCESS-TIMESTAMP': timestamp,
            'ACCESS-PASSPHRASE': self.passphrase,
            'Content-Type': 'application/json'
        }

        for attempt in range(retry_count):
            try:
                if method == 'GET':
                    response = requests.get(url, params=params, headers=headers)
                elif method == 'POST':
                    response = requests.post(url, json=data, headers=headers)
                elif method == 'DELETE':
                    response = requests.delete(url, params=params, headers=headers)
                else:
                    raise ValueError(f"Unsupported method: {method}")

                # 处理限频错误
                if response.status_code == 429:
                    self.rate_limiter.report_error(rate_limit_key, 429)
                    time.sleep(1)
                    continue

                # 处理其他错误
                if response.status_code != 200:
                    self.rate_limiter.report_error(rate_limit_key)
                    raise Exception(f"API error: {response.text}")

                # 成功响应
                self.rate_limiter.report_success(rate_limit_key)
                return response.json()

            except Exception as e:
                if attempt == retry_count - 1:
                    raise e
                time.sleep(0.5 * (attempt + 1))  # 递增等待

        return {}

    def get_balance(self) -> Dict:
        """查询账户余额"""
        return self._request('GET', '/api/v2/mix/account/accounts')

    def get_positions(self) -> Dict:
        """查询持仓信息"""
        return self._request('GET', '/api/v2/mix/position/all-position')

    def get_ticker(self, symbol: str) -> Dict:
        """
        获取行情信息

        Args:
            symbol: 交易对，如BTCUSDT
        """
        return self._request('GET', '/api/v2/mix/market/ticker', params={'symbol': symbol})

    def place_order(self, symbol: str, side: str, order_type: str, size: float,
                    price: Optional[float] = None, client_oid: Optional[str] = None) -> Dict:
        """
        下单

        Args:
            symbol: 交易对
            side: 买卖方向 buy/sell
            order_type: 订单类型 limit/market
            size: 数量
            price: 价格（限价单必填）
            client_oid: 客户自定义订单ID
        """
        data = {
            'symbol': symbol,
            'side': side,
            'orderType': order_type,
            'size': str(size)
        }
        if price:
            data['price'] = str(price)
        if client_oid:
            data['clientOid'] = client_oid

        return self._request('POST', '/api/v2/mix/order/place-order',
                             data=data, rate_limit_key='place_order')

    def place_batch_orders(self, orders: List[Dict]) -> Dict:
        """批量下单"""
        return self._request('POST', '/api/v2/mix/order/batch-orders',
                             data={'orders': orders}, rate_limit_key='batch_order')

    def cancel_order(self, symbol: str, order_id: str) -> Dict:
        """撤单"""
        return self._request('POST', '/api/v2/mix/order/cancel-order',
                             data={'symbol': symbol, 'orderId': order_id},
                             rate_limit_key='cancel_order')

    def cancel_all_orders(self, symbol: str) -> Dict:
        """撤销某交易对所有订单"""
        return self._request('POST', '/api/v2/mix/order/cancel-all-order',
                             data={'symbol': symbol}, rate_limit_key='cancel_order')

    def get_order_detail(self, symbol: str, order_id: str) -> Dict:
        """查询订单详情"""
        return self._request('GET', '/api/v2/mix/order/detail',
                             params={'symbol': symbol, 'orderId': order_id})

    def get_open_orders(self, symbol: Optional[str] = None) -> Dict:
        """查询当前挂单"""
        params = {'symbol': symbol} if symbol else {}
        return self._request('GET', '/api/v2/mix/order/orders-pending', params=params)

