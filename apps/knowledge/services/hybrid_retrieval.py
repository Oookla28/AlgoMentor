"""Advanced hybrid retrieval: query rewrite -> fan-out -> RRF -> rerank -> Small2Big."""

from dataclasses import asdict, dataclass, field
import time

from django.conf import settings

from core.exceptions import BusinessError, KnowledgeRetrievalError, ValidationError

from .embedding_service import cached_embeddings, embedding_identity


@dataclass
class RetrievalResult:
    citations: list = field(default_factory=list)
    mode: str = 'advanced'
    trace_id: str = ''
    original_query: str = ''
    query_variants: list = field(default_factory=list)
    retrieval_trace: list = field(default_factory=list)
    conflicts: list = field(default_factory=list)
    fallback: dict = field(default_factory=dict)
    media_evidence: list = field(default_factory=list)
    evidence_sufficient: bool = False
    embedding_provider: str = ''
    rerank_backend: str = ''
    query_route: dict = field(default_factory=dict)
    citation_check: dict = field(default_factory=dict)
    warnings: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            'citations': [asdict(citation) for citation in self.citations],
            'mode': self.mode,
            'trace_id': self.trace_id,
            'original_query': self.original_query,
            'query_variants': list(self.query_variants),
            'retrieval_trace': list(self.retrieval_trace),
            'conflicts': list(self.conflicts),
            'fallback': dict(self.fallback),
            'media_evidence': list(self.media_evidence),
            'evidence_sufficient': self.evidence_sufficient,
            'embedding_provider': self.embedding_provider,
            'rerank_backend': self.rerank_backend,
            'query_route': dict(self.query_route),
            'citation_check': dict(self.citation_check),
            'warnings': list(self.warnings),
        }


def _document_freshness(document):
    from .rerank_service import freshness_score
    return freshness_score(document.valid_from, document.valid_to, document.created_at)


def _to_citation(row, score: float):
    from .retrieval_service import Citation
    media = row.media_asset if row.media_asset_id else None
    return Citation(
        chunk_id=row.chunk_id,
        document_name=row.document.name,
        document_hash=row.document.document_hash,
        chapter=row.chapter,
        section=row.section,
        page_number=row.page_number,
        content=row.content,
        source_type=row.source_type,
        version=row.version,
        score=round(float(score), 6),
        url=f'/knowledge/source/{row.chunk_id}/',
        parent_chunk_id=row.parent_chunk.chunk_id if row.parent_chunk_id else '',
        heading_path=row.heading_path,
        chunk_type=row.chunk_type,
        char_start=row.char_start,
        char_end=row.char_end,
        evidence_id=f'chunk:{row.chunk_id}',
        matched_content=row.content,
        media_asset_id=media.asset_id if media else '',
        start_time=media.start_time if media else None,
        end_time=media.end_time if media else None,
        authority_level=row.document.authority_level,
        source_uri=f'/knowledge/source/{row.chunk_id}/',
    )


def _serialize_media(row):
    media = row.media_asset
    if not media:
        return None
    from .evidence_schema import evidence_from_media
    return evidence_from_media(media).to_dict()


def _legacy_fallback(query, top_k, reason, warnings, route=None, variants=None, user=None):
    from .retrieval_service import retrieve_knowledge
    from .trace_service import create_trace, finalize_trace
    trace = create_trace(query, variants or [query], mode='legacy', user=user, fallback_reason=reason, metadata={'requested_mode': 'advanced'})
    try:
        citations = retrieve_knowledge(query, top_k=top_k)
        error = ''
    except BusinessError as exc:
        citations = []
        error = exc.message
        warnings.append(error)
    finalize_trace(trace, [citation.chunk_id for citation in citations], 0, bool(citations), 0, reason, {'legacy_error': error})
    return RetrievalResult(
        citations=citations,
        mode='legacy',
        trace_id=trace.trace_id,
        original_query=query,
        query_variants=list(variants or [query]),
        fallback={'used': True, 'reason': reason, 'warnings': warnings},
        evidence_sufficient=bool(citations),
        embedding_provider=getattr(settings, 'EMBEDDING_PROVIDER', ''),
        query_route=route or {},
    )


def _dense_candidates(variants, documents, route_top_k, min_score, warnings):
    from langchain_chroma import Chroma
    from .advanced_index_service import collection_name_for
    routes = []
    raw_scores = {}
    failed = False
    for document in documents:
        identity = ((document.source_metadata or {}).get('advanced') or {}).get('embedding_identity', '')
        if identity and identity != embedding_identity():
            warnings.append(f'DOC_EMBEDDING_MISMATCH:{document.pk}')
            continue
        try:
            store = Chroma(
                collection_name=collection_name_for(document.latest_index_version),
                persist_directory=str(settings.CHROMA_PATH),
                embedding_function=cached_embeddings(document.latest_index_version),
                collection_metadata={'hnsw:space': 'cosine'},
            )
        except Exception:
            failed = True
            warnings.append(f'DENSE_INDEX_OPEN_FAILED:{document.pk}')
            continue
        for variant in variants:
            try:
                hits = store.similarity_search_with_score(variant, k=route_top_k)
            except Exception:
                failed = True
                warnings.append(f'DENSE_QUERY_FAILED:{document.pk}')
                continue
            rank = 0
            for item, distance in hits:
                chunk_id = item.metadata.get('chunk_id')
                if not chunk_id:
                    continue
                score = max(0.0, min(1.0, 1 - float(distance)))
                if score < min_score:
                    continue
                rank += 1
                routes.append({
                    'query_variant': variant,
                    'retriever_name': 'dense',
                    'chunk_id': chunk_id,
                    'rank': rank,
                    'raw_score': round(score, 6),
                })
                raw_scores[chunk_id] = max(raw_scores.get(chunk_id, 0.0), score)
    return routes, raw_scores, failed


