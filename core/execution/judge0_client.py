"""Judge0 CE adapter, async submission with a bounded polling deadline."""
import time
from django.conf import settings
from core.exceptions import CodeExecutionError
from .http_client import request_json, validate_url
from .provider import ExecutionResult, ExecutionLimits, validate_program, clipped


class Judge0Client:
    def __init__(self, base_url=None, token=None):
        self.base_url = validate_url(base_url or getattr(settings, "JUDGE0_BASE_URL", "https://ce.judge0.com"))
        self.token = token if token is not None else getattr(settings, "JUDGE0_API_TOKEN", "")
        self.headers = {getattr(settings, "JUDGE0_AUTH_HEADER", "X-Auth-Token"): self.token} if self.token else {}
        rapid_key = getattr(settings, "JUDGE0_RAPIDAPI_KEY", "")
        if rapid_key:
            self.headers.update({"X-RapidAPI-Key": rapid_key, "X-RapidAPI-Host": getattr(settings, "JUDGE0_RAPIDAPI_HOST", "judge0-ce.p.rapidapi.com")})

    def probe(self):
        return request_json("GET", f"{self.base_url}/languages", headers=self.headers)

    def run(self, source, stdin="", limits=ExecutionLimits()):
        validate_program(source, stdin, limits)
        payload = {"language_id": getattr(settings, "JUDGE0_PYTHON_LANGUAGE_ID", 71), "source_code": source,
                   "stdin": stdin, "cpu_time_limit": limits.time_seconds,
                   "wall_time_limit": limits.time_seconds + 2, "memory_limit": limits.memory_mb * 1024,
                   "max_file_size": max(1, limits.output_bytes // 1024),
                   "max_processes_and_or_threads": 8, "enable_network": False}
        data = request_json("POST", f"{self.base_url}/submissions?base64_encoded=false&wait=false", payload=payload, headers=self.headers)
        if not isinstance(data, dict):
            raise CodeExecutionError("执行服务返回格式无效。", code="EXECUTION_INVALID_RESPONSE")
        token = data.get("token")
        if not token or not isinstance(token, str) or len(token) > 100 or any(c not in "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ-_" for c in token):
            raise CodeExecutionError("执行服务未返回有效任务标识。", code="EXECUTION_INVALID_RESPONSE")
        deadline = time.monotonic() + getattr(settings, "EXECUTION_POLL_TIMEOUT", 15)
        while time.monotonic() < deadline:
            data = request_json("GET", f"{self.base_url}/submissions/{token}?base64_encoded=false&fields=status,stdout,stderr,compile_output,time,memory,exit_code", headers=self.headers, timeout=max(1, deadline - time.monotonic()))
            if not isinstance(data, dict) or not isinstance(data.get("status"), dict):
                raise CodeExecutionError("执行服务返回格式无效。", code="EXECUTION_INVALID_RESPONSE")
            status_id = data["status"].get("id")
            if status_id not in (1, 2):
                break
            time.sleep(0.5)
        else:
            raise CodeExecutionError("执行服务排队超时；本次不计入成绩。", code="EXECUTION_SERVICE_TIMEOUT")
        statuses = {3: "ACCEPTED", 4: "WRONG_ANSWER", 5: "TIME_LIMIT_EXCEEDED", 6: "SYNTAX_ERROR", 7: "RUNTIME_ERROR", 8: "RUNTIME_ERROR", 9: "RUNTIME_ERROR", 10: "RUNTIME_ERROR", 11: "RUNTIME_ERROR", 12: "RUNTIME_ERROR"}
        if status_id not in statuses:
            raise CodeExecutionError("隔离执行服务内部错误；本次不计入成绩。", code="EXECUTION_INTERNAL_ERROR")
        stdout, cut = clipped(data.get("stdout"), limits.output_bytes)
        stderr, errcut = clipped(data.get("compile_output") or data.get("stderr"), limits.output_bytes)
        status = "MEMORY_LIMIT_EXCEEDED" if "MemoryError" in stderr else statuses[status_id]
        if cut or errcut:
            status = "RUNTIME_ERROR"
        return ExecutionResult(status, stdout, stderr, float(data.get("time") or 0), data.get("memory"), "judge0", data.get("exit_code"), cut or errcut)
