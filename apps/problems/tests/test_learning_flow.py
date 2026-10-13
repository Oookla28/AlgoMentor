"""Integration tests inject execution responses; these are not live judge claims."""
import uuid
import pytest
from django.contrib.auth import get_user_model
from django.test import Client
from django.utils import timezone
from django.core.management import call_command
from core.execution.provider import ExecutionResult
from core.exceptions import CodeExecutionError
from apps.knowledge.models import KnowledgePoint
from apps.problems.models import Problem, TestCase as ProblemTestCase, Submission
from apps.learning.models import MasteryState, LearningActivity, MistakeRecord, MasterySnapshot
from apps.problems.services.submission_service import submit_code, serialize_submission
from apps.learning.services.mastery_service import record_submission_evidence
from apps.learning.services.progress_service import get_learning_summary
from apps.graph.services.graph_builder import get_graph


@pytest.fixture
def user(db):
    return get_user_model().objects.create_user(username="learner", password="LongPassword123!")


@pytest.fixture
def problem(db):
    point = KnowledgePoint.objects.create(slug="linked-list", name="单链表", chapter=2, order=1)
    sibling = KnowledgePoint.objects.create(slug="list-insert", name="顺序表插入", chapter=2, order=2)
    problem = Problem.objects.create(slug="reverse", title="反转", description="反转序列", difficulty=2,
        input_description="输入", output_description="输出", reference_solution="print(3,2,1)", reference_complexity="O(n)")
    problem.knowledge_points.add(point)
    ProblemTestCase.objects.create(problem=problem, sequence=1, stdin="1 2 3\n", expected_output="3 2 1\n", is_hidden=False)
    ProblemTestCase.objects.create(problem=problem, sequence=2, stdin="SECRET_CASE_72\n", expected_output="secret answer\n", is_hidden=True)
    return problem


class Responses:
    def __init__(self, correct=True, status="ACCEPTED"):
        self.correct, self.status, self.calls = correct, status, []

    def run(self, source, stdin, limits):
        self.calls.append((source, stdin, limits))
        stdout = ("3 2 1\n" if stdin == "1 2 3\n" else "secret answer\n") if self.correct else stdin
        return ExecutionResult(self.status, stdout=stdout, stderr="SyntaxError: invalid syntax" if self.status == "SYNTAX_ERROR" else "", elapsed_seconds=.01, provider="test-only")


class Unavailable:
    def run(self, *args):
        raise CodeExecutionError("测试替身服务不可用。", code="EXECUTION_UNAVAILABLE")


def submit(user, problem, provider, **kwargs):
    return submit_code(user, problem.pk, "print(input())", provider=provider, **kwargs)


def test_accepted_submission_updates_only_tagged_point_and_snapshot(user, problem):
    provider = Responses()
    item = submit(user, problem, provider, request_key="successful")
    assert item.status == "ACCEPTED" and item.passed_cases == 2
    assert len(provider.calls) == 2
    assert LearningActivity.objects.filter(user=user).count() == 1
    state = MasteryState.objects.get(user=user)
    assert 0 < state.index <= 55
    assert state.evidence_count == 1
    assert MasterySnapshot.objects.filter(user=user).count() == 1
    graph = get_graph(user)
    nodes = {node["id"]: node for node in graph["nodes"]}
    assert nodes["linked-list"]["status"] != "UNSEEN"
    assert nodes["list-insert"]["status"] == "UNSEEN"
    assert nodes["chapter_02"]["index"] < 70
    assert nodes["chapter_02"]["coverage"] == 50


def test_wrong_answer_creates_mistake_then_pass_preserves_history(user, problem):
    failed = submit(user, problem, Responses(correct=False))
    assert failed.status == "WRONG_ANSWER"
    mistake = MistakeRecord.objects.get(submission=failed)
    assert not mistake.resolved
    passed = submit(user, problem, Responses())
    mistake.refresh_from_db()
    assert passed.status == "ACCEPTED" and mistake.resolved and mistake.resolved_at
    assert MistakeRecord.objects.count() == 1
    summary = get_learning_summary(user)
    assert summary["total_submissions"] == 2
    assert summary["submission_accuracy"] == 50
    assert summary["problem_pass_rate"] == 100


def test_external_failure_never_changes_mastery_or_mistakes_or_accuracy(user, problem):
    item = submit(user, problem, Unavailable())
    assert item.status == "JUDGE_ERROR" and not item.is_valid
    assert not MasteryState.objects.exists() and not MistakeRecord.objects.exists()
    summary = get_learning_summary(user)
    assert summary["total_submissions"] == 0
    assert summary["submission_accuracy"] is None
    assert summary["excluded_infrastructure_submissions"] == 1


@pytest.mark.parametrize("status", ["SYNTAX_ERROR", "RUNTIME_ERROR", "TIME_LIMIT_EXCEEDED", "MEMORY_LIMIT_EXCEEDED"])
def test_actual_program_failures_are_distinct_valid_evidence(user, problem, status):
    item = submit(user, problem, Responses(status=status))
    assert item.status == status and item.is_valid
    assert MistakeRecord.objects.get().error_type == status
    assert MasteryState.objects.get().index == 0


