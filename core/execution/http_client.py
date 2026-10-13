"""Bounded HTTP reads and redacted error mapping for administrator-owned URLs."""
import json
from urllib.parse import urlparse
import requests
from core.exceptions import CodeExecutionError


def validate_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname or parsed.username or parsed.password:
        raise CodeExecutionError("执行服务地址配置无效。", code="EXECUTION_CONFIGURATION")
    # The URL is server configuration; no endpoint is ever supplied by a student.
    return url.rstrip("/")


def request_json(method: str, url: str, *, payload=None, headers=None, timeout=12.0) -> dict | list:
    try:
        network_options = {'proxies': {'http': '', 'https': '', 'all': ''}} if urlparse(url).hostname in ('127.0.0.1', 'localhost', '::1') else {}
        with requests.request(method, url, json=payload, headers=headers or {}, timeout=(4, timeout), stream=True, allow_redirects=False, **network_options) as response:
            if response.status_code in (401, 403):
                raise CodeExecutionError("执行服务需要管理员授权，请配置服务密钥或隔离实例。", code="EXECUTION_AUTH_REQUIRED")
            if response.status_code == 429:
                raise CodeExecutionError("执行服务请求过于频繁，请稍后重试。", code="EXECUTION_RATE_LIMITED")
            if not 200 <= response.status_code < 300:
                raise CodeExecutionError("执行服务暂不可用或运行参数不被服务支持。", code="EXECUTION_UPSTREAM_ERROR")
            chunks = bytearray()
            for chunk in response.iter_content(8192):
                chunks.extend(chunk)
                if len(chunks) > 262144:
                    raise CodeExecutionError("执行服务响应超过安全上限。", code="EXECUTION_RESPONSE_TOO_LARGE")
            result = json.loads(chunks)
            if not isinstance(result, (dict, list)):
                raise ValueError("Unexpected response shape")
            return result
    except requests.Timeout as exc:
        raise CodeExecutionError("隔离执行服务请求超时；本次不计入成绩。", code="EXECUTION_SERVICE_TIMEOUT") from exc
    except (requests.RequestException, ValueError) as exc:
        raise CodeExecutionError("无法连接隔离执行服务；本次不计入成绩。", code="EXECUTION_UNAVAILABLE") from exc
