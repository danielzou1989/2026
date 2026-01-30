"""
限频控制器 - Token Bucket 算法实现
支持多个限频规则，预留20% buffer避免触发429错误
"""

import time
from collections import deque
from threading import Lock
from typing import Dict, Optional


class RateLimiter:
    """限频控制器，支持多个限频规则"""

    def __init__(self, limits: Dict[str, Dict[str, int]]):
        """
        初始化限频控制器

        Args:
            limits: 限频规则配置
                {
                    'place_order': {'limit': 10, 'window': 1},  # 10次/秒
                    'batch_order': {'limit': 5, 'window': 1},   # 5次/秒
                    'query': {'limit': 20, 'window': 1}         # 20次/秒
                }
        """
        self.limits = limits
        self.call_history: Dict[str, deque] = {key: deque() for key in limits.keys()}
        self.locks: Dict[str, Lock] = {key: Lock() for key in limits.keys()}

        # 应用20% buffer（降低到80%的限制）
        for key in self.limits:
            self.limits[key]['limit'] = int(self.limits[key]['limit'] * 0.8)

    def acquire(self, key: str) -> None:
        """
        获取许可，如果超限则阻塞等待

        Args:
            key: 限频规则键名
        """
        if key not in self.limits:
            return  # 无限制

        limit_config = self.limits[key]
        max_calls = limit_config['limit']
        window = limit_config['window']

        with self.locks[key]:
            now = time.time()
            history = self.call_history[key]

            # 清理过期记录
            while history and history[0] <= now - window:
                history.popleft()

            # 检查是否超限
            if len(history) >= max_calls:
                # 计算需要等待的时间
                oldest_call = history[0]
                wait_time = window - (now - oldest_call)
                if wait_time > 0:
                    time.sleep(wait_time + 0.01)  # 多等10ms确保安全
                    now = time.time()

                    # 再次清理
                    while history and history[0] <= now - window:
                        history.popleft()

            # 记录本次调用
            history.append(now)

    def get_remaining_quota(self, key: str) -> float:
        """
        查询剩余配额

        Args:
            key: 限频规则键名

        Returns:
            剩余配额数量
        """
        if key not in self.limits:
            return float('inf')

        limit_config = self.limits[key]
        max_calls = limit_config['limit']
        window = limit_config['window']

        with self.locks[key]:
            now = time.time()
            history = self.call_history[key]

            # 清理过期记录
            while history and history[0] <= now - window:
                history.popleft()

            return max_calls - len(history)

    def reset(self, key: Optional[str] = None) -> None:
        """
        重置限频历史记录

        Args:
            key: 限频规则键名，如果为None则重置所有
        """
        if key is None:
            for k in self.call_history:
                with self.locks[k]:
                    self.call_history[k].clear()
        else:
            if key in self.call_history:
                with self.locks[key]:
                    self.call_history[key].clear()


class AdaptiveRateLimiter(RateLimiter):
    """自适应限频控制器，根据API响应动态调整限频"""

    def __init__(self, limits: Dict[str, Dict[str, int]]):
        super().__init__(limits)
        self.error_count: Dict[str, int] = {key: 0 for key in limits.keys()}
        self.success_count: Dict[str, int] = {key: 0 for key in limits.keys()}

    def report_success(self, key: str) -> None:
        """报告API调用成功"""
        if key in self.success_count:
            self.success_count[key] += 1

            # 连续成功超过100次，尝试恢复部分限频
            if self.success_count[key] >= 100 and self.error_count[key] == 0:
                original_limit = int(self.limits[key]['limit'] / 0.8)  # 恢复到原始限制
                current_limit = self.limits[key]['limit']
                if current_limit < original_limit * 0.9:
                    self.limits[key]['limit'] = min(current_limit + 1, int(original_limit * 0.9))
                    print(f"[RateLimiter] {key} 限频恢复至 {self.limits[key]['limit']}")
                self.success_count[key] = 0

    def report_error(self, key: str, error_code: Optional[int] = None) -> None:
        """
        报告API调用错误

        Args:
            key: 限频规则键名
            error_code: 错误代码，429为限频错误
        """
        if key in self.error_count:
            self.error_count[key] += 1

            # 如果是429错误，立即降低限频
            if error_code == 429:
                self.limits[key]['limit'] = max(1, int(self.limits[key]['limit'] * 0.5))
                print(f"[RateLimiter] 检测到429错误，{key} 限频降低至 {self.limits[key]['limit']}")
                self.error_count[key] = 0
                self.success_count[key] = 0
