import pytest
from apps.learning.services.mastery_service import RuleEstimator, get_estimator, mastery_label
from apps.learning.services.bkt_service import update_bkt, BKTParameters


def evidence(correct, problem=1, hints=0, difficulty=2):
    return {"correct": correct, "problem_id": problem, "hints_used": hints, "difficulty": difficulty}


def test_rule_single_success_and_repeated_same_problem_cannot_master():
    score, details = RuleEstimator().estimate([evidence(True)], 1)
    assert score <= 55 and not details["evidence_sufficient"]
    repeated, details = RuleEstimator().estimate([evidence(True)] * 20, 1)
    assert repeated <= 55 and not details["evidence_sufficient"]


def test_rule_diversity_and_independence_influence_estimate():
    records = [evidence(True, i % 3, difficulty=3) for i in range(6)]
    value, details = RuleEstimator().estimate(records, 3)
    assert value == 100 and details["evidence_sufficient"]
    assisted, _ = RuleEstimator().estimate([{**row, "hints_used": 4} for row in records], 3)
    assert assisted < value


def test_empty_evidence_and_thresholds():
    assert RuleEstimator().estimate([], 4)[0] == 0
    assert mastery_label(99, 0)["status"] == "UNSEEN"
    for threshold, expected in [(0, "BEGINNER"), (30, "DEVELOPING"), (50, "UNDERSTANDING"), (70, "PROFICIENT"), (85, "MASTERED")]:
        assert mastery_label(threshold, 1)["status"] == expected


def test_bkt_bayes_formula_and_decline():
    # posterior(correct)=.2*.9/(.2*.9+.8*.2), followed by learning transition
    expected = (0.18 / 0.34) + (1 - 0.18 / 0.34) * .1
    assert update_bkt(.2, True) == pytest.approx(expected)
    assert update_bkt(.8, False) < .8
    assert get_estimator("rule").name == "rule"
    assert get_estimator("bkt").name == "bkt"
    with pytest.raises(ValueError):
        BKTParameters(guess=1)
