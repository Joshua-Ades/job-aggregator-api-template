from django.db import models
from django.utils import timezone


class Skill(models.Model):
    """A technical or soft skill extracted from job descriptions."""

    name = models.CharField(max_length=100, unique=True, db_index=True)
    category = models.CharField(max_length=50)  # tech | soft

    class Meta:
        db_table = "skill"
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.category})"


class Job(models.Model):
    """A Python Backend Developer job posting fetched from RapidAPI."""

    external_id = models.CharField(max_length=255, unique=True, db_index=True)
    title = models.CharField(max_length=255)
    company = models.CharField(max_length=255)
    location = models.CharField(max_length=255, blank=True, null=True)
    description = models.TextField(blank=True, null=True)
    employment_type = models.CharField(max_length=100, blank=True, null=True)
    seniority_level = models.CharField(max_length=100, blank=True, null=True)
    job_url = models.URLField(max_length=500, blank=True, null=True)
    posted_at = models.DateTimeField(blank=True, null=True)
    fetched_at = models.DateTimeField(default=timezone.now)
    last_seen_at = models.DateTimeField(blank=True, null=True)   # updated every fetch cycle
    is_active = models.BooleanField(default=True)                # False = no longer on API
    remote_type = models.CharField(max_length=50, blank=True, null=True)  # Remote/Hybrid/On-site — AI extracted
    ai_summary = models.TextField(blank=True, null=True)
    city   = models.CharField(max_length=100, blank=True, null=True)  # AI-extracted, normalized
    state  = models.CharField(max_length=100, blank=True, null=True)  # AI-extracted, normalized
    region = models.CharField(max_length=100, blank=True, null=True)  # AI-extracted, normalized

    skills = models.ManyToManyField(
        Skill, through="JobSkill", related_name="jobs", blank=True
    )

    class Meta:
        db_table = "job"
        ordering = ["-fetched_at"]

    def __str__(self):
        return f"{self.title} @ {self.company}"


class JobSkill(models.Model):
    """Junction table — links a Job to a Skill. Category (tech/soft) lives on Skill."""

    job = models.ForeignKey(Job, on_delete=models.CASCADE, related_name="job_skills")
    skill = models.ForeignKey(Skill, on_delete=models.CASCADE, related_name="job_skills")

    class Meta:
        db_table = "job_skill"
        unique_together = ("job", "skill")
