"""
风控管理器 - 核心风控模块
集成情绪过滤、仓位控制、爆仓监控、最大回撤限制
调用 crypto-news-sentiment-filter 和 position-analysis
"""

from typing import Dict, List, Optional
import time
import logging

logger = logging.getLogger(__name__)


class RiskManager:
    """风控管理器"""

    def __init__(self, config: Dict):
        """
        初始化风控管理器

        Args:
            config: 风控配置
                {
                    'sentiment_filter': {
                        'enabled': True,
                        'veto_threshold': -0.4,  # 否决阈值
                        'critical_threshold': -0.6  # 严重负面阈值
                    },
                    'position_sizing': {
                        'base_position_size': 0.10,  # 基础仓位10%
                        'max_position_size': 0.30,   # 最大仓位30%
                        'account_risk_pct': 0.02     # 账户风险2%
                    },
                    'liquidation_monitor': {
                        'warning_threshold': 0.20,   # 风险率20%警告
                        'critical_threshold': 0.50   # 风险率50%危险
                    },
                    'drawdown': {
                        'max_drawdown': 0.15,        # 最大回撤15%
                        'pause_threshold': 0.10       # 回撤10%暂停
                    }
                }
        """
        self.config = config
        self.sentiment_enabled = config.get('sentiment_filter', {}).get('enabled', True)
        self.veto_threshold = config.get('sentiment_filter', {}).get('veto_threshold', -0.4)
        self.critical_threshold = config.get('sentiment_filter', {}).get('critical_threshold', -0.6)

        # 风控状态
        self.is_paused = False
        self.pause_reason = None
        self.daily_loss = 0.0
        self.max_equity = 0.0

        # 缓存
        self.last_sentiment_check = 0
        self.cached_sentiment = None

    def validate_signal(self, signal: Dict, account_info: Dict,
                       positions: Optional[List[Dict]] = None,
                       sentiment_data: Optional[Dict] = None) -> Dict:
        """
        验证交易信号是否符合风控要求

        Args:
            signal: 交易信号
            account_info: 账户信息
            positions: 当前持仓
            sentiment_data: 情绪数据（可选，如果不提供则会调用情绪过滤器）

        Returns:
            风控结果
            {
                'approved': True/False,
                'reason': str,
                'position_size_multiplier': float,  # 仓位调整系数
                'warnings': List[str]
            }
        """
        warnings = []
        position_multiplier = 1.0

        # 检查是否暂停交易
        if self.is_paused:
            return {
                'approved': False,
                'reason': f"Trading paused: {self.pause_reason}",
                'position_size_multiplier': 0.0,
                'warnings': warnings
            }

        # ========== 1. 情绪过滤 ==========
        if self.sentiment_enabled and signal['direction'] == 'buy':
            sentiment_result = self._check_sentiment(sentiment_data)

            if not sentiment_result['approved']:
                return {
                    'approved': False,
                    'reason': sentiment_result['reason'],
                    'position_size_multiplier': 0.0,
                    'warnings': sentiment_result['warnings']
                }

            # 根据情绪调整仓位
            if sentiment_result['sentiment_score'] < -0.2:
                position_multiplier *= 0.7
                warnings.append(f"Sentiment negative ({sentiment_result['sentiment_score']:.2f}), reduce position to 70%")

        # ========== 2. 爆仓风险监控 ==========
        liquidation_result = self._check_liquidation_risk(account_info, positions)

        if not liquidation_result['approved']:
            return {
                'approved': False,
                'reason': liquidation_result['reason'],
                'position_size_multiplier': 0.0,
                'warnings': liquidation_result['warnings']
            }

        warnings.extend(liquidation_result['warnings'])

        # 根据风险率调整仓位
        risk_rate = liquidation_result.get('risk_rate', 0)
        if risk_rate > 0.10:  # 风险率>10%
            position_multiplier *= 0.5
            warnings.append(f"High risk rate ({risk_rate:.1%}), reduce position to 50%")

        # ========== 3. 最大回撤检查 ==========
        drawdown_result = self._check_drawdown(account_info)

        if not drawdown_result['approved']:
            return {
                'approved': False,
                'reason': drawdown_result['reason'],
                'position_size_multiplier': 0.0,
                'warnings': drawdown_result['warnings']
            }

        warnings.extend(drawdown_result['warnings'])

        # ========== 4. 账户资金充足性 ==========
        account_result = self._check_account_balance(account_info)

        if not account_result['approved']:
            return {
                'approved': False,
                'reason': account_result['reason'],
                'position_size_multiplier': 0.0,
                'warnings': warnings
            }

        # 通过所有风控检查
        return {
            'approved': True,
            'reason': 'All risk checks passed',
            'position_size_multiplier': position_multiplier,
            'warnings': warnings
        }

    def _check_sentiment(self, sentiment_data: Optional[Dict] = None) -> Dict:
        """
        检查市场情绪

        Args:
            sentiment_data: 情绪数据（如果为None，则使用缓存或调用API）

        Returns:
            情绪检查结果
        """
        # 如果提供了情绪数据，直接使用
        if sentiment_data:
            sentiment_score = sentiment_data.get('score', 0)
            fud_ratio = sentiment_data.get('fud_ratio', 0)
        # 否则使用缓存（5分钟内有效）
        elif self.cached_sentiment and (time.time() - self.last_sentiment_check) < 300:
            sentiment_score = self.cached_sentiment.get('score', 0)
            fud_ratio = self.cached_sentiment.get('fud_ratio', 0)
        else:
            # 注意：实际运行时需要调用 crypto-news-sentiment-filter skill
            # 这里提供占位逻辑
            logger.warning("No sentiment data provided, using default")
            sentiment_score = 0.0
            fud_ratio = 0.0

            # 缓存结果
            self.cached_sentiment = {'score': sentiment_score, 'fud_ratio': fud_ratio}
            self.last_sentiment_check = time.time()

        warnings = []

        # 严重负面情绪，直接否决
        if sentiment_score <= self.critical_threshold:
            return {
                'approved': False,
                'reason': f"Critical negative sentiment: {sentiment_score:.2f}",
                'sentiment_score': sentiment_score,
                'warnings': [f"FUD ratio: {fud_ratio:.1%}"]
            }

        # 负面情绪，否决买入
        if sentiment_score <= self.veto_threshold:
            return {
                'approved': False,
                'reason': f"Negative sentiment veto: {sentiment_score:.2f}",
                'sentiment_score': sentiment_score,
                'warnings': [f"FUD ratio: {fud_ratio:.1%}"]
            }

        # FUD占比过高，警告
        if fud_ratio > 0.30:
            warnings.append(f"High FUD ratio: {fud_ratio:.1%}")

        return {
            'approved': True,
            'reason': 'Sentiment check passed',
            'sentiment_score': sentiment_score,
            'warnings': warnings
        }

    def _check_liquidation_risk(self, account_info: Dict,
                                positions: Optional[List[Dict]]) -> Dict:
        """
        检查爆仓风险（集成 position-analysis）

        Args:
            account_info: 账户信息
            positions: 持仓列表

        Returns:
            爆仓风险检查结果
        """
        warnings = []

        # 如果没有持仓，风险为0
        if not positions or len(positions) == 0:
            return {
                'approved': True,
                'reason': 'No positions',
                'risk_rate': 0.0,
                'warnings': []
            }

        # 计算风险率（简化版，实际应调用 position-analysis）
        # 风险率 = 已用保证金 / 账户权益
        total_equity = account_info.get('total', 0)
        used_margin = account_info.get('used', 0)

        if total_equity > 0:
            risk_rate = used_margin / total_equity
        else:
            risk_rate = 0.0

        # 危险阈值（50%）
        if risk_rate >= self.config.get('liquidation_monitor', {}).get('critical_threshold', 0.50):
            return {
                'approved': False,
                'reason': f"Critical liquidation risk: {risk_rate:.1%}",
                'risk_rate': risk_rate,
                'warnings': ['Immediate action required!']
            }

        # 警告阈值（20%）
        if risk_rate >= self.config.get('liquidation_monitor', {}).get('warning_threshold', 0.20):
            warnings.append(f"Warning: risk rate {risk_rate:.1%}")

        return {
            'approved': True,
            'reason': 'Liquidation risk acceptable',
            'risk_rate': risk_rate,
            'warnings': warnings
        }

    def _check_drawdown(self, account_info: Dict) -> Dict:
        """
        检查最大回撤

        Args:
            account_info: 账户信息

        Returns:
            回撤检查结果
        """
        warnings = []

        total_equity = account_info.get('total', 0)

        # 更新最大权益
        if total_equity > self.max_equity:
            self.max_equity = total_equity

        # 计算回撤
        if self.max_equity > 0:
            drawdown = (self.max_equity - total_equity) / self.max_equity
        else:
            drawdown = 0.0

        max_drawdown = self.config.get('drawdown', {}).get('max_drawdown', 0.15)
        pause_threshold = self.config.get('drawdown', {}).get('pause_threshold', 0.10)

        # 达到最大回撤，暂停交易
        if drawdown >= max_drawdown:
            self.is_paused = True
            self.pause_reason = f"Max drawdown reached: {drawdown:.1%}"
            return {
                'approved': False,
                'reason': self.pause_reason,
                'drawdown': drawdown,
                'warnings': ['Trading paused']
            }

        # 达到暂停阈值，发出警告
        if drawdown >= pause_threshold:
            warnings.append(f"High drawdown: {drawdown:.1%}")

        return {
            'approved': True,
            'reason': 'Drawdown acceptable',
            'drawdown': drawdown,
            'warnings': warnings
        }

    def _check_account_balance(self, account_info: Dict) -> Dict:
        """
        检查账户资金是否充足

        Args:
            account_info: 账户信息

        Returns:
            账户资金检查结果
        """
        available = account_info.get('available', 0)
        total = account_info.get('total', 0)

        # 可用资金低于总权益的10%
        if total > 0 and available < total * 0.10:
            return {
                'approved': False,
                'reason': f"Insufficient available balance: {available:.2f} ({available/total:.1%})"
            }

        # 可用资金低于总权益的20%，警告
        if total > 0 and available < total * 0.20:
            logger.warning(f"Low available balance: {available:.2f} ({available/total:.1%})")

        return {
            'approved': True,
            'reason': 'Balance sufficient'
        }

    def pause_trading(self, reason: str):
        """暂停交易"""
        self.is_paused = True
        self.pause_reason = reason
        logger.critical(f"Trading paused: {reason}")

    def resume_trading(self):
        """恢复交易"""
        self.is_paused = False
        self.pause_reason = None
        logger.info("Trading resumed")

    def reset_max_equity(self, equity: float):
        """重置最大权益（例如每日重置）"""
        self.max_equity = equity
        logger.info(f"Max equity reset to {equity}")