def test_hidden_test_inputs_outputs_and_tracebacks_not_in_api(user, problem):
    item = submit(user, problem, Responses(correct=False))
    payload = serialize_submission(item)
    hidden = next(row for row in payload["test_results"] if row["hidden"])
    assert "stdout" not in hidden and "stdin" not in hidden and "expected_output" not in hidden
    import json
    assert "SECRET_CASE_72" not in json.dumps(payload)
    assert "secret answer" not in json.dumps(payload)


def test_submission_and_learning_events_deduplicate(user, problem):
    provider = Responses()
    first = submit(user, problem, provider, request_key="unique-request")
    second = submit(user, problem, provider, request_key="unique-request")
    assert first.pk == second.pk and len(provider.calls) == 2
    record_submission_evidence(first)
    assert MasteryState.objects.get().evidence_count == 1
    assert LearningActivity.objects.count() == MasterySnapshot.objects.count() == 1


def test_recent_errors_reduce_rule_and_bkt_mastery(user, problem):
    submit(user, problem, Responses())
    before = MasteryState.objects.get()
    before_index, before_probability = before.index, before.bkt_probability
    for _ in range(3):
        submit(user, problem, Responses(correct=False))
    after = MasteryState.objects.get()
    assert after.index < before_index and after.bkt_probability < before_probability


def test_multiuser_submission_graph_mistake_isolation(user, problem, client):
    item = submit(user, problem, Responses(correct=False))
    stranger = get_user_model().objects.create_user(username="other", password="LongPassword123!")
    client.force_login(stranger)
    response = client.get(f"/api/v1/submissions/{item.pk}/")
    assert response.status_code == 404
    graph = client.get("/api/v1/graph/").json()["data"]
    assert all(node["status"] == "UNSEEN" for node in graph["nodes"])
    assert client.get("/api/v1/learning/mistakes/").json()["data"]["mistakes"] == []
    client.logout()
    assert client.get("/api/v1/graph/").status_code == 401


def test_api_invalid_id_and_malformed_json(user, client):
    client.force_login(user)
    assert client.post("/api/v1/code/submit/", data='{"problem_id":"invalid","code":"print(1)"}', content_type="application/json").status_code == 400
    assert client.post("/api/v1/code/submit/", data="[]", content_type="application/json").status_code == 400
    assert client.post("/api/v1/code/submit/", data="not json", content_type="application/json").status_code == 400
    assert client.post("/api/v1/code/submit/", data='{"problem_id":999,"code":"print(1)"}', content_type="application/json").status_code == 404


def test_run_requires_csrf_token(user):
    client = Client(enforce_csrf_checks=True)
    client.force_login(user)
    assert client.post("/api/v1/code/run/", data='{"code":"print(1)"}', content_type="application/json").status_code == 403


def test_rate_limit_applies_across_runs_and_submissions(user, problem, settings):
    from apps.problems.services.submission_service import run_code
    settings.EXECUTION_REQUESTS_PER_MINUTE = 2
    run_code(user, "print(1)", provider=Responses())
    submit(user, problem, Responses())
    with pytest.raises(CodeExecutionError, match="每分钟"):
        submit(user, problem, Responses())


def test_unexpected_upstream_response_becomes_judge_error(user, problem):
    class MalformedProvider:
        def run(self, *args):
            raise ValueError("secret upstream bad format")
    item = submit(user, problem, MalformedProvider())
    assert item.status == "JUDGE_ERROR"
    assert "secret" not in item.error_message
    assert not MasteryState.objects.exists()


def test_stale_pending_task_recovers_without_evidence(user, problem):
    from datetime import timedelta
    from apps.problems.services.submission_service import serialize_submission
    pending = Submission.objects.create(user=user, problem=problem, code="print(1)", request_key="interrupted")
    Submission.objects.filter(pk=pending.pk).update(created_at=timezone.now() - timedelta(minutes=10))
    pending.refresh_from_db()
    result = serialize_submission(pending)
    assert result["status"] == "JUDGE_ERROR" and not result["is_valid"]
    assert not MasteryState.objects.exists()


def test_hint_independence_lower_bound_from_saved_teaching_evidence(user, problem):
    from apps.tutor.models import ChatSession, TeachingSession
    session = ChatSession.objects.create(user=user)
    TeachingSession.objects.create(user=user, chat_session=session, problem=problem,
        provided_hints=[{"level": 2, "at": timezone.now().isoformat()}, {"level": 3, "at": timezone.now().isoformat()}])
    item = submit(user, problem, Responses(), hints_used=0)
    assert item.hints_used == 2
    state = MasteryState.objects.get(user=user)
    assert state.explanation["independence"] == pytest.approx(1/3, abs=.0001)


def test_invalid_dates_are_validation_errors(user, client):
    client.force_login(user)
    assert client.get("/api/v1/graph/?as_of=2026-99-99").status_code == 400
    assert client.get("/api/v1/learning/mistakes/?since=2026-99-99").status_code == 400


