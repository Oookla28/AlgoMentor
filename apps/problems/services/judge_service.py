from dataclasses import dataclass
from core.execution.provider import ExecutionLimits, ExecutionResult, CodeExecutionProvider
from core.exceptions import CodeExecutionError
from apps.problems.models import TestCase


def normalize_output(value: str) -> str:
    """Ignore trailing line whitespace and final newlines; preserve token content."""
    return "\n".join(line.rstrip() for line in value.replace("\r\n", "\n").splitlines()).rstrip("\n")


@dataclass(frozen=True)
class CaseOutcome:
    case: TestCase
    execution: ExecutionResult
    status: str


@dataclass(frozen=True)
class JudgeOutcome:
    status: str
    outcomes: tuple[CaseOutcome, ...]
    passed_cases: int
    total_cases: int
    error_message: str = ""


def judge_problem(problem, code: str, provider: CodeExecutionProvider) -> JudgeOutcome:
    from django.conf import settings
    cases = list(problem.test_cases.all())
    if not cases or len(cases) > getattr(settings, "MAX_TEST_CASES", 10):
        raise CodeExecutionError("题目测试用例配置无效，请联系管理员。", code="JUDGE_CONFIGURATION")
    limits = ExecutionLimits(time_seconds=min(problem.time_limit_seconds, 3), memory_mb=min(problem.memory_limit_mb, 256))
    outcomes = []
    for case in cases:
        execution = provider.run(code, case.stdin, limits)
        status = execution.status
        if status not in ("ACCEPTED", "WRONG_ANSWER", "SYNTAX_ERROR", "RUNTIME_ERROR", "TIME_LIMIT_EXCEEDED", "MEMORY_LIMIT_EXCEEDED"):
            raise CodeExecutionError("执行服务返回无效评测状态；本次不计入成绩。", code="EXECUTION_INVALID_STATUS")
        if status == "ACCEPTED" and normalize_output(execution.stdout) != normalize_output(case.expected_output):
            status = "WRONG_ANSWER"
        outcomes.append(CaseOutcome(case, execution, status))
    passed = sum(outcome.status == "ACCEPTED" for outcome in outcomes)
    # A runtime or resource failure is more specific than merely a wrong answer.
    failed = [outcome.status for outcome in outcomes if outcome.status != "ACCEPTED"]
    status = next((value for value in failed if value != "WRONG_ANSWER"), failed[0] if failed else "ACCEPTED")
    return JudgeOutcome(status, tuple(outcomes), passed, len(cases))
