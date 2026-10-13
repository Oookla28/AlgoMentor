"""Unit tests inject result-only providers; fixed probe source is never run locally."""
import json
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import pytest
from django.core.management import call_command
from django.test import override_settings

from apps.problems.management.commands.verify_execution_isolation import (
    CHECK_IDS, HOST_SENTINEL_CONTENT, HOST_SENTINEL_NAME, assess, probes_for,
    run_isolation_suite,
)
from core.exceptions import CodeExecutionError
from core.execution.provider import ExecutionResult


def accepted(data):
    return ExecutionResult("ACCEPTED", stdout=json.dumps(data), provider="piston", exit_code=0)


PASS_RESULTS = {
    "outbound_network": accepted({"connected": False, "errno": 101, "timed_out": False}),
    "host_files": accepted({"readable": [False, False, False]}),
    "environment_secrets": accepted({"present": {"DJANGO_SECRET_KEY": False, "APP_ENCRYPTION_KEY": False}}),
    "process_limit": accepted({"soft_limit": 16, "hard_limit": 16, "exercised": True, "spawned": 14, "denied_errno": 11}),
    "output_limit": ExecutionResult("RUNTIME_ERROR", stdout="ALGOMENTOR_OUTPUT_PROBE\n" + "X" * 8000, provider="piston", output_truncated=True),
    "memory_limit": ExecutionResult("MEMORY_LIMIT_EXCEEDED", stderr="MemoryError", provider="piston", exit_code=1),
    "wall_timeout": ExecutionResult("TIME_LIMIT_EXCEEDED", elapsed_seconds=1.01, provider="piston"),
    "cpu_timeout": ExecutionResult("TIME_LIMIT_EXCEEDED", elapsed_seconds=1.1, provider="piston", cpu_seconds=1.01, remote_status="TO", remote_message="Time limit exceeded", signal="SIGKILL"),
    "temporary_file_write": ExecutionResult("ACCEPTED", stdout="ALGOMENTOR_TEMP_MARKER_WRITTEN\n", provider="piston", exit_code=0),
    "temporary_file_read": accepted({"marker_exists": False}),
}


class InjectedSandboxProvider:
    def __init__(self, responses=None, sentinel_path=None):
        self.responses = {**PASS_RESULTS, **(responses or {})}
        self.calls = []
        self.sentinel_path = sentinel_path

    def run(self, source, stdin="", limits=None):
        identifier = source.splitlines()[0].split(": ", 1)[1]
        self.calls.append((identifier, source, stdin, limits))
        if self.sentinel_path:
            assert self.sentinel_path.read_text() == HOST_SENTINEL_CONTENT
        response = self.responses[identifier]
        if isinstance(response, Exception):
            raise response
        return response


def test_complete_suite_has_nine_checks_ten_remote_calls_and_cleans_host_sentinel(tmp_path):
    sentinel = tmp_path / HOST_SENTINEL_NAME
    provider = InjectedSandboxProvider(sentinel_path=sentinel)
    report = run_isolation_suite(provider, sentinel_path=sentinel)
    assert report["all_passed"] is True
    assert report["counts"] == {"PASS": 9, "FAIL": 0, "UNVERIFIED": 0}
    assert tuple(row["id"] for row in report["results"]) == CHECK_IDS
    assert len(provider.calls) == 10 and all(call[2] == "" for call in provider.calls)
    assert not sentinel.exists()
    host = next(row for row in report["results"] if row["id"] == "host_files")
    assert host["host_sentinel_confirmed_before_probe"] is True
    assert host["raw_executions"][0]["result"]["stdout"] == '{"readable": [false, false, false]}'


