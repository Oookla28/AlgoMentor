import re
from typing import Any

_SECRET = re.compile(r'(?i)(?:sk-[a-z0-9_\-]{8,}|bearer\s+[^\s"\']+|(?:api[_ -]?key|authorization|secret|password)\s*[:=]\s*[^\s,}]+)')


def redact(value: Any, limit: int = 500) -> str:
    return _SECRET.sub('[已脱敏]', str(value))[:limit]
