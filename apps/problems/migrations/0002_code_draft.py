from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("problems", "0001_initial"), migrations.swappable_dependency(settings.AUTH_USER_MODEL)]

    operations = [
        migrations.CreateModel(
            name="CodeDraft",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("scope", models.CharField(max_length=48)),
                ("code", models.TextField(blank=True)),
                ("stdin", models.TextField(blank=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("problem", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE, to="problems.problem")),
                ("user", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="code_drafts", to=settings.AUTH_USER_MODEL)),
            ],
            options={"constraints": [models.UniqueConstraint(fields=("user", "scope"), name="unique_user_code_draft")]},
        ),
    ]
