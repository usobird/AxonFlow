"""Token 用量追踪"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime

import structlog

logger = structlog.get_logger()


@dataclass
class TokenUsageRecord:
    """单次 LLM 调用的 Token 记录"""

    model: str
    input_tokens: int
    output_tokens: int
    timestamp: str = field(
        default_factory=lambda: datetime.now(UTC).isoformat()
    )

    @property
    def total_tokens(self) -> int:
        return self.input_tokens + self.output_tokens


class TokenTracker:
    """全局 Token 用量追踪器"""

    def __init__(self, budget: int | None = None) -> None:
        self._budget = budget
        self._records: list[TokenUsageRecord] = []
        self._total_input = 0
        self._total_output = 0

    @property
    def total_tokens(self) -> int:
        return self._total_input + self._total_output

    @property
    def total_input_tokens(self) -> int:
        return self._total_input

    @property
    def total_output_tokens(self) -> int:
        return self._total_output

    def record(self, model: str, input_tokens: int, output_tokens: int) -> None:
        """记录一次 LLM 调用的 Token 用量"""
        usage = TokenUsageRecord(
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )
        self._records.append(usage)
        self._total_input += input_tokens
        self._total_output += output_tokens

        logger.info(
            "token_usage",
            model=model,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total=self.total_tokens,
            budget=self._budget,
        )

    def is_budget_exceeded(self) -> bool:
        """是否超出预算"""
        if self._budget is None:
            return False
        return self.total_tokens >= self._budget

    def remaining_budget(self) -> int | None:
        """剩余预算"""
        if self._budget is None:
            return None
        return max(0, self._budget - self.total_tokens)

    def summary(self) -> dict:
        """生成用量摘要"""
        return {
            "total_tokens": self.total_tokens,
            "total_input_tokens": self._total_input,
            "total_output_tokens": self._total_output,
            "total_calls": len(self._records),
            "budget": self._budget,
            "remaining": self.remaining_budget(),
        }
