"""
趋势跟踪策略
使用EMA金叉/死叉、MACD、布林带、RSI、成交量综合判断趋势
适合趋势明显的市场环境
"""

import numpy as np
from typing import Dict, Optional, List
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from strategies.base_strategy import BaseStrategy
from utils.technical_indicators import TechnicalIndicators


class TrendFollowingStrategy(BaseStrategy):
    """趋势跟踪策略"""

    def __init__(self, weight: float = 0.30, config: Dict = None):
        """
        初始化趋势跟踪策略

        Args:
            weight: 策略权重
            config: 配置参数
        """
        default_config = {
            'enabled': True,
            'min_signal_score': 5,
            'ema_fast': 10,
            'ema_slow': 20,
            'stop_loss_pct': 0.02,  # 2%
            'take_profit_pcts': [0.03, 0.05, 0.08]  # 3%, 5%, 8%
        }

        if config:
            default_config.update(config)

        super().__init__('TrendFollowing', weight, default_config)

        self.ema_fast = default_config['ema_fast']
        self.ema_slow = default_config['ema_slow']
        self.stop_loss_pct = default_config['stop_loss_pct']
        self.take_profit_pcts = default_config['take_profit_pcts']

    def generate_signal(self,
                       symbol: str,
                       market_data: Dict,
                       indicators: Optional[Dict] = None,
                       account_info: Optional[Dict] = None,
                       positions: Optional[List[Dict]] = None) -> Optional[Dict]:
        """
        生成趋势跟踪信号

        评分规则（总分10分）：
        1. 趋势得分（3分）：EMA排列 + 金叉/死叉
        2. MACD得分（2分）：MACD与信号线关系 + 柱状图
        3. 布林带得分（2分）：价格相对布林带位置
        4. RSI得分（2分）：RSI是否过热/超卖
        5. 成交量得分（1分）：成交量是否放大
        """
        # 检查数据长度
        if len(market_data['close']) < 50:
            return None

        # 计算技术指标（如果未提供）
        if indicators is None:
            indicators = self.calculate_indicators(market_data)

        close = market_data['close']
        volume = market_data['volume']

        # 提取指标
        ema_10 = indicators['ema_10']
        ema_20 = indicators['ema_20']
        ema_50 = indicators['ema_50']
        macd_data = indicators['macd']
        rsi = indicators['rsi']
        bollinger = indicators['bollinger']

        # 当前价格
        current_price = float(close[-1])

        # ========== 1. 趋势得分（3分）==========
        trend_score = self._calculate_trend_score(ema_10, ema_20, ema_50)

        # 检测EMA金叉/死叉
        golden_cross, death_cross = TechnicalIndicators.detect_crossover(ema_10, ema_20)

        # ========== 2. MACD得分（2分）==========
        macd_score = self._calculate_macd_score(macd_data)

        # ========== 3. 布林带得分（2分）==========
        bollinger_score, bb_signal = self._calculate_bollinger_score(
            current_price, bollinger
        )

        # ========== 4. RSI得分（2分）==========
        rsi_score, rsi_signal = self._calculate_rsi_score(rsi)

        # ========== 5. 成交量得分（1分）==========
        volume_score = self._calculate_volume_score(volume)

        # ========== 综合评分 ==========
        total_score = trend_score + macd_score + bollinger_score + rsi_score + volume_score

        # 判断信号方向
        direction = None
        if golden_cross and total_score >= self.min_signal_score:
            direction = 'buy'
        elif death_cross and total_score >= self.min_signal_score:
            direction = 'sell'

        # 如果没有明确的金叉/死叉，根据各项指标判断
        if direction is None and total_score >= self.min_signal_score + 1:
            # 强趋势信号
            if trend_score >= 2 and macd_score >= 1 and bb_signal:
                if bb_signal == 'buy' and rsi_signal != 'overbought':
                    direction = 'buy'
                elif bb_signal == 'sell' and rsi_signal != 'oversold':
                    direction = 'sell'

        # 无有效信号
        if direction is None:
            return None

        # 已有持仓则不重复开仓
        if self.has_existing_position(symbol, positions):
            return None

        # 构建信号原因
        reason = self._build_reason(
            direction, golden_cross, death_cross,
            trend_score, macd_score, bollinger_score, rsi_score, volume_score
        )

        # 格式化信号
        signal = self.format_signal(
            symbol=symbol,
            direction=direction,
            score=total_score,
            entry_price=current_price,
            stop_loss_pct=self.stop_loss_pct,
            take_profit_pcts=self.take_profit_pcts,
            reason=reason,
            timestamp=market_data['timestamp'][-1]
        )

        return signal

    def _calculate_trend_score(self, ema_10: np.ndarray, ema_20: np.ndarray,
                               ema_50: np.ndarray) -> float:
        """
        计算趋势得分（3分）

        Args:
            ema_10: EMA10
            ema_20: EMA20
            ema_50: EMA50

        Returns:
            趋势得分（0-3）
        """
        score = 0.0

        # 检查是否有有效数据
        if np.isnan(ema_10[-1]) or np.isnan(ema_20[-1]) or np.isnan(ema_50[-1]):
            return 0.0

        # 多头排列：EMA10 > EMA20 > EMA50
        if ema_10[-1] > ema_20[-1] > ema_50[-1]:
            score += 1.5
        # 空头排列：EMA10 < EMA20 < EMA50
        elif ema_10[-1] < ema_20[-1] < ema_50[-1]:
            score += 1.5

        # EMA斜率（趋势强度）
        ema_20_slope = (ema_20[-1] - ema_20[-5]) / ema_20[-5] if len(ema_20) >= 5 else 0
        if abs(ema_20_slope) > 0.005:  # 斜率>0.5%
            score += 1.0
        elif abs(ema_20_slope) > 0.002:  # 斜率>0.2%
            score += 0.5

        return min(score, 3.0)

    def _calculate_macd_score(self, macd_data: Dict) -> float:
        """
        计算MACD得分（2分）

        Args:
            macd_data: MACD数据

        Returns:
            MACD得分（0-2）
        """
        score = 0.0

        macd_line = macd_data['macd']
        signal_line = macd_data['signal']
        histogram = macd_data['histogram']

        # 检查是否有有效数据
        if np.isnan(macd_line[-1]) or np.isnan(signal_line[-1]):
            return 0.0

        # MACD在信号线上方（多头）
        if macd_line[-1] > signal_line[-1]:
            score += 1.0
        # MACD在信号线下方（空头）
        elif macd_line[-1] < signal_line[-1]:
            score += 1.0

        # 柱状图扩大（趋势加强）
        if len(histogram) >= 2 and not np.isnan(histogram[-2]):
            if abs(histogram[-1]) > abs(histogram[-2]):
                score += 1.0
            elif abs(histogram[-1]) > abs(histogram[-2]) * 0.8:
                score += 0.5

        return min(score, 2.0)

    def _calculate_bollinger_score(self, current_price: float,
                                   bollinger: Dict) -> tuple:
        """
        计算布林带得分（2分）

        Args:
            current_price: 当前价格
            bollinger: 布林带数据

        Returns:
            (得分, 信号方向)
        """
        score = 0.0
        signal = None

        upper = bollinger['upper'][-1]
        middle = bollinger['middle'][-1]
        lower = bollinger['lower'][-1]

        if np.isnan(upper) or np.isnan(middle) or np.isnan(lower):
            return 0.0, None

        # 计算价格在布林带中的位置（0-100）
        bb_position = (current_price - lower) / (upper - lower) * 100

        # 突破上轨（超买，可能回调或强势突破）
        if bb_position > 95:
            score += 2.0
            signal = 'sell'  # 趋势跟踪中，也可能是强势买入信号
        # 突破下轨（超卖，可能反弹或弱势跌破）
        elif bb_position < 5:
            score += 2.0
            signal = 'buy'
        # 接近上轨
        elif bb_position > 80:
            score += 1.5
            signal = 'buy'
        # 接近下轨
        elif bb_position < 20:
            score += 1.5
            signal = 'sell'
        # 中性位置
        elif 40 < bb_position < 60:
            score += 0.5

        return min(score, 2.0), signal

    def _calculate_rsi_score(self, rsi: np.ndarray) -> tuple:
        """
        计算RSI得分（2分）

        Args:
            rsi: RSI数组

        Returns:
            (得分, 信号状态)
        """
        score = 0.0
        signal = None

        if np.isnan(rsi[-1]):
            return 0.0, None

        current_rsi = rsi[-1]

        # 超卖区（<30）
        if current_rsi < 30:
            score += 2.0
            signal = 'oversold'
        # 超买区（>70）
        elif current_rsi > 70:
            score += 2.0
            signal = 'overbought'
        # 强势区（50-70）
        elif 50 <= current_rsi <= 70:
            score += 1.0
            signal = 'bullish'
        # 弱势区（30-50）
        elif 30 <= current_rsi <= 50:
            score += 1.0
            signal = 'bearish'

        return min(score, 2.0), signal

    def _calculate_volume_score(self, volume: np.ndarray) -> float:
        """
        计算成交量得分（1分）

        Args:
            volume: 成交量数组

        Returns:
            成交量得分（0-1）
        """
        if len(volume) < 20:
            return 0.0

        current_volume = volume[-1]
        avg_volume = np.mean(volume[-20:-1])

        # 成交量放大
        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1

        if volume_ratio > 2.0:  # 成交量翻倍
            return 1.0
        elif volume_ratio > 1.5:  # 成交量增加50%
            return 0.7
        elif volume_ratio > 1.2:  # 成交量增加20%
            return 0.5
        else:
            return 0.2

    def _build_reason(self, direction: str, golden_cross: bool, death_cross: bool,
                     trend_score: float, macd_score: float, bollinger_score: float,
                     rsi_score: float, volume_score: float) -> str:
        """构建信号原因描述"""
        reasons = []

        if golden_cross:
            reasons.append("EMA金叉")
        elif death_cross:
            reasons.append("EMA死叉")

        if trend_score >= 2.0:
            reasons.append(f"趋势强劲({trend_score:.1f}/3)")
        elif trend_score >= 1.0:
            reasons.append(f"趋势中等({trend_score:.1f}/3)")

        if macd_score >= 1.5:
            reasons.append(f"MACD确认({macd_score:.1f}/2)")

        if bollinger_score >= 1.5:
            reasons.append(f"布林带突破({bollinger_score:.1f}/2)")

        if rsi_score >= 1.5:
            reasons.append(f"RSI指示{direction}({rsi_score:.1f}/2)")

        if volume_score >= 0.7:
            reasons.append(f"成交量放大({volume_score:.1f}/1)")

        return " | ".join(reasons) if reasons else f"{direction.upper()} signal"
