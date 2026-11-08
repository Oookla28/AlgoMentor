"""Pure retrieval / answer-support / agent-quality metrics."""

import math


def recall_at_k(retrieved, relevant, k=None):
    retrieved = list(retrieved)
    relevant = set(relevant)
    if not relevant:
        return 0.0
    if k is not None:
        retrieved = retrieved[:k]
    return len(set(retrieved) & relevant) / len(relevant)


def mrr(retrieved, relevant):
    relevant = set(relevant)
    for index, item in enumerate(retrieved, 1):
        if item in relevant:
            return 1.0 / index
    return 0.0


def ndcg_at_k(retrieved, relevant, k=None):
    relevant = set(relevant)
    if not relevant:
        return 0.0
    if k is not None:
        retrieved = list(retrieved)[:k]
    dcg = 0.0
    for index, item in enumerate(retrieved, 1):
        if item in relevant:
            dcg += 1.0 / math.log2(index + 1)
    ideal = sum(1.0 / math.log2(index + 1) for index in range(1, min(len(relevant), len(retrieved)) + 1))
    return dcg / ideal if ideal else 0.0


def parent_recovery_rate(retrieved_parent_ids, relevant_parent_ids):
    relevant = set(relevant_parent_ids)
    if not relevant:
        return 0.0
    return len(set(retrieved_parent_ids) & relevant) / len(relevant)


def citation_precision(cited_evidence_ids, gold_evidence_ids):
    cited = set(cited_evidence_ids)
    if not cited:
        return 0.0
    return len(cited & set(gold_evidence_ids)) / len(cited)


def citation_recall(cited_evidence_ids, gold_evidence_ids):
    gold = set(gold_evidence_ids)
    if not gold:
        return 1.0
    return len(set(cited_evidence_ids) & gold) / len(gold)


def supported_claim_ratio(claims):
    claims = list(claims)
    if not claims:
        return 1.0
    return sum(1 for claim in claims if claim.get('status') == 'supported') / len(claims)


def unsupported_claim_rate(claims):
    return 1.0 - supported_claim_ratio(claims)


def contradiction_rate(contradictions, claims):
    total = max(1, len(list(claims)))
    return len(contradictions or []) / total


def abstention_precision(predicted_abstentions, actual_unanswerable):
    predicted = set(predicted_abstentions)
    actual = set(actual_unanswerable)
    if not predicted:
        return 1.0
    return len(predicted & actual) / len(predicted)


def abstention_recall(predicted_abstentions, actual_unanswerable):
    actual = set(actual_unanswerable)
    if not actual:
        return 1.0
    return len(set(predicted_abstentions) & actual) / len(actual)


def brier_score(probabilities, outcomes):
    pairs = list(zip(probabilities, outcomes))
    if not pairs:
        return 0.0
    return sum((float(p) - float(o)) ** 2 for p, o in pairs) / len(pairs)


def expected_calibration_error(probabilities, outcomes, bins=5):
    pairs = list(zip(probabilities, outcomes))
    if not pairs:
        return 0.0
    bins = max(1, int(bins))
    total = len(pairs)
    error = 0.0
    for index in range(bins):
        lower, upper = index / bins, (index + 1) / bins
        bucket = [(p, o) for p, o in pairs if lower <= p < upper or (index == bins - 1 and p == 1.0)]
        if not bucket:
            continue
        avg_confidence = sum(p for p, _o in bucket) / len(bucket)
        accuracy = sum(o for _p, o in bucket) / len(bucket)
        error += len(bucket) / total * abs(avg_confidence - accuracy)
    return error


def percentile(values, fraction):
    values = sorted(float(value) for value in values)
    if not values:
        return 0.0
    index = min(len(values) - 1, max(0, int((len(values) - 1) * fraction)))
    return values[index]
