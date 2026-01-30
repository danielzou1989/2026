"""
技术指标库 - 使用numpy向量化计算
实现：EMA, SMA, MACD, RSI, Bollinger Bands, ATR, KDJ
支持增量计算优化
"""

import numpy as np
from typing import Dict, Tuple, Optional


class TechnicalIndicators:
    """技术指标计算类（静态方法）"""

    @staticmethod
    def SMA(data: np.ndarray, period: int) -> np.ndarray:
        """
        简单移动平均 (Simple Moving Average)

        Args:
            data: 价格数据数组
            period: 周期

        Returns:
            SMA数组
        """
        if len(data) < period:
            return np.array([np.nan] * len(data))

        sma = np.convolve(data, np.ones(period) / period, mode='valid')
        # 填充前面的NaN
        return np.concatenate([np.full(period - 1, np.nan), sma])

    @staticmethod
    def EMA(data: np.ndarray, period: int, prev_ema: Optional[float] = None) -> np.ndarray:
        """
        指数移动平均 (Exponential Moving Average)
        支持增量计算

        Args:
            data: 价格数据数组
            period: 周期
            prev_ema: 上一个EMA值（用于增量计算）

        Returns:
            EMA数组
        """
        if len(data) < period:
            return np.array([np.nan] * len(data))

        alpha = 2.0 / (period + 1)
        ema = np.zeros_like(data)

        # 初始值使用SMA
        if prev_ema is None:
            ema[period - 1] = np.mean(data[:period])
            start_idx = period
        else:
            ema[0] = prev_ema
            start_idx = 1

        # 增量计算
        for i in range(start_idx, len(data)):
            ema[i] = alpha * data[i] + (1 - alpha) * ema[i - 1]

        # 填充前面的NaN
        if prev_ema is None:
            ema[:period - 1] = np.nan

        return ema

    @staticmethod
    def MACD(close: np.ndarray, fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, np.ndarray]:
        """
        MACD指标 (Moving Average Convergence Divergence)

        Args:
            close: 收盘价数组
            fast: 快线周期
            slow: 慢线周期
            signal: 信号线周期

        Returns:
            {'macd': MACD线, 'signal': 信号线, 'histogram': 柱状图}
        """
        ema_fast = TechnicalIndicators.EMA(close, fast)
        ema_slow = TechnicalIndicators.EMA(close, slow)

        macd_line = ema_fast - ema_slow
        signal_line = TechnicalIndicators.EMA(macd_line[~np.isnan(macd_line)], signal)

        # 对齐长度
        signal_aligned = np.full_like(macd_line, np.nan)
        signal_aligned[len(signal_aligned) - len(signal_line):] = signal_line

        histogram = macd_line - signal_aligned

        return {
            'macd': macd_line,
            'signal': signal_aligned,
            'histogram': histogram
        }

    @staticmethod
    def RSI(close: np.ndarray, period: int = 14) -> np.ndarray:
        """
        相对强弱指标 (Relative Strength Index)

        Args:
            close: 收盘价数组
            period: 周期

        Returns:
            RSI数组 (0-100)
        """
        if len(close) < period + 1:
            return np.array([np.nan] * len(close))

        # 计算价格变化
        delta = np.diff(close)

        # 分离上涨和下跌
        gains = np.where(delta > 0, delta, 0)
        losses = np.where(delta < 0, -delta, 0)

        # 计算平均涨跌幅
        avg_gain = np.zeros(len(delta))
        avg_loss = np.zeros(len(delta))

        # 初始平均值
        avg_gain[period - 1] = np.mean(gains[:period])
        avg_loss[period - 1] = np.mean(losses[:period])

        # 指数平滑
        for i in range(period, len(delta)):
            avg_gain[i] = (avg_gain[i - 1] * (period - 1) + gains[i]) / period
            avg_loss[i] = (avg_loss[i - 1] * (period - 1) + losses[i]) / period

        # 计算RS和RSI
        rs = np.where(avg_loss != 0, avg_gain / avg_loss, 0)
        rsi = 100 - (100 / (1 + rs))

        # 填充NaN
        rsi_aligned = np.full(len(close), np.nan)
        rsi_aligned[period:] = rsi[period - 1:]

        return rsi_aligned

    @staticmethod
    def BollingerBands(close: np.ndarray, period: int = 20, std_dev: float = 2.0) -> Dict[str, np.ndarray]:
        """
        布林带 (Bollinger Bands)

        Args:
            close: 收盘价数组
            period: 周期
            std_dev: 标准差倍数

        Returns:
            {'upper': 上轨, 'middle': 中轨(SMA), 'lower': 下轨}
        """
        middle = TechnicalIndicators.SMA(close, period)

        # 计算滚动标准差
        std = np.zeros_like(close)
        for i in range(period - 1, len(close)):
            std[i] = np.std(close[i - period + 1:i + 1])

        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)

        return {
            'upper': upper,
            'middle': middle,
            'lower': lower
        }

    @staticmethod
    def ATR(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int = 14) -> np.ndarray:
        """
        平均真实波幅 (Average True Range)

        Args:
            high: 最高价数组
            low: 最低价数组
            close: 收盘价数组
            period: 周期

        Returns:
            ATR数组
        """
        if len(close) < 2:
            return np.array([np.nan] * len(close))

        # 计算真实波幅 (True Range)
        tr = np.zeros(len(close))
        tr[0] = high[0] - low[0]

        for i in range(1, len(close)):
            hl = high[i] - low[i]
            hc = abs(high[i] - close[i - 1])
            lc = abs(low[i] - close[i - 1])
            tr[i] = max(hl, hc, lc)

        # 计算ATR（使用EMA平滑）
        atr = TechnicalIndicators.EMA(tr, period)

        return atr

    @staticmethod
    def KDJ(high: np.ndarray, low: np.ndarray, close: np.ndarray,
            n: int = 9, m1: int = 3, m2: int = 3) -> Dict[str, np.ndarray]:
        """
        KDJ随机指标

        Args:
            high: 最高价数组
            low: 最低价数组
            close: 收盘价数组
            n: RSV周期
            m1: K值平滑周期
            m2: D值平滑周期

        Returns:
            {'K': K值, 'D': D值, 'J': J值}
        """
        if len(close) < n:
            nan_array = np.array([np.nan] * len(close))
            return {'K': nan_array, 'D': nan_array, 'J': nan_array}

        # 计算RSV (Raw Stochastic Value)
        rsv = np.zeros(len(close))

        for i in range(n - 1, len(close)):
            highest = np.max(high[i - n + 1:i + 1])
            lowest = np.min(low[i - n + 1:i + 1])

            if highest != lowest:
                rsv[i] = (close[i] - lowest) / (highest - lowest) * 100
            else:
                rsv[i] = 50

        # 计算K值（RSV的EMA）
        K = np.zeros(len(close))
        K[n - 1] = rsv[n - 1]

        alpha_k = 1.0 / m1
        for i in range(n, len(close)):
            K[i] = alpha_k * rsv[i] + (1 - alpha_k) * K[i - 1]

        # 计算D值（K值的EMA）
        D = np.zeros(len(close))
        D[n - 1] = K[n - 1]

        alpha_d = 1.0 / m2
        for i in range(n, len(close)):
            D[i] = alpha_d * K[i] + (1 - alpha_d) * D[i - 1]

        # 计算J值
        J = 3 * K - 2 * D

        # 填充NaN
        K[:n - 1] = np.nan
        D[:n - 1] = np.nan
        J[:n - 1] = np.nan

        return {'K': K, 'D': D, 'J': J}

    @staticmethod
    def detect_crossover(series1: np.ndarray, series2: np.ndarray) -> Tuple[bool, bool]:
        """
        检测两条线的交叉

        Args:
            series1: 数据序列1（如快线）
            series2: 数据序列2（如慢线）

        Returns:
            (golden_cross, death_cross)
            golden_cross: 金叉（快线上穿慢线）
            death_cross: 死叉（快线下穿慢线）
        """
        if len(series1) < 2 or len(series2) < 2:
            return False, False

        # 检查最后两个数据点
        prev_diff = series1[-2] - series2[-2]
        curr_diff = series1[-1] - series2[-1]

        # 金叉：从负变正
        golden_cross = prev_diff < 0 and curr_diff > 0

        # 死叉：从正变负
        death_cross = prev_diff > 0 and curr_diff < 0

        return golden_cross, death_cross

    @staticmethod
    def calculate_all_indicators(market_data: Dict[str, np.ndarray]) -> Dict[str, any]:
        """
        一次性计算所有技术指标

        Args:
            market_data: 市场数据字典
                {
                    'open': np.ndarray,
                    'high': np.ndarray,
                    'low': np.ndarray,
                    'close': np.ndarray,
                    'volume': np.ndarray
                }

        Returns:
            所有指标的字典
        """
        close = market_data['close']
        high = market_data['high']
        low = market_data['low']

        indicators = {
            # 移动平均
            'ema_5': TechnicalIndicators.EMA(close, 5),
            'ema_10': TechnicalIndicators.EMA(close, 10),
            'ema_20': TechnicalIndicators.EMA(close, 20),
            'ema_50': TechnicalIndicators.EMA(close, 50),
            'sma_20': TechnicalIndicators.SMA(close, 20),

            # MACD
            'macd': TechnicalIndicators.MACD(close),

            # RSI
            'rsi': TechnicalIndicators.RSI(close, 14),

            # 布林带
            'bollinger': TechnicalIndicators.BollingerBands(close, 20, 2.0),

            # ATR
            'atr': TechnicalIndicators.ATR(high, low, close, 14),

            # KDJ
            'kdj': TechnicalIndicators.KDJ(high, low, close, 9, 3, 3)
        }

        return indicators

    @staticmethod
    def calculate_volatility(close: np.ndarray, period: int = 20) -> Dict[str, float]:
        """
        计算波动率指标

        Args:
            close: 收盘价数组
            period: 周期

        Returns:
            {'volatility': 标准差, 'volatility_pct': 波动率百分比}
        """
        if len(close) < period:
            return {'volatility': 0, 'volatility_pct': 0}

        recent_prices = close[-period:]
        volatility = np.std(recent_prices)
        volatility_pct = volatility / np.mean(recent_prices)

        return {
            'volatility': volatility,
            'volatility_pct': volatility_pct
        }

    @staticmethod
    def detect_divergence(price: np.ndarray, indicator: np.ndarray, lookback: int = 10) -> Tuple[bool, bool]:
        """
        检测价格与指标的背离

        Args:
            price: 价格数组
            indicator: 指标数组（如RSI、MACD）
            lookback: 回看周期

        Returns:
            (bullish_divergence, bearish_divergence)
            bullish_divergence: 底背离（价格新低，指标未新低）
            bearish_divergence: 顶背离（价格新高，指标未新高）
        """
        if len(price) < lookback or len(indicator) < lookback:
            return False, False

        recent_price = price[-lookback:]
        recent_indicator = indicator[-lookback:]

        # 底背离检测
        price_min_idx = np.argmin(recent_price)
        indicator_min_idx = np.argmin(recent_indicator)
        bullish_divergence = (
            price_min_idx > lookback // 2 and  # 价格新低在后半段
            indicator_min_idx < lookback // 2 and  # 指标低点在前半段
            recent_price[-1] < recent_price[lookback // 2]  # 价格确实下跌
        )

        # 顶背离检测
        price_max_idx = np.argmax(recent_price)
        indicator_max_idx = np.argmax(recent_indicator)
        bearish_divergence = (
            price_max_idx > lookback // 2 and  # 价格新高在后半段
            indicator_max_idx < lookback // 2 and  # 指标高点在前半段
            recent_price[-1] > recent_price[lookback // 2]  # 价格确实上涨
        )

        return bullish_divergence, bearish_divergence
