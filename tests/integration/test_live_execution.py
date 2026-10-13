"""Opt-in actual local Piston API/learning flow, using only pytest's test DB."""
import os
import json

import pytest
from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management import call_command

from apps.learning.models import LearningActivity, MasteryState, MistakeRecord
from apps.problems.models import Problem, Submission


@pytest.mark.skipif(os.environ.get("ALGOMENTOR_LIVE_EXECUTION") != "1", reason="Requires explicit live local Piston test")
@pytest.mark.django_db
def test_real_sandbox_submit_updates_test_database_and_resolves_mistake(client):
    # Never send these programs to a public/shared endpoint by accident.
    assert settings.EXECUTION_PROVIDER == "piston"
    assert settings.PISTON_BASE_URL == "http://127.0.0.1:2000/api/v2"
    call_command("seed_knowledge")
    call_command("seed_problems")
    learner = get_user_model().objects.create_user(username="live_execution_test")
    client.force_login(learner)
    problem = Problem.objects.get(slug="triangular-count")

    def post(path, data):
        response = client.post(path, data=json.dumps(data), content_type="application/json")
        assert response.status_code == 200
        assert response.json()["success"] is True
        return response.json()["data"]

    result = post("/api/v1/code/run/", {"code": "n=int(input()); print(n*(n+1)//2)", "stdin": "4\n"})
    assert result["status"] == "ACCEPTED" and result["stdout"] == "10\n"
    assert Submission.objects.count() == LearningActivity.objects.count() == 0

    wrong = post("/api/v1/code/submit/", {"problem_id": problem.id, "code": "print(9)", "request_key": "live-wrong"})
    assert wrong["status"] == "WRONG_ANSWER" and wrong["evaluation_completed"] is True
    assert wrong["passed_cases"] == 0 and wrong["total_cases"] == 4
    mistake = MistakeRecord.objects.get(user=learner)
    assert not mistake.resolved
    assert all("stdout" not in case for case in wrong["test_results"] if case["hidden"])

    accepted_payload = {"problem_id": problem.id, "code": "n=int(input()); print(n*(n+1)//2)", "request_key": "live-correct"}
    correct = post("/api/v1/code/submit/", accepted_payload)
    assert correct["status"] == "ACCEPTED"
    assert correct["passed_cases"] == correct["total_cases"] == 4
    assert correct["elapsed_seconds"] > 0
    mistake.refresh_from_db()
    assert mistake.resolved and mistake.resolved_at
    states = MasteryState.objects.filter(user=learner)
    assert states.exists() and all(state.evidence_count == 2 for state in states)
    activities = LearningActivity.objects.count()
    duplicate = post("/api/v1/code/submit/", accepted_payload)
    assert duplicate["id"] == correct["id"]
    assert Submission.objects.count() == 2 and LearningActivity.objects.count() == activities

    other = get_user_model().objects.create_user(username="other_live_execution_test")
    client.force_login(other)
    assert client.get(f'/api/v1/submissions/{correct["id"]}/').status_code == 404
    assert not MasteryState.objects.filter(user=other).exists()
