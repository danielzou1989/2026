"""
动态仓位计算器
根据账户权益、信号强度、波动率、风险偏好动态计算仓位大小
确保每笔交易风险不超过账户的2%
"""

from typing import Dict
import logging

logger = logging.getLogger(__name__)


class PositionSizer:
    """动态仓位计算器"""

    def __init__(self, config: Dict):
        """
        初始化仓位计算器

        Args:
            config: 配置参数
                {
                    'base_position_size': 0.10,   # 基础仓位10%
                    'max_position_size': 0.30,    # 最大仓位30%
                    'account_risk_pct': 0.02      # 账户风险2%
                }
        """
        self.base_position_pct = config.get('base_position_size', 0.10)
        self.max_position_pct = config.get('max_position_size', 0.30)
        self.account_risk_pct = config.get('account_risk_pct', 0.02)

    def calculate_position_size(self,
                               account_equity: float,
                               signal: Dict,
                               market_data: Dict,
                               volatility: Dict,
                               risk_multiplier: float = 1.0) -> Dict:
        """
        计算仓位大小

        Args:
            account_equity: 账户权益
            signal: 交易信号
                {
                    'direction': 'buy'/'sell',
                    'entry_price': float,
                    'stop_loss': float,
                    'strength': 'strong'/'medium'/'weak',
                    ...
                }
            market_data: 市场数据（用于计算波动率）
            volatility: 波动率指标
                {
                    'atr': float,
                    'price': float
                }
            risk_multiplier: 风险调整系数（来自风控管理器）

        Returns:
            仓位计算结果
            {
                'position_value': float,  # 仓位价值（USDT）
                'quantity': float,         # 数量
                'base_size': float,        # 基础仓位
                'adjusted_size': float,    # 调整后仓位
                'risk_amount': float,      # 风险金额
                'breakdown': Dict          # 详细分解
            }
        """
        # 1. 基础仓位
        base_size = account_equity * self.base_position_pct

        # 2. 波动率调整
        vol_mult = self._calculate_volatility_multiplier(volatility)

        # 3. 信号强度调整
        signal_mult = self._calculate_signal_multiplier(signal['strength'])

        # 4. 风控调整（来自外部）
        # risk_multiplier由风控管理器提供，用于情绪过滤、风险率调整等

        # 5. 计算调整后仓位
        adjusted_size = base_size * vol_mult * signal_mult * risk_multiplier

        # 6. 基于止损距离的风险控制
        entry_price = signal['entry_price']
        stop_loss = signal['stop_loss']
        stop_distance = abs(entry_price - stop_loss) / entry_price

        # 最大风险金额 = 账户权益 * 账户风险百分比
        max_risk_amount = account_equity * self.account_risk_pct

        # 基于止损的最大仓位 = 最大风险金额 / 止损距离
        max_risk_size = max_risk_amount / stop_distance if stop_distance > 0 else adjusted_size

        # 7. 应用限制
        # 取最小值：调整后仓位、风险仓位、最大仓位
        max_position_size = account_equity * self.max_position_pct
        final_size = min(adjusted_size, max_risk_size, max_position_size)

        # 8. 计算实际数量
        quantity = final_size / entry_price

        # 9. 计算实际风险
        risk_amount = final_size * stop_distance

        # 构建详细分解
        breakdown = {
            'base_multiplier': 1.0,
            'volatility_multiplier': vol_mult,
            'signal_multiplier': signal_mult,
            'risk_multiplier': risk_multiplier,
            'combined_multiplier': vol_mult * signal_mult * risk_multiplier,
            'stop_distance_pct': stop_distance,
            'limits_applied': {
                'max_position_limit': max_position_size,
                'max_risk_limit': max_risk_size,
                'adjusted_size': adjusted_size,
                'final_size': final_size,
                'limiting_factor': self._get_limiting_factor(
                    adjusted_size, max_risk_size, max_position_size, final_size
                )
            }
        }

        logger.info(
            f"Position sizing: {final_size:.2f} USDT ({final_size/account_equity:.1%} of equity), "
            f"Qty: {quantity:.4f}, Risk: {risk_amount:.2f} USDT ({risk_amount/account_equity:.2%})"
        )

        return {
            'position_value': final_size,
            'quantity': quantity,
            'base_size': base_size,
            'adjusted_size': adjusted_size,
            'risk_amount': risk_amount,
            'breakdown': breakdown
        }

    def _calculate_volatility_multiplier(self, volatility: Dict) -> float:
        """
        计算波动率调整系数

        Args:
            volatility: 波动率数据

        Returns:
            波动率系数（0.5-1.5）
        """
        atr = volatility.get('atr', 0)
        price = volatility.get('price', 1)

        # 标准化ATR（相对于价格的百分比）
        atr_normalized = atr / price if price > 0 else 0

        # 低波动率 → 增加仓位
        if atr_normalized < 0.01:  # ATR < 1%
            return 1.5
        # 中等波动率 → 正常仓位
        elif atr_normalized < 0.03:  # ATR < 3%
            return 1.0
        # 高波动率 → 减少仓位
        else:  # ATR >= 3%
            return 0.5

    def _calculate_signal_multiplier(self, strength: str) -> float:
        """
        计算信号强度调整系数

        Args:
            strength: 信号强度（'strong'/'medium'/'weak'）

        Returns:
            信号系数（0.7-1.2）
        """
        multipliers = {
            'strong': 1.2,
            'medium': 1.0,
            'weak': 0.7
        }

        return multipliers.get(strength, 1.0)

    def _get_limiting_factor(self, adjusted_size: float, max_risk_size: float,
                            max_position_size: float, final_size: float) -> str:
        """
        确定限制因素

        Args:
            adjusted_size: 调整后仓位
            max_risk_size: 最大风险仓位
            max_position_size: 最大仓位限制
            final_size: 最终仓位

        Returns:
            限制因素描述
        """
        if final_size == adjusted_size:
            return 'none'
        elif final_size == max_risk_size:
            return 'risk_limit'
        elif final_size == max_position_size:
            return 'max_position_limit'
        else:
            return 'unknown'

    def validate_position(self, position_value: float, account_equity: float) -> Dict:
        """
        验证仓位大小是否合理

        Args:
            position_value: 仓位价值
            account_equity: 账户权益

        Returns:
            验证结果
        """
        position_pct = position_value / account_equity if account_equity > 0 else 0

        if position_pct > self.max_position_pct:
            return {
                'valid': False,
                'reason': f"Position size ({position_pct:.1%}) exceeds maximum ({self.max_position_pct:.1%})"
            }

        if position_pct < 0.01:  # 仓位太小（<1%）
            return {
                'valid': False,
                'reason': f"Position size ({position_pct:.1%}) too small (minimum 1%)"
            }

        return {
            'valid': True,
            'reason': 'Position size valid'
        }
