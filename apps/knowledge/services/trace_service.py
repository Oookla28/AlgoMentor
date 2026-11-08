"""Persistence helpers for query-level and route-level retrieval traces."""

import uuid


def new_trace_id() -> str:
    return uuid.uuid4().hex


def create_trace(query, variants=None, mode='advanced', user=None, fallback_reason='', metadata=None):
    from apps.knowledge.models import KnowledgeQueryTrace
    return KnowledgeQueryTrace.objects.create(
        trace_id=new_trace_id(),
        user=user if getattr(user, 'is_authenticated', False) else None,
        original_query=query,
        query_variants=list(variants or []),
        retrieval_mode=mode,
        fallback_reason=fallback_reason[:255],
        metadata=metadata or {},
    )


def record_routes(trace, routes) -> int:
    from apps.knowledge.models import KnowledgeRetrievalTrace
    rows = []
    for route in routes:
        rows.append(KnowledgeRetrievalTrace(
            trace=trace,
            query_variant=str(route.get('query_variant', '')),
            retriever_name=str(route.get('retriever_name', 'unknown'))[:50],
            chunk_id=str(route.get('chunk_id', ''))[:100],
            rank=max(1, int(route.get('rank', 1))),
            raw_score=float(route.get('raw_score', 0.0) or 0.0),
            rrf_score=float(route.get('rrf_score', 0.0) or 0.0),
            rerank_score=route.get('rerank_score'),
            selected=bool(route.get('selected', False)),
        ))
    if rows:
        KnowledgeRetrievalTrace.objects.bulk_create(rows, ignore_conflicts=True)
    return len(rows)


def finalize_trace(trace, selected_chunk_ids, latency_ms, evidence_sufficient=False,
                   conflict_count=0, fallback_reason='', metadata=None):
    trace.selected_chunk_ids = list(selected_chunk_ids or [])
    trace.latency_ms = max(0, int(latency_ms))
    trace.evidence_sufficient = bool(evidence_sufficient)
    trace.conflict_count = int(conflict_count)
    trace.fallback_reason = (fallback_reason or trace.fallback_reason or '')[:255]
    if metadata:
        trace.metadata = {**(trace.metadata or {}), **metadata}
    trace.save(update_fields=['selected_chunk_ids', 'latency_ms', 'evidence_sufficient', 'conflict_count', 'fallback_reason', 'metadata'])
    return trace


def serialize_trace(trace) -> dict:
    rows = list(trace.retrieval_traces.all())
    return {
        'trace_id': trace.trace_id,
        'original_query': trace.original_query,
        'query_variants': trace.query_variants,
        'retrieval_mode': trace.retrieval_mode,
        'selected_chunk_ids': trace.selected_chunk_ids,
        'latency_ms': trace.latency_ms,
        'fallback_reason': trace.fallback_reason,
        'evidence_sufficient': trace.evidence_sufficient,
        'conflict_count': trace.conflict_count,
        'created_at': trace.created_at.isoformat() if trace.created_at else '',
        'routes': [
            {
                'query_variant': row.query_variant,
                'retriever_name': row.retriever_name,
                'chunk_id': row.chunk_id,
                'rank': row.rank,
                'raw_score': row.raw_score,
                'rrf_score': row.rrf_score,
                'rerank_score': row.rerank_score,
                'selected': row.selected,
            }
            for row in rows
        ],
    }
