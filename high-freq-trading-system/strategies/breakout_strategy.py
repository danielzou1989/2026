"""
突破策略
识别价格突破关键支撑/阻力位，捕捉突破后的趋势
要求：突破幅度足够 + 成交量确认 + 连续K线确认
"""

import numpy as np
from typing import Dict, Optional, List, Tuple
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from strategies.base_strategy import BaseStrategy
from utils.technical_indicators import TechnicalIndicators


class BreakoutStrategy(BaseStrategy):
    """突破策略"""

    def __init__(self, weight: float = 0.25, config: Dict = None):
        """
        初始化突破策略

        Args:
            weight: 策略权重
            config: 配置参数
        """
        default_config = {
            'enabled': True,
            'min_signal_score': 5,
            'lookback_period': 48,  # 4小时（48根5分钟K线）
            'min_breakout_pct': 0.003,  # 最小突破幅度（0.3%）
            'volume_multiplier': 1.5,  # 成交量放大倍数
            'confirmation_bars': 2,  # 确认K线数量
            'stop_loss_pct': 0.03,  # 3%（给予更大空间）
            'take_profit_pcts': [0.04, 0.06, 0.10]  # 4%, 6%, 10%
        }

        if config:
            default_config.update(config)

        super().__init__('Breakout', weight, default_config)

        self.lookback_period = default_config['lookback_period']
        self.min_breakout_pct = default_config['min_breakout_pct']
        self.volume_multiplier = default_config['volume_multiplier']
        self.confirmation_bars = default_config['confirmation_bars']
        self.stop_loss_pct = default_config['stop_loss_pct']
        self.take_profit_pcts = default_config['take_profit_pcts']

    def generate_signal(self,
                       symbol: str,
                       market_data: Dict,
                       indicators: Optional[Dict] = None,
                       account_info: Optional[Dict] = None,
                       positions: Optional[List[Dict]] = None) -> Optional[Dict]:
        """
        生成突破信号

        评分规则（总分10分）：
        1. 突破强度（4分）：突破幅度 + 连续确认
        2. 成交量确认（3分）：成交量放大倍数
        3. 趋势支持（2分）：EMA方向是否支持
        4. RSI确认（1分）：RSI不在极端区域
        """
        # 检查数据长度
        if len(market_data['close']) < self.lookback_period + 5:
            return None

        # 计算技术指标（如果未提供）
        if indicators is None:
            indicators = self.calculate_indicators(market_data)

        close = market_data['close']
        high = market_data['high']
        low = market_data['low']
        volume = market_data['volume']

        # 当前价格
        current_price = float(close[-1])

        # ========== 1. 计算支撑/阻力位 ==========
        resistance, support = self._calculate_support_resistance(
            high, low, self.lookback_period
        )

        # ========== 2. 检测突破（4分）==========
        breakout_score, breakout_direction = self._detect_breakout(
            current_price, high, low, close, resistance, support
        )

        # 无突破
        if breakout_direction is None:
            return None

        # ========== 3. 成交量确认（3分）==========
        volume_score = self._calculate_volume_confirmation(volume)

        # ========== 4. 趋势支持（2分）==========
        trend_score = self._calculate_trend_support(
            indicators['ema_10'], indicators['ema_20'], breakout_direction
        )

        # ========== 5. RSI确认（1分）==========
        rsi_score = self._calculate_rsi_confirmation(indicators['rsi'], breakout_direction)

        # ========== 综合评分 ==========
        total_score = breakout_score + volume_score + trend_score + rsi_score

        # 信号必须达到最低分数
        if total_score < self.min_signal_score:
            return None

        # 已有持仓则不重复开仓
        if self.has_existing_position(symbol, positions):
            return None

        # 构建信号原因
        reason = self._build_reason(
            breakout_direction, resistance, support, current_price,
            breakout_score, volume_score, trend_score, rsi_score
        )

        # 格式化信号
        signal = self.format_signal(
            symbol=symbol,
            direction=breakout_direction,
            score=total_score,
            entry_price=current_price,
            stop_loss_pct=self.stop_loss_pct,
            take_profit_pcts=self.take_profit_pcts,
            reason=reason,
            timestamp=market_data['timestamp'][-1]
        )

        # 添加突破信息
        signal['resistance'] = resistance
        signal['support'] = support
        signal['breakout_level'] = resistance if breakout_direction == 'buy' else support

        return signal

    def _calculate_support_resistance(self, high: np.ndarray, low: np.ndarray,
                                     lookback: int) -> Tuple[float, float]:
        """
        计算支撑/阻力位

        Args:
            high: 最高价数组
            low: 最低价数组
            lookback: 回看周期

        Returns:
            (阻力位, 支撑位)
        """
        # 使用最近lookback根K线的最高/最低价
        resistance = float(np.max(high[-lookback:]))
        support = float(np.min(low[-lookback:]))

        return resistance, support

    def _detect_breakout(self, current_price: float, high: np.ndarray,
                        low: np.ndarray, close: np.ndarray,
                        resistance: float, support: float) -> Tuple[float, Optional[str]]:
        """
        检测突破并评分（4分）

        Args:
            current_price: 当前价格
            high: 最高价数组
            low: 最低价数组
            close: 收盘价数组
            resistance: 阻力位
            support: 支撑位

        Returns:
            (突破得分, 突破方向)
        """
        score = 0.0
        direction = None

        # 向上突破阻力位
        if current_price > resistance:
            breakout_pct = (current_price - resistance) / resistance

            # 突破幅度必须足够
            if breakout_pct >= self.min_breakout_pct:
                direction = 'buy'

                # 突破幅度评分（2分）
                if breakout_pct >= 0.01:  # 突破1%
                    score += 2.0
                elif breakout_pct >= 0.005:  # 突破0.5%
                    score += 1.5
                else:  # 突破0.3%
                    score += 1.0

                # 连续K线确认（2分）
                confirmation_score = self._check_confirmation(
                    close, high, resistance, 'buy'
                )
                score += confirmation_score

        # 向下突破支撑位
        elif current_price < support:
            breakout_pct = (support - current_price) / support

            # 突破幅度必须足够
            if breakout_pct >= self.min_breakout_pct:
                direction = 'sell'

                # 突破幅度评分（2分）
                if breakout_pct >= 0.01:  # 突破1%
                    score += 2.0
                elif breakout_pct >= 0.005:  # 突破0.5%
                    score += 1.5
                else:  # 突破0.3%
                    score += 1.0

                # 连续K线确认（2分）
                confirmation_score = self._check_confirmation(
                    close, low, support, 'sell'
                )
                score += confirmation_score

        return min(score, 4.0), direction

    def _check_confirmation(self, close: np.ndarray, extreme: np.ndarray,
                           level: float, direction: str) -> float:
        """
        检查连续K线确认

        Args:
            close: 收盘价数组
            extreme: 最高价或最低价数组
            level: 支撑/阻力位
            direction: 方向

        Returns:
            确认得分（0-2）
        """
        score = 0.0

        # 检查最近几根K线是否持续在突破水平之上/之下
        confirmed_bars = 0

        for i in range(1, min(self.confirmation_bars + 1, len(close))):
            if direction == 'buy':
                if close[-i] > level and extreme[-i] > level:
                    confirmed_bars += 1
            else:  # sell
                if close[-i] < level and extreme[-i] < level:
                    confirmed_bars += 1

        # 根据确认K线数量评分
        if confirmed_bars >= self.confirmation_bars:
            score = 2.0
        elif confirmed_bars >= 1:
            score = 1.0

        return score

    def _calculate_volume_confirmation(self, volume: np.ndarray) -> float:
        """
        计算成交量确认得分（3分）

        Args:
            volume: 成交量数组

        Returns:
            成交量得分（0-3）
        """
        if len(volume) < 20:
            return 0.0

        current_volume = volume[-1]
        avg_volume = np.mean(volume[-20:-1])

        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1

        # 成交量放大倍数
        if volume_ratio >= 3.0:  # 3倍以上
            return 3.0
        elif volume_ratio >= 2.0:  # 2倍以上
            return 2.5
        elif volume_ratio >= self.volume_multiplier:  # 1.5倍以上
            return 2.0
        elif volume_ratio >= 1.2:  # 1.2倍以上
            return 1.0
        else:
            return 0.0

    def _calculate_trend_support(self, ema_10: np.ndarray, ema_20: np.ndarray,
                                direction: str) -> float:
        """
        计算趋势支持得分（2分）

        Args:
            ema_10: EMA10
            ema_20: EMA20
            direction: 突破方向

        Returns:
            趋势得分（0-2）
        """
        if np.isnan(ema_10[-1]) or np.isnan(ema_20[-1]):
            return 0.0

        score = 0.0

        # EMA方向与突破方向一致
        if direction == 'buy':
            # 多头排列
            if ema_10[-1] > ema_20[-1]:
                score += 1.5
            # EMA向上
            if len(ema_20) >= 3 and ema_20[-1] > ema_20[-3]:
                score += 0.5

        else:  # sell
            # 空头排列
            if ema_10[-1] < ema_20[-1]:
                score += 1.5
            # EMA向下
            if len(ema_20) >= 3 and ema_20[-1] < ema_20[-3]:
                score += 0.5

        return min(score, 2.0)

    def _calculate_rsi_confirmation(self, rsi: np.ndarray, direction: str) -> float:
        """
        计算RSI确认得分（1分）

        Args:
            rsi: RSI数组
            direction: 突破方向

        Returns:
            RSI得分（0-1）
        """
        if np.isnan(rsi[-1]):
            return 0.5

        current_rsi = rsi[-1]

        # 向上突破
        if direction == 'buy':
            # RSI不能超买
            if current_rsi < 70:
                return 1.0
            elif current_rsi < 80:
                return 0.5
            else:
                return 0.0

        # 向下突破
        else:  # sell
            # RSI不能超卖
            if current_rsi > 30:
                return 1.0
            elif current_rsi > 20:
                return 0.5
            else:
                return 0.0

    def _build_reason(self, direction: str, resistance: float, support: float,
                     current_price: float, breakout_score: float,
                     volume_score: float, trend_score: float, rsi_score: float) -> str:
        """构建信号原因描述"""
        reasons = []

        # 突破方向
        if direction == 'buy':
            breakout_pct = (current_price - resistance) / resistance * 100
            reasons.append(f"向上突破阻力位{breakout_pct:.2f}%")
        else:
            breakout_pct = (support - current_price) / support * 100
            reasons.append(f"向下突破支撑位{breakout_pct:.2f}%")

        # 突破强度
        if breakout_score >= 3.0:
            reasons.append("强突破+K线确认")
        elif breakout_score >= 2.0:
            reasons.append("有效突破")

        # 成交量
        if volume_score >= 2.5:
            reasons.append("成交量大幅放大")
        elif volume_score >= 2.0:
            reasons.append("成交量放大确认")

        # 趋势
        if trend_score >= 1.5:
            reasons.append("趋势支持")

        # RSI
        if rsi_score >= 0.8:
            reasons.append("RSI正常")

        # 总分
        total_score = breakout_score + volume_score + trend_score + rsi_score
        reasons.append(f"总分{total_score:.1f}/10")

        return " | ".join(reasons)
