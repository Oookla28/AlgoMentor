import pytest

from apps.platform.evaluation.metrics import (
    abstention_precision, abstention_recall, brier_score, citation_precision, citation_recall,
    expected_calibration_error, mrr, ndcg_at_k, percentile, recall_at_k, supported_claim_ratio,
    unsupported_claim_rate,
)


def test_retrieval_metrics():
    assert recall_at_k(['a', 'b', 'c'], {'b'}, 2) == 1.0
    assert recall_at_k(['a', 'b', 'c'], {'c'}, 2) == 0.0
    assert mrr(['a', 'b', 'c'], {'c'}) == 1 / 3
    assert ndcg_at_k(['a', 'b'], {'b'}) == pytest.approx(1 / 1.5849625007211563)
    assert percentile([1, 2, 3, 4], 0.5) == 2.0


def test_citation_and_claim_metrics():
    assert citation_precision(['a', 'b'], {'a'}) == 0.5
    assert citation_recall(['a'], {'a', 'b'}) == 0.5
    claims = [{'status': 'supported'}, {'status': 'unsupported'}]
    assert supported_claim_ratio(claims) == 0.5
    assert unsupported_claim_rate(claims) == 0.5


def test_abstention_and_calibration_metrics():
    assert abstention_precision(['x', 'y'], {'x'}) == 0.5
    assert abstention_recall(['x'], {'x', 'y'}) == 0.5
    assert brier_score([0.8, 0.2], [1, 0]) == pytest.approx(0.04)
    assert expected_calibration_error([0.8, 0.2], [1, 0], bins=2) == pytest.approx(0.2)
