import ast
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from apps.problems.models import Problem, TestCase, ProblemKnowledgePoint
from apps.knowledge.models import KnowledgePoint
from apps.problems.services.seed_catalog import CATALOG


class Command(BaseCommand):
    help = "Initialize original course exercises idempotently; retain real submissions."

    @transaction.atomic
    def handle(self, *args, **options):
        points = {point.slug: point for point in KnowledgePoint.objects.all()}
        missing = sorted({tag for item in CATALOG for tag in item["tags"] if tag not in points})
        if missing:
            raise CommandError("先执行 seed_knowledge：缺少知识点 " + ", ".join(missing))
        count = 0
        for item in CATALOG:
            ast.parse(item["reference_solution"])  # syntax checking only; no local execution
            fields = {key: value for key, value in item.items() if key not in ("slug", "tags", "cases")}
            fields["examples"] = [{"input": item["cases"][0][0], "output": item["cases"][0][1]}]
            problem, _ = Problem.objects.update_or_create(slug=item["slug"], defaults=fields)
            for tag in item["tags"]:
                ProblemKnowledgePoint.objects.get_or_create(problem=problem, knowledge_point=points[tag])
            for sequence, (stdin, expected) in enumerate(item["cases"], 1):
                TestCase.objects.update_or_create(problem=problem, sequence=sequence,
                    defaults={"stdin": stdin, "expected_output": expected, "is_hidden": sequence != 1,
                              "description": "公开示例" if sequence == 1 else "服务端边界测试"})
            count += 1
        self.stdout.write(self.style.SUCCESS(f"题库初始化：{count} 题，{sum(len(item['cases']) for item in CATALOG)} 个测试用例。仅校验参考代码语法；远程真实评测须配置执行服务。"))
