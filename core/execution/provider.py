"""Sandbox execution boundary. Never execute user programs on the Django host."""
from dataclasses import asdict, dataclass
from typing import Protocol
from django.conf import settings
from core.exceptions import CodeExecutionError, ValidationError


@dataclass(frozen=True)
class ExecutionLimits:
    time_seconds: float = 2.0
    memory_mb: int = 128
    output_bytes: int = 8192
    code_bytes: int = 20000
    stdin_bytes: int = 20000
    # Optional independent CPU budget; existing positional arguments retain meaning.
    cpu_seconds: float | None = None


@dataclass(frozen=True)
class ExecutionResult:
    status: str
    stdout: str = ""
    stderr: str = ""
    elapsed_seconds: float = 0.0
    memory_kb: int | None = None
    provider: str = ""
    exit_code: int | None = None
    output_truncated: bool = False
    cpu_seconds: float | None = None
    remote_status: str | None = None
    remote_message: str | None = None
    signal: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


class CodeExecutionProvider(Protocol):
    def run(self, source: str, stdin: str = "", limits: ExecutionLimits = ExecutionLimits()) -> ExecutionResult: ...


def validate_program(source: str, stdin: str, limits: ExecutionLimits) -> None:
    if not isinstance(source, str) or not source.strip():
        raise ValidationError("请输入 Python 代码。", code="INVALID_CODE")
    if not isinstance(stdin, str):
        raise ValidationError("标准输入必须为字符串。")
    if len(source.encode()) > limits.code_bytes or len(stdin.encode()) > limits.stdin_bytes:
        raise ValidationError("代码或标准输入超过大小上限。", code="INPUT_TOO_LARGE")


def clipped(value: str | None, limit: int) -> tuple[str, bool]:
    raw = (value or "").encode("utf-8")
    return raw[:limit].decode("utf-8", errors="replace"), len(raw) > limit


def get_execution_provider() -> CodeExecutionProvider:
    provider = getattr(settings, "EXECUTION_PROVIDER", "piston")
    if provider == "piston":
        from .piston_client import PistonClient
        return PistonClient()
    if provider == "judge0":
        from .judge0_client import Judge0Client
        return Judge0Client()
    raise CodeExecutionError("管理员尚未配置有效的隔离执行服务。", code="EXECUTION_NOT_CONFIGURED")
