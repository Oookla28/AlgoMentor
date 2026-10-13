from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class TokenUsage:
    input_tokens: int | None = None
    output_tokens: int | None = None
    total_tokens: int | None = None


@dataclass(frozen=True)
class LLMResult:
    text: str
    usage: TokenUsage
    model: str
    tool_calls: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    reasoning_content: str = field(default='', repr=False)
    finish_reason: str = ''


class LLMProvider(Protocol):
    def complete(self, messages: list[dict], tier: str | None = None, **kwargs) -> LLMResult: ...
