from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    initial = True
    dependencies = []

    operations = [
        # 1. Skill (no deps)
        migrations.CreateModel(
            name="Skill",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("name", models.CharField(db_index=True, max_length=100, unique=True)),
                ("category", models.CharField(max_length=50)),
                ("frequency", models.IntegerField(default=0)),
            ],
            options={"ordering": ["-frequency"]},
        ),
        # 2. Job — WITHOUT the skills M2M (added below after JobSkill exists)
        migrations.CreateModel(
            name="Job",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("external_id", models.CharField(db_index=True, max_length=255, unique=True)),
                ("title", models.CharField(max_length=255)),
                ("company", models.CharField(max_length=255)),
                ("location", models.CharField(blank=True, max_length=255, null=True)),
                ("description", models.TextField(blank=True, null=True)),
                ("employment_type", models.CharField(blank=True, max_length=100, null=True)),
                ("seniority_level", models.CharField(blank=True, max_length=100, null=True)),
                ("job_url", models.URLField(blank=True, max_length=500, null=True)),
                ("posted_at", models.DateTimeField(blank=True, null=True)),
                ("fetched_at", models.DateTimeField(default=django.utils.timezone.now)),
                ("ai_summary", models.TextField(blank=True, null=True)),
            ],
            options={"ordering": ["-fetched_at"]},
        ),
        # 3. JobSkill junction (requires Job + Skill)
        migrations.CreateModel(
            name="JobSkill",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("is_required", models.BooleanField(default=True)),
                ("job", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="job_skills",
                    to="jobs.Job",
                )),
                ("skill", models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name="job_skills",
                    to="jobs.Skill",
                )),
            ],
            options={"unique_together": {("job", "skill")}},
        ),
        # 4. Now safe to add M2M (through table exists)
        migrations.AddField(
            model_name="Job",
            name="skills",
            field=models.ManyToManyField(
                blank=True,
                related_name="jobs",
                through="jobs.JobSkill",
                to="jobs.Skill",
            ),
        ),
    ]
