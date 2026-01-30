"""
止损管理器
管理固定止损和移动止损（Trailing Stop）
盈利>1%后激活移动止损，跟踪距离1%
"""

from typing import Dict, Optional
import logging

logger = logging.getLogger(__name__)


class StopLossManager:
    """止损管理器"""

    def __init__(self, config: Dict):
        """
        初始化止损管理器

        Args:
            config: 止损配置
                {
                    'default_pct': 0.02,             # 默认止损2%
                    'breakout_pct': 0.03,            # 突破策略止损3%
                    'trailing_enabled': True,        # 启用移动止损
                    'trailing_activation': 0.01,     # 盈利1%后激活
                    'trailing_distance': 0.01        # 跟踪距离1%
                }
        """
        self.default_stop_pct = config.get('default_pct', 0.02)
        self.breakout_stop_pct = config.get('breakout_pct', 0.03)
        self.trailing_enabled = config.get('trailing_enabled', True)
        self.trailing_activation_pct = config.get('trailing_activation', 0.01)
        self.trailing_distance_pct = config.get('trailing_distance', 0.01)

        # 持仓止损跟踪
        self.position_stops: Dict[str, Dict] = {}

    def initialize_stop_loss(self, symbol: str, position: Dict, strategy: str = 'default') -> Dict:
        """
        初始化止损

        Args:
            symbol: 交易对符号
            position: 持仓信息
                {
                    'side': 'buy'/'sell',
                    'entry_price': float,
                    'qty': float,
                    ...
                }
            strategy: 策略名称（用于确定止损百分比）

        Returns:
            止损信息
            {
                'fixed_stop': float,           # 固定止损价
                'trailing_stop': float,        # 移动止损价
                'trailing_activated': bool,    # 移动止损是否激活
                'highest_price': float,        # 多头最高价
                'lowest_price': float          # 空头最低价
            }
        """
        side = position['side']
        entry_price = position['entry_price']

        # 确定止损百分比
        if strategy == 'Breakout':
            stop_pct = self.breakout_stop_pct
        else:
            stop_pct = self.default_stop_pct

        # 计算固定止损价
        if side == 'buy':
            fixed_stop = entry_price * (1 - stop_pct)
        else:  # sell
            fixed_stop = entry_price * (1 + stop_pct)

        # 初始化止损跟踪
        stop_info = {
            'fixed_stop': fixed_stop,
            'trailing_stop': fixed_stop,  # 初始等于固定止损
            'trailing_activated': False,
            'highest_price': entry_price,  # 多头用
            'lowest_price': entry_price,   # 空头用
            'entry_price': entry_price,
            'side': side,
            'stop_pct': stop_pct
        }

        self.position_stops[symbol] = stop_info

        logger.info(
            f"Initialized stop loss for {symbol}: "
            f"Entry={entry_price:.2f}, Stop={fixed_stop:.2f} ({stop_pct:.1%})"
        )

        return stop_info

    def update_stop_loss(self, symbol: str, current_price: float) -> Dict:
        """
        更新止损（每次价格更新时调用）

        Args:
            symbol: 交易对符号
            current_price: 当前价格

        Returns:
            更新后的止损信息 + 是否触发止损
            {
                'stop_triggered': bool,
                'stop_price': float,
                'stop_type': 'fixed'/'trailing',
                'stop_info': Dict
            }
        """
        if symbol not in self.position_stops:
            logger.warning(f"No stop loss tracking for {symbol}")
            return {'stop_triggered': False}

        stop_info = self.position_stops[symbol]
        side = stop_info['side']
        entry_price = stop_info['entry_price']

        # 计算盈亏百分比
        if side == 'buy':
            pnl_pct = (current_price - entry_price) / entry_price
        else:  # sell
            pnl_pct = (entry_price - current_price) / entry_price

        # ========== 1. 检查是否激活移动止损 ==========
        if self.trailing_enabled and not stop_info['trailing_activated']:
            if pnl_pct >= self.trailing_activation_pct:
                stop_info['trailing_activated'] = True
                logger.info(
                    f"Trailing stop activated for {symbol} at {current_price:.2f} "
                    f"(PnL: {pnl_pct:.2%})"
                )

        # ========== 2. 更新移动止损 ==========
        if stop_info['trailing_activated']:
            if side == 'buy':
                # 多头：更新最高价
                if current_price > stop_info['highest_price']:
                    stop_info['highest_price'] = current_price
                    # 更新移动止损 = 最高价 - 跟踪距离
                    stop_info['trailing_stop'] = current_price * (1 - self.trailing_distance_pct)
                    logger.debug(
                        f"Updated trailing stop for {symbol}: "
                        f"High={current_price:.2f}, Stop={stop_info['trailing_stop']:.2f}"
                    )

            else:  # sell
                # 空头：更新最低价
                if current_price < stop_info['lowest_price']:
                    stop_info['lowest_price'] = current_price
                    # 更新移动止损 = 最低价 + 跟踪距离
                    stop_info['trailing_stop'] = current_price * (1 + self.trailing_distance_pct)
                    logger.debug(
                        f"Updated trailing stop for {symbol}: "
                        f"Low={current_price:.2f}, Stop={stop_info['trailing_stop']:.2f}"
                    )

        # ========== 3. 检查是否触发止损 ==========
        if side == 'buy':
            # 多头：价格跌破止损价
            if stop_info['trailing_activated']:
                if current_price <= stop_info['trailing_stop']:
                    return {
                        'stop_triggered': True,
                        'stop_price': stop_info['trailing_stop'],
                        'stop_type': 'trailing',
                        'stop_info': stop_info,
                        'current_price': current_price,
                        'pnl_pct': pnl_pct
                    }
            else:
                if current_price <= stop_info['fixed_stop']:
                    return {
                        'stop_triggered': True,
                        'stop_price': stop_info['fixed_stop'],
                        'stop_type': 'fixed',
                        'stop_info': stop_info,
                        'current_price': current_price,
                        'pnl_pct': pnl_pct
                    }

        else:  # sell
            # 空头：价格涨破止损价
            if stop_info['trailing_activated']:
                if current_price >= stop_info['trailing_stop']:
                    return {
                        'stop_triggered': True,
                        'stop_price': stop_info['trailing_stop'],
                        'stop_type': 'trailing',
                        'stop_info': stop_info,
                        'current_price': current_price,
                        'pnl_pct': pnl_pct
                    }
            else:
                if current_price >= stop_info['fixed_stop']:
                    return {
                        'stop_triggered': True,
                        'stop_price': stop_info['fixed_stop'],
                        'stop_type': 'fixed',
                        'stop_info': stop_info,
                        'current_price': current_price,
                        'pnl_pct': pnl_pct
                    }

        # 未触发止损
        return {
            'stop_triggered': False,
            'stop_info': stop_info,
            'current_price': current_price,
            'pnl_pct': pnl_pct
        }

    def remove_stop_loss(self, symbol: str):
        """移除止损跟踪（平仓后调用）"""
        if symbol in self.position_stops:
            del self.position_stops[symbol]
            logger.info(f"Removed stop loss tracking for {symbol}")

    def get_stop_loss(self, symbol: str) -> Optional[Dict]:
        """获取当前止损信息"""
        return self.position_stops.get(symbol)

    def get_all_stops(self) -> Dict[str, Dict]:
        """获取所有止损信息"""
        return self.position_stops.copy()
