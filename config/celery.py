import os
from celery import Celery
from datetime import timedelta

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

app = Celery("config")

# Read config from Django settings, keys prefixed with CELERY_
app.config_from_object("django.conf:settings", namespace="CELERY")

# Auto-discover tasks from all INSTALLED_APPS
app.autodiscover_tasks()

# ── Periodic schedule ─────────────────────────────────────────────────────────
app.conf.beat_schedule = {
    "fetch-jobs-every-6-hours": {
        "task": "jobs.tasks.fetch_jobs_task",
        "schedule": timedelta(hours=6),
    },
}