@pytest.mark.parametrize("identifier,response,verdict", [
    ("outbound_network", accepted({"connected": True}), "FAIL"),
    ("outbound_network", accepted({"connected": False, "errno": None, "timed_out": True}), "UNVERIFIED"),
    ("outbound_network", accepted({"connected": False, "errno": 111}), "UNVERIFIED"),
    ("host_files", accepted({"readable": [True, False, False]}), "FAIL"),
    ("host_files", accepted({"readable": [0, 0, 0]}), "UNVERIFIED"),
    ("environment_secrets", accepted({"present": {"DJANGO_SECRET_KEY": True, "APP_ENCRYPTION_KEY": False}}), "FAIL"),
    ("environment_secrets", accepted({"present": {}}), "UNVERIFIED"),
    ("process_limit", accepted({"soft_limit": 16, "hard_limit": 16, "exercised": True, "spawned": 18, "denied_errno": None}), "FAIL"),
    ("process_limit", accepted({"soft_limit": -1, "hard_limit": -1, "exercised": False, "spawned": 0, "denied_errno": None}), "UNVERIFIED"),
    ("process_limit", accepted({"soft_limit": 64, "hard_limit": 64, "exercised": False, "spawned": 0, "denied_errno": None}), "UNVERIFIED"),
    ("memory_limit", ExecutionResult("RUNTIME_ERROR", memory_kb=131072, exit_code=None), "UNVERIFIED"),
    ("memory_limit", ExecutionResult("ACCEPTED", stdout="ALGOMENTOR_200M_ALLOCATION_SUCCEEDED"), "FAIL"),
    ("wall_timeout", ExecutionResult("TIME_LIMIT_EXCEEDED", elapsed_seconds=5), "FAIL"),
    ("cpu_timeout", ExecutionResult("RUNTIME_ERROR"), "UNVERIFIED"),
    ("cpu_timeout", ExecutionResult("TIME_LIMIT_EXCEEDED", elapsed_seconds=1.01), "UNVERIFIED"),
    ("cpu_timeout", ExecutionResult("TIME_LIMIT_EXCEEDED", elapsed_seconds=3.1, cpu_seconds=0.7, remote_status="TO", remote_message="Time limit exceeded (wall clock)"), "UNVERIFIED"),
    ("cpu_timeout", ExecutionResult("TIME_LIMIT_EXCEEDED", elapsed_seconds=3.1, cpu_seconds=2.9, remote_status="TO", remote_message="Time limit exceeded (wall clock)"), "FAIL"),
    ("cpu_timeout", ExecutionResult("TIME_LIMIT_EXCEEDED", elapsed_seconds=1.1, cpu_seconds=1.01, remote_status="TO", remote_message="Time limit exceeded (wall clock)"), "UNVERIFIED"),
    ("cpu_timeout", ExecutionResult("TIME_LIMIT_EXCEEDED", elapsed_seconds=1.1, cpu_seconds=1.01, remote_status="TO", remote_message=None), "UNVERIFIED"),
    ("cpu_timeout", ExecutionResult("TIME_LIMIT_EXCEEDED", elapsed_seconds=1.1, cpu_seconds=0.01, remote_status="TO", remote_message="Time limit exceeded"), "UNVERIFIED"),
    ("output_limit", ExecutionResult("ACCEPTED", stdout="ALGOMENTOR_OUTPUT_FINISHED"), "FAIL"),
    ("output_limit", ExecutionResult("RUNTIME_ERROR", stderr="Unknown error"), "UNVERIFIED"),
])
def test_assessment_requires_positive_unambiguous_evidence(tmp_path, identifier, response, verdict):
    probe = next(probe for probe in probes_for(tmp_path / HOST_SENTINEL_NAME) if probe.id == identifier)
    assert assess(probe, response)[0] == verdict


def test_all_infrastructure_failures_remain_unverified(tmp_path):
    error = CodeExecutionError("Unavailable", code="EXECUTION_UNAVAILABLE")
    provider = InjectedSandboxProvider({identifier: error for identifier in PASS_RESULTS})
    report = run_isolation_suite(provider, sentinel_path=tmp_path / HOST_SENTINEL_NAME)
    assert report["counts"] == {"PASS": 0, "FAIL": 0, "UNVERIFIED": 9}
    assert report["all_passed"] is False
    assert all(row["error_code"] == "EXECUTION_UNAVAILABLE" for row in report["results"])


