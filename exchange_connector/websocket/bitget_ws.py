"""
Bitget WebSocket 实时数据流
订阅K线数据、深度数据、订单更新等实时推送
支持自动重连、心跳保持、多通道订阅
"""

import json
import time
import hmac
import hashlib
import threading
from typing import Callable, Dict, List, Optional
from websocket import WebSocketApp
import logging

logger = logging.getLogger(__name__)


class BitgetWebSocket:
    """Bitget WebSocket客户端"""

    def __init__(self,
                 api_key: Optional[str] = None,
                 api_secret: Optional[str] = None,
                 passphrase: Optional[str] = None,
                 is_private: bool = False,
                 ws_url: str = "wss://ws.bitget.com/v2/ws/public"):
        """
        初始化WebSocket客户端

        Args:
            api_key: API密钥（私有频道需要）
            api_secret: API密钥（私有频道需要）
            passphrase: API密码短语（私有频道需要）
            is_private: 是否为私有频道
            ws_url: WebSocket URL
        """
        self.api_key = api_key
        self.api_secret = api_secret
        self.passphrase = passphrase
        self.is_private = is_private

        if is_private:
            self.ws_url = "wss://ws.bitget.com/v2/ws/private"
        else:
            self.ws_url = ws_url

        self.ws: Optional[WebSocketApp] = None
        self.ws_thread: Optional[threading.Thread] = None
        self.is_connected = False
        self.should_reconnect = True

        # 订阅管理
        self.subscriptions: List[Dict] = []
        self.callbacks: Dict[str, Callable] = {}

        # 心跳
        self.heartbeat_interval = 30
        self.last_heartbeat = 0

    def _generate_signature(self, timestamp: str, method: str = 'GET', request_path: str = '/user/verify') -> str:
        """
        生成签名（私有频道需要）

        Args:
            timestamp: 时间戳
            method: HTTP方法
            request_path: 请求路径

        Returns:
            签名字符串
        """
        message = timestamp + method + request_path
        mac = hmac.new(
            self.api_secret.encode('utf-8'),
            message.encode('utf-8'),
            hashlib.sha256
        )
        return mac.hexdigest()

    def _on_open(self, ws):
        """WebSocket连接建立回调"""
        logger.info("WebSocket connected")
        self.is_connected = True

        # 私有频道需要登录
        if self.is_private:
            self._login()

        # 重新订阅所有通道
        for sub in self.subscriptions:
            self._send_subscribe(sub)

    def _on_message(self, ws, message):
        """接收消息回调"""
        try:
            data = json.loads(message)

            # 处理pong响应
            if data.get('event') == 'pong':
                self.last_heartbeat = time.time()
                return

            # 处理登录响应
            if data.get('event') == 'login':
                if data.get('code') == '00000':
                    logger.info("WebSocket login successful")
                else:
                    logger.error(f"WebSocket login failed: {data}")
                return

            # 处理订阅响应
            if data.get('event') == 'subscribe':
                if data.get('code') == '00000':
                    logger.info(f"Subscribed to {data.get('arg', {}).get('channel')}")
                else:
                    logger.error(f"Subscribe failed: {data}")
                return

            # 处理数据推送
            if 'data' in data:
                channel = data.get('arg', {}).get('channel', '')
                inst_id = data.get('arg', {}).get('instId', '')

                # 构建回调键
                callback_key = f"{channel}:{inst_id}" if inst_id else channel

                if callback_key in self.callbacks:
                    self.callbacks[callback_key](data['data'])
                elif channel in self.callbacks:
                    self.callbacks[channel](data['data'])

        except Exception as e:
            logger.error(f"Error processing message: {e}")
            logger.debug(f"Message: {message}")

    def _on_error(self, ws, error):
        """错误回调"""
        logger.error(f"WebSocket error: {error}")

    def _on_close(self, ws, close_status_code, close_msg):
        """连接关闭回调"""
        logger.warning(f"WebSocket closed: {close_status_code} - {close_msg}")
        self.is_connected = False

        # 自动重连
        if self.should_reconnect:
            logger.info("Reconnecting in 5 seconds...")
            time.sleep(5)
            self.connect()

    def _login(self):
        """私有频道登录"""
        timestamp = str(int(time.time()))
        signature = self._generate_signature(timestamp)

        login_msg = {
            "op": "login",
            "args": [{
                "apiKey": self.api_key,
                "passphrase": self.passphrase,
                "timestamp": timestamp,
                "sign": signature
            }]
        }

        self.ws.send(json.dumps(login_msg))

    def _send_subscribe(self, subscription: Dict):
        """发送订阅请求"""
        subscribe_msg = {
            "op": "subscribe",
            "args": [subscription]
        }
        self.ws.send(json.dumps(subscribe_msg))

    def _heartbeat_loop(self):
        """心跳循环"""
        while self.is_connected:
            try:
                if time.time() - self.last_heartbeat > self.heartbeat_interval:
                    ping_msg = {"op": "ping"}
                    self.ws.send(json.dumps(ping_msg))
                    self.last_heartbeat = time.time()
                time.sleep(10)
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")

    def connect(self):
        """建立WebSocket连接"""
        if self.is_connected:
            logger.warning("WebSocket already connected")
            return

        self.ws = WebSocketApp(
            self.ws_url,
            on_open=self._on_open,
            on_message=self._on_message,
            on_error=self._on_error,
            on_close=self._on_close
        )

        self.ws_thread = threading.Thread(target=self.ws.run_forever)
        self.ws_thread.daemon = True
        self.ws_thread.start()

        # 启动心跳
        heartbeat_thread = threading.Thread(target=self._heartbeat_loop)
        heartbeat_thread.daemon = True
        heartbeat_thread.start()

    def disconnect(self):
        """断开连接"""
        self.should_reconnect = False
        if self.ws:
            self.ws.close()
        self.is_connected = False

    def subscribe(self, channel: str, inst_id: Optional[str] = None, callback: Optional[Callable] = None):
        """
        订阅通道

        Args:
            channel: 通道名称
            inst_id: 标的ID（可选）
            callback: 回调函数
        """
        subscription = {"channel": channel}
        if inst_id:
            subscription["instId"] = inst_id

        # 保存订阅
        self.subscriptions.append(subscription)

        # 注册回调
        if callback:
            key = f"{channel}:{inst_id}" if inst_id else channel
            self.callbacks[key] = callback

        # 如果已连接，立即订阅
        if self.is_connected:
            self._send_subscribe(subscription)
