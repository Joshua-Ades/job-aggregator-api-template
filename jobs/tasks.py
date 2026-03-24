import logging
from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(bind=True, name="jobs.tasks.summarize_bulk_task")
def summarize_bulk_task(self, job_ids: list) -> dict:
    """
    Summarize a batch of jobs in the background.
    Celery worker runs this — never called directly from a web request.
    Reports progress after each job so GET /jobs/tasks/{id}/ stays current.
    """
    from .models import Job
    from .services.summarizer import summarize
    from .views import _upsert_skills

    total = len(job_ids)
    processed = 0

    for job_id in job_ids:
        try:
            job = Job.objects.get(pk=job_id)
            result = summarize(
                title=job.title,
                company=job.company,
                location=job.location,
                description=job.description,
                employment_type=job.employment_type,
                seniority_level=job.seniority_level,
            )
            _upsert_skills(job, result["tech_skills"], result["soft_skills"])

            update_fields = ["ai_summary"]
            job.ai_summary = result["summary"]
            for field in ("city", "state", "region", "remote_type"):
                if result.get(field):
                    setattr(job, field, result[field])
                    update_fields.append(field)
            job.save(update_fields=update_fields)

            processed += 1
            # Push live progress so the status endpoint can report it
            self.update_state(
                state="PROGRESS",
                meta={"processed": processed, "total": total},
            )
            logger.info("Summarized job %d (%d/%d)", job_id, processed, total)

        except Exception as exc:
            logger.error("Failed to summarize job %d: %s", job_id, exc)

    return {"processed": processed, "total": total}


@shared_task(name="jobs.tasks.fetch_jobs_task")
def fetch_jobs_task():
    """Celery task — runs every 6 hours via Beat schedule in config/celery.py."""
    from .services.fetcher import fetch_and_store

    try:
        new_count = fetch_and_store()
        logger.info("Scheduled fetch complete — %d new jobs", new_count)
        return {"new_jobs": new_count}
    except Exception as exc:
        logger.error("Scheduled fetch error: %s", exc)
        raise
