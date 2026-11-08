"""Tool registry with explicit permissions, timeouts and budget costs."""

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeout
import time

from core.exceptions import BusinessError
from core.security.permissions import require_user

from apps.platform.contracts import ToolResult, ToolSpec
from . import knowledge_tools


SPECS = (
    ToolSpec(
        tool_id='keyword_search', version='1.0.0', name='关键词检索',
        description='BM25 多字词法检索课程子块。',
        input_schema={'query': 'string', 'top_k': 'integer'},
        output_schema={'results': 'array'}, permission='read', timeout_seconds=4.0, budget_cost=1,
    ),
    ToolSpec(
        tool_id='semantic_search', version='1.0.0', name='语义检索',
        description='使用当前配置的稠密索引检索课程片段。',
        input_schema={'query': 'string', 'top_k': 'integer'},
        output_schema={'results': 'array'}, permission='read', timeout_seconds=6.0, budget_cost=1,
    ),
    ToolSpec(
        tool_id='read_child', version='1.0.0', name='读取命中子块',
        description='读取一个子块的完整内容与来源。',
        input_schema={'chunk_id': 'string'}, output_schema={'result': 'object'},
        permission='read', timeout_seconds=3.0, budget_cost=1,
    ),
    ToolSpec(
        tool_id='read_parent', version='1.0.0', name='读取父块',
        description='读取命中子块的父块上下文。',
        input_schema={'chunk_id': 'string'}, output_schema={'result': 'object'},
        permission='read', timeout_seconds=3.0, budget_cost=1,
    ),
    ToolSpec(
        tool_id='read_siblings', version='1.0.0', name='读取相邻片段',
        description='读取同一父块下的其他子块。',
        input_schema={'chunk_id': 'string', 'limit': 'integer'}, output_schema={'results': 'array'},
        permission='read', timeout_seconds=3.0, budget_cost=1,
    ),
    ToolSpec(
        tool_id='read_source_page', version='1.0.0', name='读取原文页',
        description='读取同一文档同一页的片段。',
        input_schema={'chunk_id': 'string', 'limit': 'integer'}, output_schema={'results': 'array'},
        permission='read', timeout_seconds=3.0, budget_cost=1,
    ),
    ToolSpec(
        tool_id='retrieve_conflicting_versions', version='1.0.0', name='读取冲突版本',
        description='检索同名文档的其他版本中的相关证据。',
        input_schema={'query': 'string', 'chunk_id': 'string'},
        output_schema={'results': 'array'}, permission='read', timeout_seconds=5.0, budget_cost=2,
    ),
)

HANDLERS = {
    'keyword_search': knowledge_tools.keyword_search,
    'semantic_search': knowledge_tools.semantic_search,
    'read_child': knowledge_tools.read_child,
    'read_parent': knowledge_tools.read_parent,
    'read_siblings': knowledge_tools.read_siblings,
    'read_source_page': knowledge_tools.read_source_page,
    'retrieve_conflicting_versions': knowledge_tools.retrieve_conflicting_versions,
}

REGISTRY = {spec.tool_id: (spec, HANDLERS[spec.tool_id]) for spec in SPECS}


def get_tool_spec(tool_id: str):
    entry = REGISTRY.get(tool_id)
    return entry[0] if entry else None


def list_tool_specs():
    return [spec.to_dict() for spec in SPECS]


def execute_spec(spec: ToolSpec, handler, user, **kwargs) -> ToolResult:
    require_user(user)
    if not spec.enabled:
        return ToolResult(False, spec.tool_id, failure_code='TOOL_DISABLED', message='工具已禁用。')
    if spec.permission == 'write' and not user.is_staff:
        return ToolResult(False, spec.tool_id, failure_code='TOOL_PERMISSION_DENIED', message='当前账户无该工具权限。')
    started = time.monotonic()
    executor = ThreadPoolExecutor(max_workers=1)
    try:
        future = executor.submit(handler, user, **kwargs)
        output = future.result(timeout=spec.timeout_seconds)
        latency = int((time.monotonic() - started) * 1000)
        evidence_ids = tuple(
            item.get('chunk_id') for item in (output.get('results') or [])
            if isinstance(item, dict) and item.get('chunk_id')
        )
        if not evidence_ids and isinstance(output.get('result'), dict) and output['result'].get('chunk_id'):
            evidence_ids = (output['result']['chunk_id'],)
        return ToolResult(True, spec.tool_id, output=output, evidence_ids=evidence_ids, latency_ms=latency)
    except FutureTimeout:
        return ToolResult(False, spec.tool_id, latency_ms=int(spec.timeout_seconds * 1000), failure_code='TOOL_TIMEOUT', message='工具执行超时。')
    except BusinessError as exc:
        return ToolResult(False, spec.tool_id, latency_ms=int((time.monotonic() - started) * 1000), failure_code=exc.code, message=exc.message)
    except Exception as exc:
        return ToolResult(False, spec.tool_id, latency_ms=int((time.monotonic() - started) * 1000), failure_code=f'TOOL_ERROR:{type(exc).__name__}', message='工具执行失败。')
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def execute_tool(tool_id: str, user, **kwargs) -> ToolResult:
    entry = REGISTRY.get(tool_id)
    if entry is None:
        require_user(user)
        return ToolResult(False, tool_id, failure_code='TOOL_NOT_FOUND', message='工具不存在。')
    spec, handler = entry
    return execute_spec(spec, handler, user, **kwargs)
