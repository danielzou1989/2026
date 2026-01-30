"""
数据管理器 - 缓存K线数据和市场数据
使用deque自动淘汰旧数据，支持多币种多周期
"""

import numpy as np
from collections import deque
from typing import Dict, List, Optional
from datetime import datetime


class DataManager:
    """数据管理器：缓存K线数据和技术指标"""

    def __init__(self, max_bars: int = 1000):
        """
        初始化数据管理器

        Args:
            max_bars: 最大缓存K线数量（约3.5天的5分钟数据）
        """
        self.max_bars = max_bars
        self.data: Dict[str, Dict[str, deque]] = {}  # {symbol: {open, high, low, close, volume}}
        self.indicators: Dict[str, Dict[str, any]] = {}  # 缓存的技术指标

    def update_kline(self, symbol: str, kline: Dict) -> None:
        """
        更新K线数据

        Args:
            symbol: 交易对符号
            kline: K线数据
                {
                    'timestamp': 毫秒时间戳,
                    'open': 开盘价,
                    'high': 最高价,
                    'low': 最低价,
                    'close': 收盘价,
                    'volume': 成交量
                }
        """
        if symbol not in self.data:
            self.data[symbol] = {
                'timestamp': deque(maxlen=self.max_bars),
                'open': deque(maxlen=self.max_bars),
                'high': deque(maxlen=self.max_bars),
                'low': deque(maxlen=self.max_bars),
                'close': deque(maxlen=self.max_bars),
                'volume': deque(maxlen=self.max_bars),
                'bid': deque(maxlen=self.max_bars),  # 买一价
                'ask': deque(maxlen=self.max_bars)   # 卖一价
            }

        data = self.data[symbol]
        data['timestamp'].append(kline['timestamp'])
        data['open'].append(float(kline['open']))
        data['high'].append(float(kline['high']))
        data['low'].append(float(kline['low']))
        data['close'].append(float(kline['close']))
        data['volume'].append(float(kline['volume']))

        # 买卖价（如果有的话）
        if 'bid' in kline:
            data['bid'].append(float(kline['bid']))
        else:
            data['bid'].append(float(kline['close']))  # 默认使用收盘价

        if 'ask' in kline:
            data['ask'].append(float(kline['ask']))
        else:
            data['ask'].append(float(kline['close']))

        # 清除该symbol的指标缓存（因为数据更新了）
        if symbol in self.indicators:
            self.indicators[symbol] = {}

    def get_market_data(self, symbol: str, lookback: int = 100) -> Optional[Dict]:
        """
        获取市场数据

        Args:
            symbol: 交易对符号
            lookback: 回看K线数量

        Returns:
            市场数据字典，包含numpy数组
        """
        if symbol not in self.data:
            return None

        data = self.data[symbol]

        # 检查数据是否足够
        if len(data['close']) < lookback:
            lookback = len(data['close'])

        if lookback == 0:
            return None

        return {
            'timestamp': list(data['timestamp'])[-lookback:],
            'open': np.array(list(data['open'])[-lookback:]),
            'high': np.array(list(data['high'])[-lookback:]),
            'low': np.array(list(data['low'])[-lookback:]),
            'close': np.array(list(data['close'])[-lookback:]),
            'volume': np.array(list(data['volume'])[-lookback:]),
            'bid': np.array(list(data['bid'])[-lookback:]),
            'ask': np.array(list(data['ask'])[-lookback:])
        }

    def get_latest_price(self, symbol: str) -> Optional[float]:
        """
        获取最新价格

        Args:
            symbol: 交易对符号

        Returns:
            最新收盘价
        """
        if symbol not in self.data or len(self.data[symbol]['close']) == 0:
            return None

        return self.data[symbol]['close'][-1]

    def get_latest_bid_ask(self, symbol: str) -> Optional[Dict[str, float]]:
        """
        获取最新买卖价

        Args:
            symbol: 交易对符号

        Returns:
            {'bid': 买一价, 'ask': 卖一价}
        """
        if symbol not in self.data or len(self.data[symbol]['close']) == 0:
            return None

        return {
            'bid': self.data[symbol]['bid'][-1],
            'ask': self.data[symbol]['ask'][-1]
        }

    def get_data_length(self, symbol: str) -> int:
        """
        获取数据长度

        Args:
            symbol: 交易对符号

        Returns:
            K线数量
        """
        if symbol not in self.data:
            return 0

        return len(self.data[symbol]['close'])

    def cache_indicator(self, symbol: str, indicator_name: str, value: any) -> None:
        """
        缓存技术指标计算结果

        Args:
            symbol: 交易对符号
            indicator_name: 指标名称
            value: 指标值
        """
        if symbol not in self.indicators:
            self.indicators[symbol] = {}

        self.indicators[symbol][indicator_name] = value

    def get_cached_indicator(self, symbol: str, indicator_name: str) -> Optional[any]:
        """
        获取缓存的技术指标

        Args:
            symbol: 交易对符号
            indicator_name: 指标名称

        Returns:
            缓存的指标值，如果不存在则返回None
        """
        if symbol not in self.indicators:
            return None

        return self.indicators[symbol].get(indicator_name)

    def clear_cache(self, symbol: Optional[str] = None) -> None:
        """
        清除缓存

        Args:
            symbol: 交易对符号，如果为None则清除所有
        """
        if symbol is None:
            self.data.clear()
            self.indicators.clear()
        else:
            if symbol in self.data:
                del self.data[symbol]
            if symbol in self.indicators:
                del self.indicators[symbol]

    def get_summary(self) -> Dict:
        """
        获取数据管理器概况

        Returns:
            概况信息
        """
        summary = {
            'symbols': list(self.data.keys()),
            'data_counts': {}
        }

        for symbol in self.data:
            summary['data_counts'][symbol] = len(self.data[symbol]['close'])

        return summary
