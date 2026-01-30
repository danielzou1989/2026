"""
策略基类 - 定义所有策略的统一接口
所有具体策略必须继承此基类并实现generate_signal方法
"""

from abc import ABC, abstractmethod
from typing import Dict, Optional, List
import sys
import os

# 添加父目录到路径
sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from utils.technical_indicators import TechnicalIndicators


class BaseStrategy(ABC):
    """策略基类"""

    def __init__(self, name: str, weight: float, config: Dict):
        """
        初始化策略

        Args:
            name: 策略名称
            weight: 策略权重（0-1）
            config: 策略配置参数
        """
        self.name = name
        self.weight = weight
        self.config = config
        self.enabled = config.get('enabled', True)
        self.min_signal_score = config.get('min_signal_score', 5)

    @abstractmethod
    def generate_signal(self,
                       symbol: str,
                       market_data: Dict,
                       indicators: Optional[Dict] = None,
                       account_info: Optional[Dict] = None,
                       positions: Optional[List[Dict]] = None) -> Optional[Dict]:
        """
        生成交易信号（抽象方法，子类必须实现）

        Args:
            symbol: 交易对符号
            market_data: 市场数据
                {
                    'timestamp': List[int],
                    'open': np.ndarray,
                    'high': np.ndarray,
                    'low': np.ndarray,
                    'close': np.ndarray,
                    'volume': np.ndarray,
                    'bid': np.ndarray,
                    'ask': np.ndarray
                }
            indicators: 技术指标（如果已计算）
            account_info: 账户信息
            positions: 当前持仓

        Returns:
            交易信号字典，如果无信号则返回None
            {
                'strategy': 策略名称,
                'symbol': 交易对,
                'direction': 'buy' / 'sell',
                'score': 0-10评分,
                'strength': 'strong' / 'medium' / 'weak',
                'entry_price': 建议入场价格,
                'stop_loss': 止损价格,
                'stop_loss_pct': 止损百分比,
                'take_profit': 止盈价格列表,
                'take_profit_pcts': 止盈百分比列表,
                'confidence': 0-1置信度,
                'reason': 信号原因描述,
                'timestamp': 信号生成时间戳
            }
        """
        pass

    def calculate_indicators(self, market_data: Dict) -> Dict:
        """
        计算技术指标（公共方法）

        Args:
            market_data: 市场数据

        Returns:
            技术指标字典
        """
        return TechnicalIndicators.calculate_all_indicators(market_data)

    def calculate_stop_loss(self, entry_price: float, direction: str, stop_loss_pct: float) -> float:
        """
        计算止损价格

        Args:
            entry_price: 入场价格
            direction: 方向 (buy/sell)
            stop_loss_pct: 止损百分比（如0.02表示2%）

        Returns:
            止损价格
        """
        if direction == 'buy':
            return entry_price * (1 - stop_loss_pct)
        else:  # sell
            return entry_price * (1 + stop_loss_pct)

    def calculate_take_profit(self, entry_price: float, direction: str,
                             take_profit_pcts: List[float]) -> List[float]:
        """
        计算止盈价格列表

        Args:
            entry_price: 入场价格
            direction: 方向 (buy/sell)
            take_profit_pcts: 止盈百分比列表（如[0.03, 0.05, 0.08]）

        Returns:
            止盈价格列表
        """
        take_profits = []
        for pct in take_profit_pcts:
            if direction == 'buy':
                tp = entry_price * (1 + pct)
            else:  # sell
                tp = entry_price * (1 - pct)
            take_profits.append(tp)

        return take_profits

    def evaluate_signal_strength(self, score: float) -> str:
        """
        根据评分评估信号强度

        Args:
            score: 信号评分（0-10）

        Returns:
            'strong' / 'medium' / 'weak'
        """
        if score >= 8:
            return 'strong'
        elif score >= 6:
            return 'medium'
        else:
            return 'weak'

    def get_current_price(self, market_data: Dict) -> float:
        """
        获取当前价格（最新收盘价）

        Args:
            market_data: 市场数据

        Returns:
            当前价格
        """
        return float(market_data['close'][-1])

    def has_existing_position(self, symbol: str, positions: Optional[List[Dict]]) -> bool:
        """
        检查是否已有持仓

        Args:
            symbol: 交易对符号
            positions: 持仓列表

        Returns:
            是否已有持仓
        """
        if not positions:
            return False

        for pos in positions:
            if pos.get('symbol') == symbol and pos.get('qty', 0) > 0:
                return True

        return False

    def format_signal(self, symbol: str, direction: str, score: float,
                     entry_price: float, stop_loss_pct: float,
                     take_profit_pcts: List[float], reason: str,
                     timestamp: Optional[int] = None) -> Dict:
        """
        格式化信号输出（标准化）

        Args:
            symbol: 交易对
            direction: 方向
            score: 评分
            entry_price: 入场价格
            stop_loss_pct: 止损百分比
            take_profit_pcts: 止盈百分比列表
            reason: 原因
            timestamp: 时间戳

        Returns:
            标准化的信号字典
        """
        import time

        stop_loss = self.calculate_stop_loss(entry_price, direction, stop_loss_pct)
        take_profits = self.calculate_take_profit(entry_price, direction, take_profit_pcts)
        strength = self.evaluate_signal_strength(score)
        confidence = min(score / 10.0, 1.0)

        return {
            'strategy': self.name,
            'symbol': symbol,
            'direction': direction,
            'score': score,
            'strength': strength,
            'entry_price': entry_price,
            'stop_loss': stop_loss,
            'stop_loss_pct': stop_loss_pct,
            'take_profit': take_profits,
            'take_profit_pcts': take_profit_pcts,
            'confidence': confidence,
            'reason': reason,
            'timestamp': timestamp or int(time.time() * 1000)
        }

    def is_enabled(self) -> bool:
        """策略是否启用"""
        return self.enabled

    def get_weight(self) -> float:
        """获取策略权重"""
        return self.weight

    def __str__(self) -> str:
        """字符串表示"""
        return f"{self.name} (weight={self.weight}, enabled={self.enabled})"

    def __repr__(self) -> str:
        """调试表示"""
        return f"<{self.__class__.__name__}: {self.name}>"