def test_ai_diagnosis_uses_real_evidence_and_never_changes_verdict(user, problem):
    import json
    from core.llm.provider import LLMResult, TokenUsage
    from apps.problems.services.diagnosis_service import diagnose_with_ai
    failed = submit(user, problem, Responses(correct=False))
    class DiagnosisProvider:
        def complete(self, messages, **kwargs):
            evidence = json.loads(messages[-1]["content"])
            assert evidence["observed_result"]["status"] == "WRONG_ANSWER"
            assert "SECRET_CASE_72" not in messages[-1]["content"]
            assert "secret answer" not in messages[-1]["content"]
            return LLMResult(text="检查反转指针后是否保存了原后继。", usage=TokenUsage(), model="test-only")
    result = diagnose_with_ai(user, failed.pk, 2, provider=DiagnosisProvider())
    failed.refresh_from_db()
    assert result["verdict"] == failed.status == "WRONG_ANSWER"
    assert "原后继" in MistakeRecord.objects.get(submission=failed).ai_diagnosis
    hint_events = LearningActivity.objects.filter(event_type="hint")
    assert hint_events.count() == 1 and hint_events.first().correct is None
    # Hint contact is not another graded response.
    assert MasteryState.objects.get(user=user).evidence_count == 1
    subsequent = submit(user, problem, Responses())
    assert subsequent.hints_used >= 1


def test_ai_diagnosis_rejects_infrastructure_failures_and_other_user(user, problem):
    from apps.problems.services.diagnosis_service import diagnose_with_ai
    from core.exceptions import ValidationError
    from django.core.exceptions import ObjectDoesNotExist
    item = submit(user, problem, Unavailable())
    with pytest.raises(ValidationError):
        diagnose_with_ai(user, item.pk, 1)
    other = get_user_model().objects.create_user(username="diagnosis-stranger")
    with pytest.raises(ObjectDoesNotExist):
        diagnose_with_ai(other, item.pk, 1)


def test_problem_queryset_search(user, problem):
    from apps.problems.services.problem_service import problem_queryset
    assert list(problem_queryset(query="反转")) == [problem]
    assert not problem_queryset(query="没有这个标题").exists()


@pytest.mark.django_db(transaction=True)
def test_concurrent_same_request_runs_once_and_updates_evidence_once(user, problem):
    import threading
    from concurrent.futures import ThreadPoolExecutor
    from django.db import close_old_connections
    entered = threading.Event()
    release = threading.Event()
    class BlockingProvider(Responses):
        def run(self, source, stdin, limits):
            if not self.calls:
                entered.set()
                assert release.wait(5)
            return super().run(source, stdin, limits)
    provider = BlockingProvider()
    def submit_in_connection():
        close_old_connections()
        try:
            current_user = get_user_model().objects.get(pk=user.pk)
            return submit_code(current_user, problem.pk, "print(input())", request_key="parallel-unique", provider=provider).pk
        finally:
            close_old_connections()
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(submit_in_connection)
        assert entered.wait(5)
        second = pool.submit(submit_in_connection)
        second_id = second.result(timeout=5)
        release.set()
        first_id = first.result(timeout=5)
    assert first_id == second_id
    assert len(provider.calls) == 2
    assert Submission.objects.count() == LearningActivity.objects.count() == MasterySnapshot.objects.count() == 1
    assert MasteryState.objects.get().evidence_count == 1


def test_historical_graph_recovers_real_state_and_regression(user, problem):
    from datetime import timedelta
    from apps.graph.services.graph_builder import get_graph
    accepted = submit(user, problem, Responses())
    first = MasterySnapshot.objects.get(submission=accepted)
    earlier = timezone.now() - timedelta(hours=2)
    MasterySnapshot.objects.filter(pk=first.pk).update(created_at=earlier)
    first_index = first.index
    for _ in range(3):
        submit(user, problem, Responses(correct=False))
    now_graph = get_graph(user)
    history_graph = get_graph(user, earlier + timedelta(seconds=1))
    current = next(node for node in now_graph["nodes"] if node["id"] == "linked-list")
    historic = next(node for node in history_graph["nodes"] if node["id"] == "linked-list")
    assert historic["index"] == first_index
    assert current["index"] < historic["index"]
    assert historic["evidence_count"] == 1


def test_unfinished_judge_has_no_fabricated_score_or_duration(user, problem):
    item = submit(user, problem, Unavailable())
    payload = serialize_submission(item)
    assert payload['status'] == 'JUDGE_ERROR'
    assert payload['status_label'] == '评测未完成'
    assert payload['evaluation_completed'] is False
    assert payload['passed_cases'] is None
    assert payload['elapsed_seconds'] is None
    assert payload['total_cases'] == 2
    assert payload['test_results'] == []
    assert not MasteryState.objects.filter(user=user).exists()
    assert not MistakeRecord.objects.filter(user=user).exists()


def test_history_does_not_show_zero_score_for_infrastructure_error(user, problem, client):
    item = submit(user, problem, Unavailable())
    client.force_login(user)
    response = client.get(f'/problems/{problem.slug}/')
    assert response.status_code == 200
    text = response.content.decode()
    assert '评测未完成' in text
    assert '无有效成绩' in text
    assert f'data-submission-result="{item.pk}"' in text
