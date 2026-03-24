import json
import logging

from django.conf import settings
from django.db.models import Case, Exists, IntegerField, OuterRef, Q, Value, When
from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.filters import OrderingFilter
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

import redis as redis_lib
from celery.result import AsyncResult

from .models import Job, JobSkill, Skill
from .serializers import (
    FetchResponseSerializer,
    JobDetailSerializer,
    JobListSerializer,
    JobSummarySerializer,
    TrendingSkillSerializer,
)

logger = logging.getLogger(__name__)


def _get_redis():
    return redis_lib.from_url(settings.REDIS_URL, decode_responses=True)


def _upsert_skills(job: Job, tech_skills: list, soft_skills: list) -> None:
    """
    Upsert extracted skills and link them to the job.
    Category (tech/soft) lives on Skill — JobSkill is a plain junction row.
    Trending counts are computed via COUNT query on JobSkill.
    """
    all_skills = (
        [(name, "tech") for name in tech_skills]
        + [(name, "soft") for name in soft_skills]
    )
    for name, category in all_skills:
        if not name:
            continue
        skill, _ = Skill.objects.get_or_create(
            name=name, defaults={"category": category}
        )
        JobSkill.objects.get_or_create(job=job, skill=skill)


def _compute_skill_summary(job_ids):
    from django.db.models import Count
    links = (
        JobSkill.objects
        .filter(job_id__in=job_ids)
        .values("skill__name", "skill__category")
        .annotate(count=Count("id"))
        .order_by("-count", "skill__name")
    )
    tech = [{"skill": l["skill__name"], "count": l["count"]} for l in links if l["skill__category"] == "tech"]
    soft = [{"skill": l["skill__name"], "count": l["count"]} for l in links if l["skill__category"] == "soft"]
    return {"tech": tech, "soft": soft}


class JobPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "page_size"  # allow ?page_size=N override
    max_page_size = 100

    def get_paginated_response(self, data):
        job_ids = [item["id"] for item in data]
        return Response({
            "count": self.page.paginator.count,
            "next": self.get_next_link(),
            "previous": self.get_previous_link(),
            "skill_summary": _compute_skill_summary(job_ids),
            "results": data,
        })


# ── /jobs ──────────────────────────────────────────────────────────────────────

