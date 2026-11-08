"""Deterministic adaptive evidence routing with explicit action budgets.

The utility weights below are engineering defaults, not validation-calibrated
research results. The action set and stop rules are deterministic and bounded.
"""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class RouteAction:
    action_id: str
    tool_id: str
    args: dict
    token_cost: int = 200
    latency_cost_ms: int = 100
    risk: float = 0.05
    expected_support: float = 0.2


@dataclass
class RoutingState:
    query: str
    evidence: list = field(default_factory=list)
    attempted: set = field(default_factory=set)
    coverage: float = 0.0
    support: float = 0.0
    dense_support: float = 0.0
    authority: float = 0.0
    conflict_count: int = 0
    hop: int = 0
    tool_calls: int = 0
    tokens: int = 0
    latency_ms: int = 0


DEFAULT_WEIGHTS = {
    'lambda_token': 0.00002,
    'mu_latency': 0.00002,
    'nu_tool': 0.04,
    'eta_risk': 0.10,
    'minimum_utility': 0.05,
    'coverage_target': 0.45,
    'support_target': 0.30,
    'calibrated': False,
}


def _top_evidence(state: RoutingState):
    return state.evidence[0] if state.evidence else None


def candidates(state: RoutingState):
    top = _top_evidence(state)
    actions = []
    if 'keyword_search' not in state.attempted:
        actions.append(RouteAction('keyword_search', 'keyword_search', {'query': state.query}, token_cost=150, latency_cost_ms=150, risk=0.02, expected_support=0.30))
    if 'semantic_search' not in state.attempted:
        actions.append(RouteAction('semantic_search', 'semantic_search', {'query': state.query}, token_cost=250, latency_cost_ms=300, risk=0.03, expected_support=0.38))
    if top and top.get('chunk_id') and top.get('chunk_type', 'child') == 'child' and 'read_parent' not in state.attempted:
        actions.append(RouteAction('read_parent', 'read_parent', {'chunk_id': top['chunk_id']}, token_cost=180, latency_cost_ms=100, risk=0.01, expected_support=0.22))
    if top and top.get('parent_chunk_id') and 'read_siblings' not in state.attempted and state.coverage < 0.35:
        actions.append(RouteAction('read_siblings', 'read_siblings', {'chunk_id': top['chunk_id'], 'limit': 4}, token_cost=300, latency_cost_ms=150, risk=0.02, expected_support=0.15))
    if top and top.get('chunk_id') and 'read_source_page' not in state.attempted:
        actions.append(RouteAction('read_source_page', 'read_source_page', {'chunk_id': top['chunk_id'], 'limit': 6}, token_cost=350, latency_cost_ms=180, risk=0.02, expected_support=0.16))
    if state.conflict_count and top and top.get('chunk_id') and 'retrieve_conflicting_versions' not in state.attempted:
        actions.append(RouteAction('retrieve_conflicting_versions', 'retrieve_conflicting_versions', {'query': state.query, 'chunk_id': top['chunk_id']}, token_cost=400, latency_cost_ms=300, risk=0.10, expected_support=0.25))
    return actions


def action_utility(action: RouteAction, state: RoutingState, weights=None) -> float:
    weights = weights or DEFAULT_WEIGHTS
    return (
        action.expected_support
        - weights['lambda_token'] * action.token_cost
        - weights['mu_latency'] * action.latency_cost_ms
        - weights['nu_tool'] * 1
        - weights['eta_risk'] * action.risk
    )


def choose_action(state: RoutingState, weights=None):
    weights = weights or DEFAULT_WEIGHTS
    if state.coverage >= weights['coverage_target'] and state.support >= weights['support_target'] and not state.conflict_count:
        return None, {'stopped': True, 'reason': 'GATE_SATISFIED'}
    if state.coverage == 0.0 and state.dense_support == 0.0:
        return None, {'stopped': True, 'reason': 'NO_RELEVANT_EVIDENCE'}
    scored = [(action_utility(action, state, weights), action) for action in candidates(state)]
    scored.sort(key=lambda pair: (-pair[0], pair[1].action_id))
    if not scored:
        return None, {'stopped': True, 'reason': 'NO_ACTION_AVAILABLE'}
    best_score, best_action = scored[0]
    return (best_action if best_score >= weights['minimum_utility'] else None), {
        'stopped': best_score < weights['minimum_utility'],
        'reason': 'UTILITY_BELOW_THRESHOLD' if best_score < weights['minimum_utility'] else 'SELECTED',
        'utility': round(best_score, 6),
        'candidates': [{'action_id': action.action_id, 'utility': round(score, 6)} for score, action in scored],
        'calibrated': weights.get('calibrated', False),
    }
