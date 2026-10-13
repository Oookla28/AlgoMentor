"""Known-result remote experiment: raw responses retained without student data."""
import json
from pathlib import Path
from django.core.management.base import BaseCommand
from django.utils import timezone
from core.execution.provider import get_execution_provider, ExecutionLimits
from core.exceptions import CodeExecutionError
from apps.problems.services.judge_service import normalize_output

# All programs are fixed, reviewed fixtures. They are ONLY sent to a remote sandbox.
EXPERIMENTS = [
    {"id": "correct", "code": "n=int(input()); print(n*(n+1)//2)", "stdin": "4\n", "expected_stdout": "10\n", "expected_verdict": "ACCEPTED"},
    {"id": "wrong_answer", "code": "print(9)", "stdin": "4\n", "expected_stdout": "10\n", "expected_verdict": "WRONG_ANSWER"},
    {"id": "syntax_error", "code": "print(\n", "stdin": "", "expected_stdout": "", "expected_verdict": "SYNTAX_ERROR"},
    {"id": "runtime_error", "code": "print(1//0)", "stdin": "", "expected_stdout": "", "expected_verdict": "RUNTIME_ERROR"},
    {"id": "timeout", "code": "while True: pass", "stdin": "", "expected_stdout": "", "expected_verdict": "TIME_LIMIT_EXCEEDED"},
    {"id": "boundary_error", "code": "a=list(map(int,input().split())); print(a[0])", "stdin": "\n", "expected_stdout": "", "expected_verdict": "RUNTIME_ERROR"},
]


class Command(BaseCommand):
    help = "Run known-result experiments against the configured real sandbox. No local execution."

    def add_arguments(self, parser):
        parser.add_argument("--output", default="tests/evaluation/judge_results.json")

    def handle(self, *args, **options):
        provider = get_execution_provider()
        results = []
        for item in EXPERIMENTS:
            try:
                execution = provider.run(item["code"], item["stdin"], ExecutionLimits(time_seconds=1))
                observed = execution.status
                if observed == "ACCEPTED" and normalize_output(execution.stdout) != normalize_output(item["expected_stdout"]):
                    observed = "WRONG_ANSWER"
                row = {**item, "observed_verdict": observed, "matches_expected": observed == item["expected_verdict"], "raw_execution": execution.to_dict()}
            except CodeExecutionError as exc:
                row = {**item, "observed_verdict": "UNVERIFIED", "matches_expected": None, "error_code": exc.code, "message": exc.message}
            results.append(row)
        verified = [row for row in results if row["matches_expected"] is not None]
        payload = {"executed_at": timezone.now().isoformat(), "experiment": "live_remote_judge", "results": results,
                   "verified_cases": len(verified), "agreement": sum(row["matches_expected"] for row in verified) / len(verified) if verified else None}
        output = Path(options["output"])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2))
        self.stdout.write(json.dumps({"output": str(output), "verified_cases": len(verified), "agreement": payload["agreement"]}, ensure_ascii=False))
