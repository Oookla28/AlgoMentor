"""Transport adapter unit tests; HTTP is monkeypatched only in this test file."""
import pytest
from unittest.mock import patch
from core.execution.piston_client import PistonClient
from core.execution.judge0_client import Judge0Client
from core.execution.provider import ExecutionLimits, ExecutionResult, validate_program
from core.exceptions import CodeExecutionError, ValidationError

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize("stage,expected", [
    ({"code": 0, "stdout": "5\n", "stderr": ""}, "ACCEPTED"),
    ({"code": 1, "stdout": "", "stderr": "SyntaxError: error"}, "SYNTAX_ERROR"),
    ({"code": 1, "stdout": "", "stderr": "MemoryError"}, "MEMORY_LIMIT_EXCEEDED"),
    ({"code": None, "stdout": "", "stderr": "", "status": "TO"}, "TIME_LIMIT_EXCEEDED"),
    ({"code": 1, "stdout": "", "stderr": "ZeroDivisionError"}, "RUNTIME_ERROR"),
])
def test_piston_maps_real_execution_status_and_resource_payload(stage, expected):
    with patch("core.execution.piston_client.request_json", return_value={"run": stage}) as http:
        outcome = PistonClient("https://approved.example/api/v2", "token").run("print(5)", "input", ExecutionLimits(time_seconds=1, memory_mb=64))
    assert outcome.status == expected
    assert http.call_args.kwargs["payload"]["run_memory_limit"] == 64 * 1024 * 1024
    assert http.call_args.kwargs["payload"]["run_timeout"] == 1000
    assert http.call_args.kwargs["headers"] == {"Authorization": "Bearer token"}


def test_piston_stdout_cap_and_internal_service_failure():
    with patch("core.execution.piston_client.request_json", return_value={"run": {"code": 0, "stdout": "a" * 10000, "stderr": ""}}):
        outcome = PistonClient().run("print('a')")
        assert len(outcome.stdout.encode()) <= 8192 and outcome.output_truncated
        assert outcome.status == "RUNTIME_ERROR"
    with patch("core.execution.piston_client.request_json", return_value={"run": {"status": "XX"}}):
        with pytest.raises(CodeExecutionError):
            PistonClient().run("print(5)")


def test_piston_independent_cpu_budget_and_remote_timeout_metadata():
    stage = {"code": None, "stdout": "", "stderr": "", "status": "TO", "signal": "SIGKILL",
             "message": "Time limit exceeded", "cpu_time": 1010, "wall_time": 1100}
    with patch("core.execution.piston_client.request_json", return_value={"run": stage}) as http:
        outcome = PistonClient().run("while True: pass", limits=ExecutionLimits(time_seconds=3, cpu_seconds=1))
    payload = http.call_args.kwargs["payload"]
    assert payload["run_timeout"] == 3000 and payload["run_cpu_time"] == 1000
    assert outcome.cpu_seconds == 1.01 and outcome.elapsed_seconds == 1.1
    assert outcome.remote_status == "TO" and outcome.remote_message == "Time limit exceeded"
    assert outcome.signal == "SIGKILL"
    assert outcome.to_dict()["cpu_seconds"] == 1.01


def test_piston_missing_cpu_metadata_stays_unknown():
    with patch("core.execution.piston_client.request_json", return_value={"run": {"code": 0, "stdout": "5\n", "stderr": ""}}):
        outcome = PistonClient().run("print(5)")
    assert outcome.cpu_seconds is None and outcome.remote_status is None
    assert outcome.remote_message is None and outcome.signal is None


def test_execution_dataclasses_preserve_existing_positional_arguments():
    limits = ExecutionLimits(1, 64, 1024, 2000, 3000)
    assert (limits.time_seconds, limits.memory_mb, limits.output_bytes, limits.code_bytes, limits.stdin_bytes) == (1, 64, 1024, 2000, 3000)
    assert limits.cpu_seconds is None
    outcome = ExecutionResult("ACCEPTED", "5\n", "", 0.01, 100, "piston", 0, True)
    assert outcome.output_truncated is True and outcome.exit_code == 0
    assert outcome.cpu_seconds is None and outcome.remote_status is None


def test_judge0_async_polling_and_disabled_network():
    responses = [{"token": "sample-token"}, {"status": {"id": 1}}, {"status": {"id": 3}, "stdout": "5\n", "time": "0.01", "memory": 100}]
    with patch("core.execution.judge0_client.request_json", side_effect=responses) as http, patch("core.execution.judge0_client.time.sleep"):
        outcome = Judge0Client("https://approved.example", "token").run("print(5)")
    assert outcome.stdout == "5\n" and outcome.status == "ACCEPTED"
    assert http.call_args_list[0].kwargs["payload"]["enable_network"] is False
    assert "wait=false" in http.call_args_list[0].args[1]


def test_empty_nonstring_oversize_code_or_stdin_rejected():
    for source, stdin in [("", ""), (None, ""), ("a" * 20001, ""), ("print(1)", "a" * 20001), ("print(1)", {})]:
        with pytest.raises(ValidationError):
            validate_program(source, stdin, ExecutionLimits())
