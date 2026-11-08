"""Declarative tool contract used by the explicit agent state machine."""

from dataclasses import asdict, dataclass, field


@dataclass(frozen=True)
class ToolSpec:
    tool_id: str
    version: str
    name: str
    description: str
    input_schema: dict = field(default_factory=dict)
    output_schema: dict = field(default_factory=dict)
    permission: str = 'read'
    side_effects: str = 'none'
    timeout_seconds: float = 5.0
    budget_cost: int = 1
    idempotent: bool = True
    evidence_policy: str = 'evidence_ids_required'
    enabled: bool = True

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class ToolResult:
    ok: bool
    tool_id: str
    output: dict = field(default_factory=dict)
    evidence_ids: tuple[str, ...] = ()
    latency_ms: int = 0
    failure_code: str = ''
    message: str = ''

    def to_dict(self) -> dict:
        return {
            'ok': self.ok,
            'tool_id': self.tool_id,
            'output': self.output,
            'evidence_ids': list(self.evidence_ids),
            'latency_ms': self.latency_ms,
            'failure_code': self.failure_code,
            'message': self.message,
        }
