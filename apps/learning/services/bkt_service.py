"""Four-parameter Bayesian knowledge tracing.

Formula follows Corbett/Anderson BKT, described in pyBKT (EDM 2021):
https://educationaldatamining.org/EDM2021/virtual/static/pdf/EDM21_paper_237.pdf
Our numerical priors are transparent, untrained engineering defaults, not fitted
values or reported research results. They must be calibrated before deployment.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class BKTParameters:
    initial: float = 0.2
    transition: float = 0.1
    guess: float = 0.2
    slip: float = 0.1

    def __post_init__(self):
        if any(not 0 < value < 1 for value in (self.initial, self.transition, self.guess, self.slip)):
            raise ValueError("BKT parameters must be between zero and one")


def update_bkt(prior: float, correct: bool, parameters: BKTParameters = BKTParameters()) -> float:
    if correct:
        posterior = prior * (1 - parameters.slip) / (prior * (1 - parameters.slip) + (1 - prior) * parameters.guess)
    else:
        posterior = prior * parameters.slip / (prior * parameters.slip + (1 - prior) * (1 - parameters.guess))
    return posterior + (1 - posterior) * parameters.transition


class BKTEstimator:
    name = "bkt"

    def estimate(self, evidence: list[dict], available_problems: int = 1, config: dict | None = None) -> tuple[float, dict]:
        configuration = dict(config or {})
        if "learn" in configuration:
            configuration.setdefault("transition", configuration.pop("learn"))
        parameters = BKTParameters(**configuration)
        probability = parameters.initial
        for attempt in evidence:
            probability = update_bkt(probability, attempt["correct"], parameters)
        return probability, {"kind": "BKT估计掌握概率", "prior_source": "未经拟合的可配置工程先验", "parameters": parameters.__dict__, "evidence_count": len(evidence)}