class JobViewSet(viewsets.ReadOnlyModelViewSet):
    """
    list   → GET  /jobs/
    detail → GET  /jobs/{id}/
    summary→ GET  /jobs/{id}/summary/
    fetch  → POST /jobs/fetch/

    Ordering (default: -fetched_at, overridden by relevance when ?search= is active):
      ?ordering=-fetched_at     newest scraped first  (default)
      ?ordering=-posted_at      newest posted first
      ?ordering=-last_seen_at   most recently seen in API first
      ?ordering=title           alphabetical by title
      ?ordering=company         alphabetical by company

    Location filtering (case-insensitive, combinable):
      ?city=Tel+Aviv            AI-cleaned city field OR raw location fallback
      ?state=Tel+Aviv+District  AI-cleaned state field OR raw location fallback
      ?region=Center            AI-cleaned region field OR raw location fallback

    Free-text search with relevance priority:
      ?search=python            matches title, description, skills
                                title match > skill match > description match
    """
    pagination_class = JobPagination
    filter_backends = [OrderingFilter]
    ordering_fields = ["fetched_at", "posted_at", "last_seen_at", "title", "company"]
    # No class-level ordering= here — model Meta.ordering handles the default.
    # This lets relevance annotation take effect when ?search= is active.

    def get_queryset(self):
        qs = Job.objects.all()
        city   = self.request.query_params.get("city")
        state  = self.request.query_params.get("state")
        region = self.request.query_params.get("region")
        search = self.request.query_params.get("search")

        # ── Location filters ─────────────────────────────────────────────────
        # Each checks the AI-cleaned field first (exact), then falls back to
        # the raw location string (contains) so unsummarized jobs are findable.
        if city:
            qs = qs.filter(Q(city__iexact=city) | Q(location__icontains=city))
        if state:
            qs = qs.filter(Q(state__iexact=state) | Q(location__icontains=state))
        if region:
            qs = qs.filter(Q(region__iexact=region) | Q(location__icontains=region))

        # ── Full-text search with relevance ranking ───────────────────────────
        # Priority: title (3) > skill match (2) > description (1).
        # Uses Exists subquery for skill check to avoid JOIN duplicates.
        if search:
            skill_match = JobSkill.objects.filter(
                job=OuterRef("pk"),
                skill__name__icontains=search,
            )
            qs = qs.filter(
                Q(title__icontains=search)
                | Q(description__icontains=search)
                | Q(job_skills__skill__name__icontains=search)
            ).distinct().annotate(
                _relevance=Case(
                    When(title__icontains=search, then=Value(3)),
                    When(Exists(skill_match),      then=Value(2)),
                    default=Value(1),
                    output_field=IntegerField(),
                )
            ).order_by("-_relevance", "-fetched_at")

        return qs

    def get_serializer_class(self):
        if self.action == "list":
            return JobListSerializer
        return JobDetailSerializer

    @action(detail=True, methods=["get"])
    def summary(self, request, pk=None):
        """
        Three-layer summary cache:

        Layer 1 — Redis HIT:
            Return immediately (~0.1 ms). Typical case for repeated requests.

        Layer 2 — Redis MISS, Postgres HIT (ai_summary already stored):
            Happens after a server restart (Redis is empty but DB is not).
            Reconstruct payload from Postgres, re-warm Redis, return — no AI call.

        Layer 3 — Both MISS (job never summarised before):
            Call AI, save to Postgres permanently, warm Redis, return.
        """
        try:
            job = Job.objects.get(pk=pk)
        except Job.DoesNotExist:
            return Response(
                {"detail": f"Job {pk} not found."}, status=status.HTTP_404_NOT_FOUND
            )

        cache_key = f"summary:{pk}"
        r = _get_redis()

        # ── Layer 1: Redis hit ────────────────────────────────────────────────
        cached_raw = r.get(cache_key)
        if cached_raw:
            data = json.loads(cached_raw)
            return Response(
                JobSummarySerializer({"job_id": job.id, "cached": True, **data}).data
            )

        # ── Layer 2: Postgres hit — re-warm Redis, skip AI call ───────────────
        if job.ai_summary:
            # Skills are already normalised in the JobSkill table from the
            # original summarisation run — reconstruct from there.
            tech_skills = list(
                JobSkill.objects.filter(job=job, skill__category="tech")
                .select_related("skill")
                .values_list("skill__name", flat=True)
            )
            soft_skills = list(
                JobSkill.objects.filter(job=job, skill__category="soft")
                .select_related("skill")
                .values_list("skill__name", flat=True)
            )
            payload = {
                "summary": job.ai_summary,
                "tech_skills": tech_skills,
                "soft_skills": soft_skills,
                "remote_type": job.remote_type,
                "city": job.city,
                "state": job.state,
                "region": job.region,
            }
            # Put it back in Redis so the next request hits Layer 1
            r.setex(cache_key, settings.SUMMARY_CACHE_TTL, json.dumps(payload))
            return Response(
                JobSummarySerializer({"job_id": job.id, "cached": True, **payload}).data
            )

        # ── Layer 3: Both miss — call AI for the first time ───────────────────
        from .services.summarizer import summarize

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

        if result.get("city"):
            job.city = result["city"]
            update_fields.append("city")

        if result.get("state"):
            job.state = result["state"]
            update_fields.append("state")

        if result.get("region"):
            job.region = result["region"]
            update_fields.append("region")

        if result.get("remote_type"):
            job.remote_type = result["remote_type"]
            update_fields.append("remote_type")

        job.save(update_fields=update_fields)

        payload = {
            "summary": result["summary"],
            "tech_skills": result["tech_skills"],
            "soft_skills": result["soft_skills"],
            "remote_type": result.get("remote_type"),
            "city": result.get("city"),
            "state": result.get("state"),
            "region": result.get("region"),
        }
        r.setex(cache_key, settings.SUMMARY_CACHE_TTL, json.dumps(payload))

        return Response(
            JobSummarySerializer({"job_id": job.id, "cached": False, **payload}).data
        )

    @action(detail=False, methods=["post"])
    def fetch(self, request):
        """
        Manually trigger a job fetch from the configured RapidAPI provider.

        Optional overrides (fall back to .env defaults when omitted):
          ?query=Java+Developer     override JOB_SEARCH_QUERY
          ?location=Tel+Aviv        override JOB_SEARCH_LOCATION
        """
        from .services.fetcher import fetch_and_store

        query    = request.query_params.get("query")    or None
        location = request.query_params.get("location") or None

        new_count = fetch_and_store(query=query, location=location)
        return Response(
            FetchResponseSerializer({
                "new_jobs": new_count,
                "provider": settings.JOB_API_PROVIDER,
                "message": f"Fetched successfully. {new_count} new job(s) stored.",
            }).data
        )

    @action(detail=False, methods=["post"], url_path="summarize-bulk")
    def summarize_bulk(self, request):
        """
        Kick off background AI summarization for unsummarized jobs.
        Returns 202 Accepted immediately — Celery worker does the heavy lifting.
        Poll GET /jobs/tasks/{task_id}/ to track progress.

        Optional filters (all combinable):
          ?limit=25            how many jobs to queue (default 20)
          ?locations=Tel+Aviv,Haifa,Israel   OR filter on raw location field
          ?search=python,django              OR filter on title + description
        """
        from .tasks import summarize_bulk_task

        limit = int(request.query_params.get("limit", 20))

        qs = Job.objects.filter(ai_summary__isnull=True)

        # ── Location filter — OR across all provided values ───────────────────
        raw_locations = request.query_params.get("locations", "")
        locations = [l.strip() for l in raw_locations.split(",") if l.strip()]
        if locations:
            loc_filter = Q()
            for loc in locations:
                loc_filter |= Q(location__icontains=loc)
            qs = qs.filter(loc_filter)

        # ── Search filter — OR across all provided terms ──────────────────────
        raw_search = request.query_params.get("search", "")
        search_terms = [s.strip() for s in raw_search.split(",") if s.strip()]
        if search_terms:
            search_filter = Q()
            for term in search_terms:
                search_filter |= Q(title__icontains=term) | Q(description__icontains=term)
            qs = qs.filter(search_filter)

        job_ids = list(qs.values_list("id", flat=True)[:limit])

        if not job_ids:
            return Response(
                {"message": "No unsummarized jobs found.", "jobs_queued": 0},
                status=status.HTTP_200_OK,
            )

        task = summarize_bulk_task.delay(job_ids)
        return Response(
            {
                "task_id": task.id,
                "status": "queued",
                "jobs_queued": len(job_ids),
                "message": f"Summarizing {len(job_ids)} job(s) in the background.",
                "poll_url": f"/jobs/tasks/{task.id}/",
            },
            status=status.HTTP_202_ACCEPTED,
        )


