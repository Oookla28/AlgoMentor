"""Exercise fixed isolation probes only through the configured remote sandbox.

The strings below are never evaluated or spawned by Django.  A failed transport,
an ambiguous result, or a probe that could not run is UNVERIFIED, never PASS.
Only synthetic markers and booleans are returned; host secret values are not read.
"""
import json
from dataclasses import asdict, dataclass
from pathlib import Path
from textwrap import dedent

from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone

from core.exceptions import CodeExecutionError
from core.execution.provider import (
    CodeExecutionProvider,
    ExecutionLimits,
    ExecutionResult,
    get_execution_provider,
)


HOST_SENTINEL_NAME = "isolation-host-sentinel-notsecret.txt"
HOST_SENTINEL_CONTENT = "ALGOMENTOR_SYNTHETIC_HOST_SENTINEL_NOTSECRET\n"
TEMP_MARKER = "/tmp/algomentor-isolation-marker-notsecret.txt"
CHECK_IDS = (
    "outbound_network", "host_files", "environment_secrets", "process_limit",
    "output_limit", "memory_limit", "wall_timeout", "cpu_timeout",
    "temporary_file_isolation",
)


@dataclass(frozen=True)
class Probe:
    id: str
    source: str
    limits: ExecutionLimits = ExecutionLimits()


def fixed_probe(identifier: str, source: str, **limits) -> Probe:
    return Probe(identifier, f"# AlgoMentor fixed isolation probe: {identifier}\n" + dedent(source).strip() + "\n", ExecutionLimits(**limits))


def probes_for(host_sentinel_path: Path) -> tuple[Probe, ...]:
    """Only paths and known test text enter these reviewed programs."""
    project = Path(settings.BASE_DIR)
    paths = [str(host_sentinel_path), str(project / ".env"), str(project / "data/db.sqlite3")]
    return (
        fixed_probe("outbound_network", """
            import json, socket
            try:
                with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as client:
                    client.settimeout(1)
                    client.connect(("1.1.1.1", 443))
                print(json.dumps({"connected": True}))
            except OSError as error:
                print(json.dumps({"connected": False, "errno": error.errno,
                                  "timed_out": isinstance(error, TimeoutError)}))
        """, time_seconds=2),
        fixed_probe("host_files", f"""
            import json
            paths = {json.dumps(paths, ensure_ascii=True)}
            readable = []
            for path in paths:
                try:
                    with open(path, "rb"):
                        readable.append(True)
                except OSError:
                    readable.append(False)
            print(json.dumps({{"readable": readable}}))
        """),
        fixed_probe("environment_secrets", """
            import json, os
            names = ("DJANGO_SECRET_KEY", "APP_ENCRYPTION_KEY")
            print(json.dumps({"present": {name: name in os.environ for name in names}}))
        """),
        fixed_probe("process_limit", """
            import errno, json, resource, subprocess, sys
            soft, hard = resource.getrlimit(resource.RLIMIT_NPROC)
            children, denied_errno = [], None
            exercised = 0 < soft <= 24
            try:
                if exercised:
                    # At most 26 direct children, no child forks, no recursive bomb.
                    for _ in range(int(soft) + 2):
                        try:
                            children.append(subprocess.Popen(
                                [sys.executable, "-c", "import time; time.sleep(5)"],
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL))
                        except OSError as error:
                            denied_errno = error.errno
                            break
            finally:
                for child in children:
                    child.terminate()
                for child in children:
                    try:
                        child.wait(timeout=0.5)
                    except subprocess.TimeoutExpired:
                        child.kill()
                        child.wait(timeout=0.5)
            print(json.dumps({"soft_limit": soft, "hard_limit": hard,
                              "exercised": exercised, "spawned": len(children),
                              "denied_errno": denied_errno}))
        """, time_seconds=3),
        fixed_probe("output_limit", """
            import sys, time
            print("ALGOMENTOR_OUTPUT_PROBE", flush=True)
            time.sleep(0.05)
            for _ in range(64):
                sys.stdout.write("X" * 1024)
                sys.stdout.flush()
            print("ALGOMENTOR_OUTPUT_FINISHED", flush=True)
        """, output_bytes=8192),
        fixed_probe("memory_limit", """
            # A fixed 200 MiB allocation, below the VM's capacity, above 128 MiB.
            allocation = bytearray(200 * 1024 * 1024)
            print("ALGOMENTOR_200M_ALLOCATION_SUCCEEDED")
        """, time_seconds=2, memory_mb=128),
        fixed_probe("wall_timeout", """
            import time
            time.sleep(5)
            print("ALGOMENTOR_WALL_TIMEOUT_FAILED")
        """, time_seconds=1),
        fixed_probe("cpu_timeout", """
            while True:
                pass
        """, time_seconds=3, cpu_seconds=1),
        fixed_probe("temporary_file_write", f"""
            from pathlib import Path
            marker = Path({json.dumps(TEMP_MARKER)})
            marker.write_text("ALGOMENTOR_TEMP_MARKER_NOTSECRET")
            print("ALGOMENTOR_TEMP_MARKER_WRITTEN")
        """),
        fixed_probe("temporary_file_read", f"""
            import json
            from pathlib import Path
            print(json.dumps({{"marker_exists": Path({json.dumps(TEMP_MARKER)}).exists()}}))
        """),
    )


