"""
网格交易策略
适合震荡行情，通过价格在网格间波动赚取差价
判断震荡市 → 设置网格 → 低买高卖
"""

import numpy as np
from typing import Dict, Optional, List, Tuple
import sys
import os

sys.path.append(os.path.dirname(os.path.dirname(__file__)))
from strategies.base_strategy import BaseStrategy
from utils.technical_indicators import TechnicalIndicators


class GridTradingStrategy(BaseStrategy):
    """网格交易策略"""

    def __init__(self, weight: float = 0.25, config: Dict = None):
        """
        初始化网格交易策略

        Args:
            weight: 策略权重
            config: 配置参数
        """
        default_config = {
            'enabled': True,
            'min_signal_score': 6,  # 网格策略要求更高的确定性
            'grid_levels': 10,  # 网格层数
            'grid_range': 0.05,  # 网格范围（±5%）
            'volatility_threshold': 0.20,  # 波动率阈值（20%）
            'stop_loss_pct': 0.02,  # 2%
            'take_profit_pcts': [0.02, 0.03, 0.04]  # 网格策略止盈更保守
        }

        if config:
            default_config.update(config)

        super().__init__('GridTrading', weight, default_config)

        self.grid_levels = default_config['grid_levels']
        self.grid_range = default_config['grid_range']
        self.volatility_threshold = default_config['volatility_threshold']
        self.stop_loss_pct = default_config['stop_loss_pct']
        self.take_profit_pcts = default_config['take_profit_pcts']

    def generate_signal(self,
                       symbol: str,
                       market_data: Dict,
                       indicators: Optional[Dict] = None,
                       account_info: Optional[Dict] = None,
                       positions: Optional[List[Dict]] = None) -> Optional[Dict]:
        """
        生成网格交易信号

        评分规则（总分10分）：
        1. 震荡检测（4分）：ATR波动率 + 价格横盘
        2. 网格位置（3分）：当前价格距离网格的位置
        3. RSI中性（2分）：RSI在40-60之间
        4. 成交量（1分）：成交量不能太大（避免趋势行情）
        """
        # 检查数据长度
        if len(market_data['close']) < 50:
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

        # ========== 1. 震荡检测（4分）==========
        oscillation_score, is_oscillating = self._detect_oscillation(
            close, high, low, indicators['atr']
        )

        # 不在震荡行情中，不生成信号
        if not is_oscillating:
            return None

        # ========== 2. 计算网格并评分（3分）==========
        grid_score, grid_signal, grid_center = self._calculate_grid_score(
            current_price, close
        )

        # ========== 3. RSI中性检测（2分）==========
        rsi_score = self._calculate_rsi_neutrality_score(indicators['rsi'])

        # ========== 4. 成交量检测（1分）==========
        volume_score = self._calculate_volume_score(volume)

        # ========== 综合评分 ==========
        total_score = oscillation_score + grid_score + rsi_score + volume_score

        # 信号必须达到最低分数且有明确的网格信号
        if total_score < self.min_signal_score or grid_signal is None:
            return None

        # 已有持仓则不重复开仓
        if self.has_existing_position(symbol, positions):
            return None

        # 构建信号原因
        reason = self._build_reason(
            grid_signal, grid_center, current_price,
            oscillation_score, grid_score, rsi_score, volume_score
        )

        # 格式化信号
        signal = self.format_signal(
            symbol=symbol,
            direction=grid_signal,
            score=total_score,
            entry_price=current_price,
            stop_loss_pct=self.stop_loss_pct,
            take_profit_pcts=self.take_profit_pcts,
            reason=reason,
            timestamp=market_data['timestamp'][-1]
        )

        # 添加网格信息
        signal['grid_center'] = grid_center
        signal['grid_levels'] = self.grid_levels
        signal['grid_range'] = self.grid_range

        return signal

    def _detect_oscillation(self, close: np.ndarray, high: np.ndarray,
                           low: np.ndarray, atr: np.ndarray) -> Tuple[float, bool]:
        """
        检测震荡行情（4分）

        Args:
            close: 收盘价数组
            high: 最高价数组
            low: 最低价数组
            atr: ATR数组

        Returns:
            (震荡得分, 是否震荡)
        """
        score = 0.0

        # 1. ATR波动率检测（2分）
        if np.isnan(atr[-1]):
            return 0.0, False

        current_price = close[-1]
        atr_normalized = atr[-1] / current_price  # ATR相对价格的比例

        if atr_normalized < 0.01:  # 极低波动
            score += 2.0
            is_low_volatility = True
        elif atr_normalized < self.volatility_threshold:  # 中等波动
            score += 1.5
            is_low_volatility = True
        else:  # 高波动（趋势行情）
            return score, False

        # 2. 价格横盘检测（2分）
        # 计算最近20根K线的价格范围
        if len(close) >= 20:
            recent_high = np.max(high[-20:])
            recent_low = np.min(low[-20:])
            price_range = (recent_high - recent_low) / current_price

            # 价格范围小于10%认为是震荡
            if price_range < 0.10:
                score += 2.0
            elif price_range < 0.15:
                score += 1.0
            else:
                # 价格波动太大，可能是趋势
                return score, False

        return min(score, 4.0), is_low_volatility

    def _calculate_grid_score(self, current_price: float,
                             close: np.ndarray) -> Tuple[float, Optional[str], float]:
        """
        计算网格得分和信号（3分）

        Args:
            current_price: 当前价格
            close: 收盘价数组

        Returns:
            (网格得分, 信号方向, 网格中心价)
        """
        score = 0.0

        # 计算网格中心价（使用最近20根K线的中位数）
        if len(close) >= 20:
            grid_center = np.median(close[-20:])
        else:
            grid_center = np.median(close)

        # 计算网格边界
        grid_upper = grid_center * (1 + self.grid_range)
        grid_lower = grid_center * (1 - self.grid_range)

        # 网格间距
        grid_step = (grid_upper - grid_lower) / self.grid_levels

        # 计算当前价格在网格中的位置（0-100）
        if current_price > grid_center:
            grid_position = 50 + ((current_price - grid_center) / (grid_upper - grid_center)) * 50
        else:
            grid_position = 50 - ((grid_center - current_price) / (grid_center - grid_lower)) * 50

        signal = None

        # 在下方网格（买入信号）
        if grid_position < 30:  # 下方30%区域
            score += 3.0
            signal = 'buy'
        elif grid_position < 40:  # 下方40%区域
            score += 2.0
            signal = 'buy'
        # 在上方网格（卖出信号）
        elif grid_position > 70:  # 上方30%区域
            score += 3.0
            signal = 'sell'
        elif grid_position > 60:  # 上方40%区域
            score += 2.0
            signal = 'sell'
        # 在中间区域（不交易）
        else:
            score += 0.5
            signal = None

        return min(score, 3.0), signal, float(grid_center)

    def _calculate_rsi_neutrality_score(self, rsi: np.ndarray) -> float:
        """
        计算RSI中性得分（2分）
        网格策略偏好RSI在中性区域

        Args:
            rsi: RSI数组

        Returns:
            RSI得分（0-2）
        """
        if np.isnan(rsi[-1]):
            return 0.0

        current_rsi = rsi[-1]

        # RSI在40-60之间（中性区域）
        if 40 <= current_rsi <= 60:
            return 2.0
        # RSI在35-65之间（接近中性）
        elif 35 <= current_rsi <= 65:
            return 1.5
        # RSI在30-70之间（可接受）
        elif 30 <= current_rsi <= 70:
            return 1.0
        # RSI极端值（不适合网格交易）
        else:
            return 0.0

    def _calculate_volume_score(self, volume: np.ndarray) -> float:
        """
        计算成交量得分（1分）
        网格策略偏好成交量稳定，避免暴涨暴跌

        Args:
            volume: 成交量数组

        Returns:
            成交量得分（0-1）
        """
        if len(volume) < 20:
            return 0.5

        current_volume = volume[-1]
        avg_volume = np.mean(volume[-20:-1])

        volume_ratio = current_volume / avg_volume if avg_volume > 0 else 1

        # 成交量在平均水平附近（0.8-1.5倍）
        if 0.8 <= volume_ratio <= 1.5:
            return 1.0
        # 成交量略有变化（0.6-2倍）
        elif 0.6 <= volume_ratio <= 2.0:
            return 0.7
        # 成交量波动较大
        elif 0.4 <= volume_ratio <= 3.0:
            return 0.3
        # 成交量异常（可能有趋势）
        else:
            return 0.0

    def _build_reason(self, signal: str, grid_center: float, current_price: float,
                     oscillation_score: float, grid_score: float,
                     rsi_score: float, volume_score: float) -> str:
        """构建信号原因描述"""
        reasons = []

        # 震荡市场
        if oscillation_score >= 3.0:
            reasons.append("强震荡市场")
        elif oscillation_score >= 2.0:
            reasons.append("震荡市场")

        # 网格位置
        price_deviation = (current_price - grid_center) / grid_center * 100
        if signal == 'buy':
            reasons.append(f"价格低于中心{abs(price_deviation):.1f}%")
        elif signal == 'sell':
            reasons.append(f"价格高于中心{abs(price_deviation):.1f}%")

        # RSI中性
        if rsi_score >= 1.5:
            reasons.append("RSI中性")

        # 成交量稳定
        if volume_score >= 0.7:
            reasons.append("成交量稳定")

        # 得分
        total_score = oscillation_score + grid_score + rsi_score + volume_score
        reasons.append(f"总分{total_score:.1f}/10")

        return " | ".join(reasons)
