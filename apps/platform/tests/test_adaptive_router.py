from apps.platform.agent.adaptive_router import (
    DEFAULT_WEIGHTS, RouteAction, RoutingState, action_utility, choose_action,
)


def test_router_stops_when_no_lexical_or_dense_support():
    action, rationale = choose_action(RoutingState(query='量子引力', evidence=[], coverage=0.0, dense_support=0.0))
    assert action is None
    assert rationale['reason'] == 'NO_RELEVANT_EVIDENCE'


def test_router_stops_when_gate_satisfied():
    state = RoutingState(query='循环队列', evidence=[], coverage=0.8, support=0.7, dense_support=0.5)
    action, rationale = choose_action(state)
    assert action is None
    assert rationale['reason'] == 'GATE_SATISFIED'


def test_router_selects_bounded_next_action():
    evidence = [{'chunk_id': 'c1', 'chunk_type': 'child', 'parent_chunk_id': 'p1'}]
    state = RoutingState(query='循环队列判满', evidence=evidence, coverage=0.1, support=0.4, dense_support=0.4, attempted={'keyword_search', 'semantic_search'})
    action, rationale = choose_action(state)
    assert action is not None
    assert action.tool_id in {'read_parent', 'read_siblings', 'read_source_page'}
    assert rationale['calibrated'] is False
    assert rationale['candidates']


def test_utility_penalizes_cost_and_risk():
    cheap = RouteAction('cheap', 'read_child', {}, token_cost=10, latency_cost_ms=10, risk=0.0)
    expensive = RouteAction('expensive', 'read_source_page', {}, token_cost=1000, latency_cost_ms=1000, risk=0.5)
    state = RoutingState(query='q')
    assert action_utility(cheap, state, DEFAULT_WEIGHTS) > action_utility(expensive, state, DEFAULT_WEIGHTS)
