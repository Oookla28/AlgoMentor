"""Explicit external-service validation, never execute curriculum code locally."""
import json
from django.core.management.base import BaseCommand
from apps.problems.models import Problem
from apps.problems.services.judge_service import judge_problem
from core.execution.provider import get_execution_provider
from core.exceptions import CodeExecutionError


class Command(BaseCommand):
    help = "Remote-judge all trusted reference solutions; do not create student evidence."

    def add_arguments(self, parser):
        parser.add_argument("--output", default="tests/evaluation/problem_bank_results.json")

    def handle(self, *args, **options):
        from pathlib import Path
        from django.utils import timezone
        results = []
        provider = get_execution_provider()
        for problem in Problem.objects.filter(is_active=True):
            try:
                outcome = judge_problem(problem, problem.reference_solution, provider)
                row = {"problem": problem.slug, "status": outcome.status, "passed": outcome.passed_cases, "total": outcome.total_cases}
            except CodeExecutionError as exc:
                row = {"problem": problem.slug, "status": "UNVERIFIED", "error_code": exc.code, "message": exc.message}
            results.append(row)
            self.stdout.write(json.dumps(row, ensure_ascii=False))
            if row["status"] == "UNVERIFIED":
                break
        output = Path(options["output"])
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps({"time": timezone.now().isoformat(), "kind": "live_remote_evaluation", "results": results}, ensure_ascii=False, indent=2))
        if any(row["status"] != "ACCEPTED" for row in results):
            self.stderr.write("存在失败或未经真实执行验证的题目；查看结果文件。")
