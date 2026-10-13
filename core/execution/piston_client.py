import time
from django.conf import settings
from core.exceptions import CodeExecutionError
from .provider import ExecutionLimits, ExecutionResult, clipped, validate_program
from .http_client import request_json, validate_url


class PistonClient:
    def __init__(self, base_url: str | None = None, token: str | None = None):
        self.base_url = validate_url(base_url or getattr(settings, "PISTON_BASE_URL", "https://emkc.org/api/v2/piston"))
        self.token = token if token is not None else getattr(settings, "PISTON_API_TOKEN", "")

    @property
    def headers(self) -> dict:
        return {"Authorization": f"Bearer {self.token}"} if self.token else {}

    def probe(self) -> list:
        return request_json("GET", f"{self.base_url}/runtimes", headers=self.headers)

    def run(self, source: str, stdin: str = "", limits: ExecutionLimits = ExecutionLimits()) -> ExecutionResult:
        validate_program(source, stdin, limits)
        started = time.monotonic()
        cpu_limit = limits.cpu_seconds if limits.cpu_seconds is not None else limits.time_seconds
        payload = {
            "language": "python", "version": getattr(settings, "PISTON_PYTHON_VERSION", "3.x"),
            "files": [{"name": "main.py", "content": source}], "stdin": stdin,
            "compile_timeout": 3000, "run_timeout": int(limits.time_seconds * 1000),
            "compile_cpu_time": 3000, "run_cpu_time": int(cpu_limit * 1000),
            "compile_memory_limit": limits.memory_mb * 1024 * 1024,
            "run_memory_limit": limits.memory_mb * 1024 * 1024,
        }
        data = request_json("POST", f"{self.base_url}/execute", payload=payload, headers=self.headers)
        if not isinstance(data, dict):
            raise CodeExecutionError("执行服务返回格式无效。", code="EXECUTION_INVALID_RESPONSE")
        stage = data.get("compile") if data.get("compile", {}).get("code", 0) != 0 else data.get("run")
        if not isinstance(stage, dict):
            raise CodeExecutionError("执行服务未返回运行结果。", code="EXECUTION_INVALID_RESPONSE")
        stdout, out_cut = clipped(stage.get("stdout"), limits.output_bytes)
        stderr, err_cut = clipped(stage.get("stderr"), limits.output_bytes)
        remote_status = stage.get("status")
        if remote_status == "XX":
            raise CodeExecutionError("隔离执行服务内部错误；本次不计入成绩。", code="EXECUTION_INTERNAL_ERROR")
        if remote_status == "TO":
            status = "TIME_LIMIT_EXCEEDED"
        elif "SyntaxError" in stderr or "IndentationError" in stderr or "TabError" in stderr:
            status = "SYNTAX_ERROR"
        elif "MemoryError" in stderr:
            status = "MEMORY_LIMIT_EXCEEDED"
        elif stage.get("code") != 0 or stage.get("signal") or remote_status in ("RE", "SG", "OL", "EL") or out_cut or err_cut:
            status = "RUNTIME_ERROR"
        else:
            status = "ACCEPTED"
        return ExecutionResult(
            status, stdout, stderr,
            (stage.get("wall_time") or (time.monotonic() - started) * 1000) / 1000,
            stage.get("memory", 0) // 1024 if stage.get("memory") is not None else None,
            "piston", stage.get("code"), out_cut or err_cut,
            cpu_seconds=stage["cpu_time"] / 1000 if isinstance(stage.get("cpu_time"), (int, float)) else None,
            remote_status=remote_status, remote_message=stage.get("message"),
            signal=stage.get("signal"),
        )
