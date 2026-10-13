from django.conf import settings
from django.db import models


class LearningActivity(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="learning_activities")
    submission = models.ForeignKey("problems.Submission", null=True, blank=True, on_delete=models.CASCADE, related_name="activities")
    knowledge_point = models.ForeignKey("knowledge.KnowledgePoint", on_delete=models.PROTECT)
    event_type = models.CharField(max_length=24, default="submission")
    correct = models.BooleanField(null=True)
    hints_used = models.PositiveIntegerField(default=0)
    duration_seconds = models.FloatField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    event_key = models.CharField(max_length=96)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "knowledge_point", "created_at"])]
        constraints = [models.UniqueConstraint(fields=["user", "knowledge_point", "event_key"], name="unique_learning_evidence")]


class MasteryState(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mastery_states")
    knowledge_point = models.ForeignKey("knowledge.KnowledgePoint", on_delete=models.PROTECT, related_name="mastery_states")
    index = models.FloatField(default=0)
    bkt_probability = models.FloatField(default=0.2)
    evidence_count = models.PositiveIntegerField(default=0)
    distinct_problems = models.PositiveIntegerField(default=0)
    explanation = models.JSONField(default=dict)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=["user", "knowledge_point"], name="unique_user_mastery")]


class MasterySnapshot(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    knowledge_point = models.ForeignKey("knowledge.KnowledgePoint", on_delete=models.PROTECT)
    submission = models.ForeignKey("problems.Submission", null=True, on_delete=models.CASCADE)
    index = models.FloatField()
    bkt_probability = models.FloatField()
    evidence_count = models.PositiveIntegerField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        indexes = [models.Index(fields=["user", "knowledge_point", "created_at"])]
        constraints = [models.UniqueConstraint(fields=["user", "knowledge_point", "submission"], name="unique_mastery_snapshot_event")]


class MistakeRecord(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="mistakes")
    problem = models.ForeignKey("problems.Problem", on_delete=models.PROTECT)
    submission = models.OneToOneField("problems.Submission", on_delete=models.CASCADE)
    error_type = models.CharField(max_length=32)
    failure_reason = models.TextField()
    ai_diagnosis = models.TextField(blank=True)
    resolved = models.BooleanField(default=False)
    resolved_at = models.DateTimeField(null=True)
    last_reviewed_at = models.DateTimeField(null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["user", "resolved", "error_type"])]
