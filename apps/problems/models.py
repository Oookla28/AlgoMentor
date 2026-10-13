from django.conf import settings
from django.db import models
from django.core.validators import MinValueValidator, MaxValueValidator


class Problem(models.Model):
    slug = models.SlugField(unique=True)
    title = models.CharField(max_length=160)
    description = models.TextField()
    difficulty = models.PositiveSmallIntegerField(default=1, validators=[MinValueValidator(1), MaxValueValidator(3)])
    input_description = models.TextField()
    output_description = models.TextField()
    examples = models.JSONField(default=list)
    reference_solution = models.TextField()
    reference_complexity = models.CharField(max_length=160)
    source = models.CharField(max_length=240, default="据课程原文设计的原创练习")
    knowledge_points = models.ManyToManyField("knowledge.KnowledgePoint", through="ProblemKnowledgePoint", related_name="problems")
    time_limit_seconds = models.FloatField(default=2)
    memory_limit_mb = models.PositiveIntegerField(default=128)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["id"]

    def __str__(self):
        return self.title


class ProblemKnowledgePoint(models.Model):
    problem = models.ForeignKey(Problem, on_delete=models.CASCADE)
    knowledge_point = models.ForeignKey("knowledge.KnowledgePoint", on_delete=models.CASCADE)
    weight = models.FloatField(default=1.0)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["problem", "knowledge_point"], name="unique_problem_point")]


class TestCase(models.Model):
    problem = models.ForeignKey(Problem, on_delete=models.CASCADE, related_name="test_cases")
    sequence = models.PositiveIntegerField()
    stdin = models.TextField()
    expected_output = models.TextField()
    is_hidden = models.BooleanField(default=True)
    description = models.CharField(max_length=160, blank=True)

    class Meta:
        ordering = ["sequence"]
        constraints = [models.UniqueConstraint(fields=["problem", "sequence"], name="unique_problem_case")]


class Submission(models.Model):
    class Status(models.TextChoices):
        PENDING = "PENDING", "等待评测"
        ACCEPTED = "ACCEPTED", "Accepted"
        WRONG_ANSWER = "WRONG_ANSWER", "Wrong Answer"
        RUNTIME_ERROR = "RUNTIME_ERROR", "Runtime Error"
        SYNTAX_ERROR = "SYNTAX_ERROR", "Syntax Error"
        TIME_LIMIT_EXCEEDED = "TIME_LIMIT_EXCEEDED", "Time Limit Exceeded"
        MEMORY_LIMIT_EXCEEDED = "MEMORY_LIMIT_EXCEEDED", "Memory Limit Exceeded"
        JUDGE_ERROR = "JUDGE_ERROR", "Judge Error"
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="submissions")
    problem = models.ForeignKey(Problem, on_delete=models.PROTECT, related_name="submissions")
    code = models.TextField()
    status = models.CharField(max_length=32, choices=Status.choices, default=Status.PENDING)
    created_at = models.DateTimeField(auto_now_add=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True)
    elapsed_seconds = models.FloatField(default=0)
    duration_seconds = models.FloatField(default=0)
    hints_used = models.PositiveIntegerField(default=0)
    passed_cases = models.PositiveIntegerField(default=0)
    total_cases = models.PositiveIntegerField(default=0)
    error_message = models.TextField(blank=True)
    request_key = models.CharField(max_length=64)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "created_at"]), models.Index(fields=["user", "problem", "status"])]
        constraints = [models.UniqueConstraint(fields=["user", "request_key"], name="unique_submission_request")]

    @property
    def is_valid(self):
        return self.status not in (self.Status.PENDING, self.Status.JUDGE_ERROR)


class TestResult(models.Model):
    submission = models.ForeignKey(Submission, on_delete=models.CASCADE, related_name="test_results")
    test_case = models.ForeignKey(TestCase, on_delete=models.PROTECT)
    status = models.CharField(max_length=32, choices=Submission.Status.choices)
    stdout = models.TextField(blank=True)
    stderr = models.TextField(blank=True)
    elapsed_seconds = models.FloatField(default=0)
    memory_kb = models.PositiveIntegerField(null=True)
    provider = models.CharField(max_length=32)

    class Meta:
        ordering = ["test_case__sequence"]
        constraints = [models.UniqueConstraint(fields=["submission", "test_case"], name="unique_submission_test_result")]


class ExecutionRequest(models.Model):
    """Persisted rate budget for both custom runs and standard submissions."""
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    kind = models.CharField(max_length=16)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["user", "created_at"])]