def result_json(result: ExecutionResult) -> dict | None:
    if result.status != "ACCEPTED" or result.output_truncated:
        return None
    try:
        value = json.loads(result.stdout)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


def assess(probe: Probe, result: ExecutionResult) -> tuple[str, str]:
    data = result_json(result)
    if probe.id == "outbound_network" and data is not None:
        if data.get("connected") is True:
            return "FAIL", "The fixed external TCP connection succeeded."
        if data.get("connected") is False and data.get("errno") in (1, 13, 99, 101):
            return "PASS", "The kernel denied the fixed external TCP connection."
        return "UNVERIFIED", "A timeout or refusal alone does not prove network isolation."
    if probe.id == "host_files" and data is not None:
        readable = data.get("readable")
        if isinstance(readable, list) and len(readable) == 3 and all(type(value) is bool for value in readable):
            return ("FAIL", "The sandbox could open a protected host path.") if any(readable) else ("PASS", "The host sentinel, application environment file, and SQLite path were unreadable.")
    if probe.id == "environment_secrets" and data is not None:
        present = data.get("present")
        names = {"DJANGO_SECRET_KEY", "APP_ENCRYPTION_KEY"}
        if isinstance(present, dict) and set(present) == names and all(type(value) is bool for value in present.values()):
            return ("FAIL", "An application secret variable name reached the sandbox.") if any(present.values()) else ("PASS", "Neither application secret variable name was present; values were never printed.")
    if probe.id == "process_limit" and data is not None:
        soft, spawned = data.get("soft_limit"), data.get("spawned")
        if type(soft) is int and 0 < soft <= 24 and data.get("exercised") is True and type(spawned) is int and 0 <= spawned <= 26:
            if data.get("denied_errno") == 11:
                return "PASS", "The bounded child-process probe reached the kernel process limit (EAGAIN)."
            if data.get("denied_errno") is None and spawned == soft + 2:
                return "FAIL", "The bounded probe exceeded the reported process limit without denial."
        return "UNVERIFIED", "The process cap was not demonstrated within the safe bound of 26 direct children."
    if probe.id == "output_limit":
        bounded = len(result.stdout.encode()) <= probe.limits.output_bytes and len(result.stderr.encode()) <= probe.limits.output_bytes
        if result.status == "RUNTIME_ERROR" and bounded and (result.output_truncated or result.stdout.startswith("ALGOMENTOR_OUTPUT_PROBE")):
            return "PASS", "Excess output was rejected or truncated and returned within the application cap."
        if result.status == "ACCEPTED" and "ALGOMENTOR_OUTPUT_FINISHED" in result.stdout:
            return "FAIL", "The output-producing program completed without enforcing the configured cap."
    if probe.id == "memory_limit":
        if result.status == "MEMORY_LIMIT_EXCEEDED":
            return "PASS", "The fixed 200 MiB allocation exceeded the 128 MiB memory limit."
        if result.status == "ACCEPTED" and "ALGOMENTOR_200M_ALLOCATION_SUCCEEDED" in result.stdout:
            return "FAIL", "The fixed 200 MiB allocation succeeded under a 128 MiB limit."
        return "UNVERIFIED", "A generic process kill or runtime error alone is insufficient evidence of the memory limit."
    if probe.id == "cpu_timeout":
        budget = probe.limits.cpu_seconds
        cpu = result.cpu_seconds
        if result.status == "ACCEPTED":
            return "FAIL", "The fixed infinite CPU loop was allowed to complete."
        if budget is not None and cpu is not None and cpu > budget + 0.5:
            return "FAIL", "The measured CPU use exceeded the independent CPU budget and tolerance."
        message = (result.remote_message or "").strip().lower()
        if (result.status == "TIME_LIMIT_EXCEEDED" and result.remote_status == "TO"
                and message == "time limit exceeded" and budget is not None
                and cpu is not None and max(0, budget - 0.1) <= cpu <= budget + 0.5
                and 0 < result.elapsed_seconds < probe.limits.time_seconds):
            return "PASS", "The sandbox reported a CPU timeout near one CPU second, before its separate three-second wall limit."
        return "UNVERIFIED", "A wall-clock timeout, missing CPU measurement, or ambiguous timeout message does not independently verify the CPU budget."
    if probe.id == "wall_timeout":
        if result.status == "TIME_LIMIT_EXCEEDED" and result.elapsed_seconds <= 3:
            return "PASS", "The fixed program hit the requested one-second execution limit."
        if result.status == "ACCEPTED" or result.elapsed_seconds > 3:
            return "FAIL", "The requested one-second execution limit was not demonstrated within three seconds."
    return "UNVERIFIED", "The sandbox did not return an unambiguous result for this probe."


