"""
止盈管理器
管理多目标止盈、分批清仓及比例控制，配合风控配置实现动态止盈追踪。
"""

import logging
import time
from typing import Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)


class TakeProfitManager:
    """止盈管理器"""

    def __init__(self, config: Dict):
        """
        初始化止盈管理器

        Args:
            config: 止盈配置
                {
                    'levels': [0.03, 0.05, 0.08],
                    'ratios': [0.40, 0.40, 0.20]
                }
        """
        raw_levels = self._sanitize_levels(config.get('levels', [0.03, 0.05, 0.08]))
        if not raw_levels:
            raw_levels = [0.03, 0.05, 0.08]

        self.default_levels = raw_levels

        raw_ratios = [float(r) for r in (config.get('ratios') or []) if isinstance(r, (int, float)) and r >= 0]
        self.default_ratios = self._match_length_and_normalize(raw_ratios, len(self.default_levels))

        self.targets: Dict[str, Dict] = {}

    def initialize_take_profit(self,
                               symbol: str,
                               position: Dict,
                               take_profit_pcts: Optional[List[float]] = None,
                               ratios: Optional[List[float]] = None) -> Dict:
        """
        为新持仓初始化止盈目标

        Args:
            symbol: 交易对符号
            position: 持仓信息，至少应包含：
                {
                    'side': 'buy'/'sell',
                    'entry_price': float,
                    'qty': float,
                    ...
                }
            take_profit_pcts: 自定义止盈百分比
            ratios: 每个止盈层级的比例

        Returns:
            记录止盈目标的字典
        """
        direction = self._normalize_direction(position)
        entry_price = float(position['entry_price'])
        total_qty = float(position.get('qty') or position.get('quantity') or 0.0)
        if total_qty <= 0:
            logger.warning(
                f"{symbol}: 初始化止盈时检测到持仓数量为0，将按1处理"
            )
            total_qty = 1.0

        levels, normalized_ratios = self._prepare_levels_and_ratios(take_profit_pcts, ratios)
        level_infos = []

        for index, (pct, ratio) in enumerate(zip(levels, normalized_ratios)):
            target_price = self._calculate_target_price(entry_price, pct, direction)
            level_infos.append({
                'index': index,
                'pct': pct,
                'price': target_price,
                'ratio': ratio,
                'target_qty': total_qty * ratio,
                'triggered': False,
                'trigger_ts': None,
                'filled_qty': 0.0
            })

        tp_info = {
            'direction': direction,
            'entry_price': entry_price,
            'total_qty': total_qty,
            'remaining_qty': total_qty,
            'levels': level_infos,
            'next_index': 0,
            'created_at': int(time.time() * 1000),
            'completed': False
        }

        self.targets[symbol] = tp_info

        level_summary = ", ".join(
            f"{level['price']:.4f}({level['ratio']:.0%})" for level in level_infos
        )

        logger.info(
            f"Initialized take profit for {symbol}: "
            f"entry={entry_price:.4f}, levels=[{level_summary}]"
        )

        return tp_info

    def update_take_profit(self, symbol: str, current_price: float) -> Dict:
        """
        根据最新价格检查止盈层级是否触发

        Args:
            symbol: 交易对
            current_price: 当前价格

        Returns:
            {
                'symbol': symbol,
                'triggered': bool,
                'triggered_levels': List[Dict],
                'current_price': float,
                'remaining_qty': float,
                'completed': bool,
                'next_level_price': Optional[float],
                'take_profit_info': Dict
            }
        """
        current_price = float(current_price)

        if symbol not in self.targets:
            logger.warning(f"No take profit tracking for {symbol}")
            return {
                'symbol': symbol,
                'triggered': False,
                'triggered_levels': [],
                'current_price': current_price,
                'remaining_qty': 0.0,
                'completed': False,
                'next_level_price': None,
                'take_profit_info': {}
            }

        info = self.targets[symbol]
        direction = info['direction']
        triggered_levels = []

        while info['next_index'] < len(info['levels']):
            level = info['levels'][info['next_index']]
            if not self._is_level_hit(direction, current_price, level['price']):
                break

            target_qty = min(level['target_qty'], info['remaining_qty'])
            level['filled_qty'] = target_qty
            level['triggered'] = True
            level['trigger_ts'] = int(time.time() * 1000)
            info['remaining_qty'] = max(info['remaining_qty'] - target_qty, 0.0)

            triggered_levels.append({
                'index': level['index'],
                'price': level['price'],
                'ratio': level['ratio'],
                'qty': target_qty,
                'pct': level['pct']
            })

            logger.info(
                f"Take profit level {level['index'] + 1} triggered for {symbol}: "
                f"price={level['price']:.4f}, qty={target_qty:.4f} ({level['ratio']:.0%})"
            )

            info['next_index'] += 1
            if info['remaining_qty'] <= 0:
                break

        completed = info['next_index'] >= len(info['levels']) or info['remaining_qty'] <= 0
        info['completed'] = completed
        next_level_price = None
        if info['next_index'] < len(info['levels']):
            next_level_price = info['levels'][info['next_index']]['price']

        return {
            'symbol': symbol,
            'triggered': bool(triggered_levels),
            'triggered_levels': triggered_levels,
            'current_price': current_price,
            'remaining_qty': info['remaining_qty'],
            'completed': completed,
            'next_level_price': next_level_price,
            'take_profit_info': info
        }

    def remove_take_profit(self, symbol: str):
        """移除止盈追踪"""
        if symbol in self.targets:
            del self.targets[symbol]
            logger.info(f"Removed take profit tracking for {symbol}")

    def get_take_profit(self, symbol: str) -> Optional[Dict]:
        """返回当前止盈信息"""
        return self.targets.get(symbol)

    def get_all_take_profits(self) -> Dict[str, Dict]:
        """返回所有正在追踪的止盈"""
        return self.targets.copy()

    def _normalize_direction(self, position: Dict) -> str:
        side = (position.get('side') or position.get('direction') or '').lower()
        return 'sell' if side in ('sell', 'short') else 'buy'

    def _is_level_hit(self, direction: str, current_price: float, target_price: float) -> bool:
        if direction == 'buy':
            return current_price >= target_price
        return current_price <= target_price

    def _calculate_target_price(self, entry_price: float, pct: float, direction: str) -> float:
        if direction == 'buy':
            return entry_price * (1 + pct)
        return entry_price * (1 - pct)

    def _sanitize_levels(self, levels: Optional[List[float]]) -> List[float]:
        if not levels:
            return []

        sanitized = []
        for value in levels:
            if isinstance(value, (int, float)):
                pct = float(value)
                if pct > 0:
                    sanitized.append(pct)

        return sanitized

    def _match_length_and_normalize(self, ratios: List[float], length: int) -> List[float]:
        if length <= 0:
            return []

        normalized = list(ratios)
        if not normalized:
            normalized = [1.0] * length
        elif len(normalized) < length:
            pad_value = normalized[-1]
            normalized.extend([pad_value] * (length - len(normalized)))
        elif len(normalized) > length:
            normalized = normalized[:length]

        total = sum(normalized)
        if total == 0:
            return [1.0 / length] * length

        return [value / total for value in normalized]

    def _prepare_levels_and_ratios(self,
                                   requested_levels: Optional[List[float]],
                                   requested_ratios: Optional[List[float]]) -> Tuple[List[float], List[float]]:
        levels = self._sanitize_levels(requested_levels) if requested_levels is not None else []
        if not levels:
            levels = list(self.default_levels)

        ratio_candidates = []
        if requested_ratios:
            ratio_candidates = [float(r) for r in requested_ratios if isinstance(r, (int, float)) and r >= 0]

        if not ratio_candidates:
            ratio_candidates = list(self.default_ratios)

        ratios = self._match_length_and_normalize(ratio_candidates, len(levels))
        return levels, ratios