# ── /jobs/tasks ────────────────────────────────────────────────────────────────

class TaskStatusView(APIView):
    """
    GET /jobs/tasks/{task_id}/
    Poll the status of a background Celery task (e.g. summarize-bulk).

    States:
      queued      → task received, worker hasn't started yet
      in_progress → worker is processing, processed/total counters available
      done        → all jobs summarized successfully
      failed      → task crashed, error message included
    """

    def get(self, request, task_id):
        result = AsyncResult(task_id)

        if result.state == "PENDING":
            return Response({"task_id": task_id, "status": "queued"})

        if result.state == "PROGRESS":
            return Response({
                "task_id": task_id,
                "status": "in_progress",
                "processed": result.info.get("processed", 0),
                "total": result.info.get("total", 0),
            })

        if result.state == "SUCCESS":
            return Response({
                "task_id": task_id,
                "status": "done",
                "processed": result.result.get("processed", 0),
                "total": result.result.get("total", 0),
            })

        if result.state == "FAILURE":
            return Response(
                {"task_id": task_id, "status": "failed", "error": str(result.result)},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        return Response({"task_id": task_id, "status": result.state.lower()})


# ── /skills ────────────────────────────────────────────────────────────────────

class TrendingSkillsView(APIView):
    """GET /skills/trending/ — skills ranked by usage count across all jobs."""

    def get(self, request):
        from django.db.models import Count
        limit = int(request.query_params.get("limit", 20))
        skills = (
            JobSkill.objects
            .values("skill__id", "skill__name", "skill__category")
            .annotate(count=Count("id"))
            .order_by("-count", "skill__name")[:limit]
        )
        data = [
            {"id": s["skill__id"], "name": s["skill__name"], "category": s["skill__category"], "count": s["count"]}
            for s in skills
        ]
        return Response(data)