def advanced_retrieve(query: str, top_k: int | None = None, user=None) -> RetrievalResult:
    from apps.knowledge.models import KnowledgeChunk, KnowledgeDocument
    from .claim_service import extract_and_store_claims
    from .conflict_service import detect_and_store_conflicts, serialize_conflict
    from .query_rewriter import rewrite_query
    from .rerank_service import RerankCandidate, rerank
    from .rrf_service import reciprocal_rank_fusion
    from .small2big_service import expand_citations
    from .sparse_retrieval import BM25Index, load_advanced_documents, tokenize
    from .trace_service import create_trace, finalize_trace, record_routes

    started = time.monotonic()
    query = (query or '').strip()
    if not query or len(query) > 2000:
        raise ValidationError('检索问题须为 1 至 2000 字。')
    if not getattr(settings, 'EVIDENCE_RAG_ENABLED', True):
        return _legacy_fallback(query, top_k, 'EVIDENCE_RAG_DISABLED', [], None, [query], user)
    rewrite = rewrite_query(query, user=user)
    variants = list(rewrite.variants)
    route_info = rewrite.route
    documents = list(KnowledgeDocument.objects.filter(latest_index_version__gt='').order_by('-created_at')[:20])
    if not documents:
        return _legacy_fallback(query, top_k, 'ADVANCED_INDEX_MISSING', [], route_info, variants, user)
    trace = create_trace(query, variants, mode='advanced', user=user, metadata={'rewrite': rewrite.to_dict(), 'route': route_info})
    warnings = []
    if rewrite.used_fallback and rewrite.fallback_reason and rewrite.fallback_reason != 'HEURISTIC_FALLBACK':
        warnings.append(f'REWRITE_FALLBACK:{rewrite.fallback_reason}')
    route_top_k = getattr(settings, 'EVIDENCE_RAG_ROUTE_TOP_K', 20)
    dense_routes, dense_scores, dense_failed = _dense_candidates(
        variants, documents, route_top_k, getattr(settings, 'EVIDENCE_RAG_DENSE_MIN_SCORE', 0.20), warnings,
    )
    sparse_routes = []
    sparse_scores = {}
    document_ids = [document.pk for document in documents]
    sparse_documents = load_advanced_documents(document_ids)
    if sparse_documents:
        index = BM25Index(sparse_documents)
        for variant in variants:
            for hit in index.search(variant, top_k=route_top_k):
                sparse_routes.append({
                    'query_variant': variant,
                    'retriever_name': 'sparse',
                    'chunk_id': hit.chunk_id,
                    'rank': hit.rank,
                    'raw_score': hit.score,
                })
                sparse_scores[hit.chunk_id] = max(sparse_scores.get(hit.chunk_id, 0.0), hit.score)
    else:
        warnings.append('SPARSE_CORPUS_EMPTY')

    if not dense_routes and not sparse_routes:
        if dense_failed:
            return _legacy_fallback(query, top_k, 'DENSE_RETRIEVAL_FAILED', warnings, route_info, variants, user)
        finalize_trace(trace, [], int((time.monotonic() - started) * 1000), False, 0, '', {'warnings': warnings})
        return RetrievalResult(
            mode='advanced', trace_id=trace.trace_id, original_query=query, query_variants=variants,
            fallback={'used': False, 'reason': '', 'warnings': warnings},
            query_route=route_info, embedding_provider=getattr(settings, 'EMBEDDING_PROVIDER', ''),
            warnings=warnings,
        )

    rankings = {}
    for route in dense_routes:
        rankings.setdefault(f"dense::{route['query_variant']}", []).append(route['chunk_id'])
    for route in sparse_routes:
        rankings.setdefault(f"sparse::{route['query_variant']}", []).append(route['chunk_id'])
    fused = reciprocal_rank_fusion(rankings, k=getattr(settings, 'EVIDENCE_RAG_RRF_K', 60))
    fused_scores = {entry.chunk_id: entry.score for entry in fused}
    ranked_ids = [entry.chunk_id for entry in fused]
    rows = {
        row.chunk_id: row
        for row in KnowledgeChunk.objects.select_related('document', 'parent_chunk', 'media_asset')
        .filter(chunk_id__in=ranked_ids, is_active=True)
    }
    def content_terms(text):
        terms = {token for token in tokenize(text or '') if len(token) > 1}
        return terms or set(tokenize(text or ''))

    query_terms = content_terms(query)
    overlap_gate = getattr(settings, 'EVIDENCE_RAG_MIN_LEXICAL_OVERLAP', 0.20) * 0.5
    dense_support = getattr(settings, 'EVIDENCE_RAG_MIN_DENSE_SUPPORT', 0.35)
    candidates = []
    gated_out = 0
    for chunk_id in ranked_ids:
        row = rows.get(chunk_id)
        if row is None or row.chunk_type not in ('child', 'media'):
            continue
        evidence_terms = content_terms((row.content or '') + ' ' + (row.heading_path or ''))
        overlap = len(query_terms & evidence_terms) / max(1, len(query_terms))
        if overlap < overlap_gate and dense_scores.get(chunk_id, 0.0) < dense_support:
            gated_out += 1
            continue
        raw = max(dense_scores.get(chunk_id, 0.0), sparse_scores.get(chunk_id, 0.0))
        candidates.append(RerankCandidate(
            chunk_id=chunk_id,
            content=row.content,
            heading_path=row.heading_path,
            authority_level=row.document.authority_level,
            parser_confidence=row.parser_confidence,
            freshness=_document_freshness(row.document),
            rrf_score=fused_scores.get(chunk_id, 0.0),
            raw_score=raw,
        ))
    ordered, rerank_backend, rerank_fallback = rerank(query, candidates)
    if rerank_fallback:
        warnings.append(f'RERANK_FALLBACK:{rerank_fallback}')
    limit = max(1, min(top_k or getattr(settings, 'EVIDENCE_RAG_TOP_K', 6), 8))
    threshold = getattr(settings, 'EVIDENCE_RAG_MIN_RERANK_SCORE', 0.12)
    selected = [candidate for candidate in ordered[:limit] if candidate.rerank_score >= threshold]
    selected_rows = [rows[candidate.chunk_id] for candidate in selected]
    citations = [_to_citation(row, candidate.rerank_score) for row, candidate in zip(selected_rows, selected)]
    citations = expand_citations(citations)
    selected_rows = [rows[citation.chunk_id] for citation in citations]
    selected_ids = [citation.chunk_id for citation in citations]
    top_score = ordered[0].rerank_score if ordered else 0.0
    second_score = ordered[1].rerank_score if len(ordered) > 1 else 0.0
    route_info = {
        **route_info,
        'top_rerank_score': round(top_score, 6),
        'low_confidence': top_score < threshold,
        'scores_close': bool(len(ordered) > 1 and abs(top_score - second_score) < 0.02),
        'evidence_gate': {
            'min_lexical_overlap': overlap_gate, 'min_dense_support': dense_support,
            'gated_out': gated_out, 'kept_candidates': len(candidates),
        },
    }

    claims = extract_and_store_claims(selected_rows)
    retrieval_scores = {citation.chunk_id: citation.score for citation in citations}
    conflicts = detect_and_store_conflicts(trace, claims, retrieval_scores=retrieval_scores)
    conflict_payload = [serialize_conflict(conflict) for conflict in conflicts]
    media_payload = []
    seen_assets = set()
    for row in selected_rows:
        payload = _serialize_media(row)
        if payload and payload['evidence_id'] not in seen_assets:
            seen_assets.add(payload['evidence_id'])
            media_payload.append(payload)
    reranked = {candidate.chunk_id: candidate.rerank_score for candidate in ordered}
    trace_rows = []
    for route in dense_routes + sparse_routes:
        chunk_id = route['chunk_id']
        trace_rows.append({
            **route,
            'rrf_score': fused_scores.get(chunk_id, 0.0),
            'rerank_score': reranked.get(chunk_id),
            'selected': chunk_id in selected_ids,
        })
    record_routes(trace, trace_rows)
    sufficient = bool(citations)
    finalize_trace(
        trace, selected_ids, int((time.monotonic() - started) * 1000), sufficient, len(conflict_payload), '',
        {
            'warnings': warnings, 'rerank_backend': rerank_backend, 'rerank_fallback': rerank_fallback,
            'selected_scores': {candidate.chunk_id: candidate.rerank_score for candidate in selected},
            'route': route_info,
        },
    )
    from .trace_service import serialize_trace
    return RetrievalResult(
        citations=citations,
        mode='advanced',
        trace_id=trace.trace_id,
        original_query=query,
        query_variants=variants,
        retrieval_trace=serialize_trace(trace)['routes'],
        conflicts=conflict_payload,
        fallback={'used': False, 'reason': '', 'warnings': warnings},
        media_evidence=media_payload,
        evidence_sufficient=sufficient,
        embedding_provider=getattr(settings, 'EMBEDDING_PROVIDER', ''),
        rerank_backend=rerank_backend,
        query_route=route_info,
        warnings=warnings,
    )


def advanced_search_payload(query: str, top_k: int | None = None, user=None) -> dict:
    result = advanced_retrieve(query, top_k=top_k, user=user)
    payload = result.to_dict()
    payload['results'] = payload['citations']
    return payload