def test_temp_isolation_cannot_pass_without_successful_initial_write(tmp_path):
    provider = InjectedSandboxProvider({"temporary_file_write": CodeExecutionError("Unavailable", code="EXECUTION_UNAVAILABLE")})
    report = run_isolation_suite(provider, sentinel_path=tmp_path / HOST_SENTINEL_NAME)
    assert report["results"][-1]["verdict"] == "UNVERIFIED"
    assert len(report["results"][-1]["raw_executions"]) == 1


def test_temp_file_leak_is_failure(tmp_path):
    provider = InjectedSandboxProvider({"temporary_file_read": accepted({"marker_exists": True})})
    report = run_isolation_suite(provider, sentinel_path=tmp_path / HOST_SENTINEL_NAME)
    assert report["results"][-1]["verdict"] == "FAIL"
    assert len(report["results"][-1]["raw_executions"]) == 2


def test_existing_host_sentinel_is_preserved_and_host_check_unverified(tmp_path):
    sentinel = tmp_path / HOST_SENTINEL_NAME
    sentinel.write_text("PREEXISTING_FILE")
    provider = InjectedSandboxProvider()
    report = run_isolation_suite(provider, sentinel_path=sentinel)
    host = next(row for row in report["results"] if row["id"] == "host_files")
    assert host["verdict"] == "UNVERIFIED"
    assert host["error_code"] == "HOST_SENTINEL_UNAVAILABLE"
    assert sentinel.read_text() == "PREEXISTING_FILE"
    assert "host_files" not in [call[0] for call in provider.calls]


def test_fixed_probe_resource_requests_and_no_secret_values(tmp_path):
    probes = {probe.id: probe for probe in probes_for(tmp_path / HOST_SENTINEL_NAME)}
    assert probes["memory_limit"].limits.memory_mb == 128
    assert "200 * 1024 * 1024" in probes["memory_limit"].source
    assert probes["wall_timeout"].limits.time_seconds == 1
    assert probes["cpu_timeout"].limits.time_seconds == 3
    assert probes["cpu_timeout"].limits.cpu_seconds == 1
    assert probes["output_limit"].limits.output_bytes == 8192
    assert "0 < soft <= 24" in probes["process_limit"].source
    assert "soft) + 2" in probes["process_limit"].source
    assert ".read(" not in probes["host_files"].source
    assert "name in os.environ" in probes["environment_secrets"].source
    assert "os.environ[" not in probes["environment_secrets"].source


def test_management_command_uses_explicitly_injected_provider_and_saves_evidence(tmp_path):
    provider = InjectedSandboxProvider()
    output = tmp_path / "isolation_results.json"
    with override_settings(BASE_DIR=tmp_path, EXECUTION_PROVIDER="piston"), patch(
        "apps.problems.management.commands.verify_execution_isolation.get_execution_provider", return_value=provider
    ):
        call_command("verify_execution_isolation", output=str(output), stdout=StringIO())
    assert json.loads(output.read_text())["all_passed"] is True
    assert not (tmp_path / "tests/evaluation" / HOST_SENTINEL_NAME).exists()


def test_invalid_provider_configuration_is_not_a_false_pass(tmp_path):
    output = tmp_path / "isolation_results.json"
    with override_settings(EXECUTION_PROVIDER="judge0"):
        call_command("verify_execution_isolation", output=str(output), stdout=StringIO())
    report = json.loads(output.read_text())
    assert report["counts"] == {"PASS": 0, "FAIL": 0, "UNVERIFIED": 9}
    assert all(row["error_code"] == "EXECUTION_NOT_PISTON" for row in report["results"])