def unverified_row(identifier: str, error_code: str, message: str) -> dict:
    return {"id": identifier, "verdict": "UNVERIFIED", "reason": message, "error_code": error_code, "raw_executions": []}


def run_isolation_suite(provider: CodeExecutionProvider, *, sentinel_path: Path) -> dict:
    """Inject a provider explicitly in unit tests; production uses the real adapter."""
    rows = []
    written = None
    sentinel_created = False
    host_precondition = False
    try:
        sentinel_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            # Refuse to overwrite an existing file and only remove what we created.
            with sentinel_path.open("x", encoding="utf-8") as sentinel:
                sentinel.write(HOST_SENTINEL_CONTENT)
            sentinel_created = True
            host_precondition = sentinel_path.is_file()
        except OSError:
            host_precondition = False
        for probe in probes_for(sentinel_path):
            identifier = "temporary_file_isolation" if probe.id.startswith("temporary_file_") else probe.id
            if probe.id == "host_files" and not host_precondition:
                rows.append(unverified_row(identifier, "HOST_SENTINEL_UNAVAILABLE", "The synthetic host sentinel could not be created and verified."))
                continue
            try:
                result = provider.run(probe.source, "", probe.limits)
            except CodeExecutionError as error:
                row = unverified_row(identifier, error.code, error.message)
                if probe.id == "temporary_file_write":
                    written = row
                    continue
                if probe.id == "temporary_file_read" and written is not None:
                    row["raw_executions"] = written["raw_executions"]
                rows.append(row)
                continue
            raw = {"probe_id": probe.id, "requested_limits": asdict(probe.limits), "result": result.to_dict()}
            if probe.id == "temporary_file_write":
                written = {"confirmed": result.status == "ACCEPTED" and result.stdout.strip() == "ALGOMENTOR_TEMP_MARKER_WRITTEN", "raw_executions": [raw]}
                continue
            if probe.id == "temporary_file_read":
                data = result_json(result)
                verdict, reason = "UNVERIFIED", "The initial sandbox write or the subsequent existence check was not confirmed."
                if written and written.get("confirmed") and data is not None and type(data.get("marker_exists")) is bool:
                    verdict = "FAIL" if data["marker_exists"] else "PASS"
                    reason = "The fixed temporary marker persisted across executions." if data["marker_exists"] else "The confirmed temporary marker was absent in a separate execution."
                rows.append({"id": identifier, "verdict": verdict, "reason": reason, "raw_executions": (written or {}).get("raw_executions", []) + [raw]})
                continue
            verdict, reason = assess(probe, result)
            row = {"id": identifier, "verdict": verdict, "reason": reason, "raw_executions": [raw]}
            if probe.id == "host_files":
                row["host_sentinel_confirmed_before_probe"] = True
                row["protected_paths"] = [str(sentinel_path), str(Path(settings.BASE_DIR) / ".env"), str(Path(settings.BASE_DIR) / "data/db.sqlite3")]
            rows.append(row)
    finally:
        if sentinel_created:
            sentinel_path.unlink(missing_ok=True)
    return summarize(rows)


def summarize(rows: list[dict]) -> dict:
    counts = {verdict: sum(row["verdict"] == verdict for row in rows) for verdict in ("PASS", "FAIL", "UNVERIFIED")}
    return {"schema_version": 1, "experiment": "live_remote_isolation", "executed_at": timezone.now().isoformat(),
            "fixed_programs_only": True, "host_code_execution": False,
            "results": rows, "counts": counts,
            "all_passed": len(rows) == len(CHECK_IDS) and counts["PASS"] == len(CHECK_IDS)}


class Command(BaseCommand):
    help = "Send bounded, fixed probes to the configured isolated Piston; retain honest PASS/FAIL/UNVERIFIED evidence."

    def add_arguments(self, parser):
        parser.add_argument("--output", default="tests/evaluation/isolation_results.json")

    def handle(self, *args, **options):
        try:
            if settings.EXECUTION_PROVIDER != "piston":
                raise CodeExecutionError("This verification command requires the configured Piston provider.", code="EXECUTION_NOT_PISTON")
            provider = get_execution_provider()
            payload = run_isolation_suite(provider, sentinel_path=Path(settings.BASE_DIR) / "tests/evaluation" / HOST_SENTINEL_NAME)
        except CodeExecutionError as error:
            payload = summarize([unverified_row(identifier, error.code, error.message) for identifier in CHECK_IDS])
        output = Path(options["output"])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        self.stdout.write(json.dumps({"output": str(output), "counts": payload["counts"], "all_passed": payload["all_passed"]}, ensure_ascii=False))
