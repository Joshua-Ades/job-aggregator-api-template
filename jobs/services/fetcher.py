"""
Job fetcher — pulls job postings from RapidAPI (sync).

Providers (set JOB_API_PROVIDER in .env):
  "linkedin"  — linkedin-scraper-api-real-time-fast-affordable
  "jsearch"   — jsearch.p.rapidapi.com  (recommended, more stable schema)

Default search query + location come from .env (JOB_SEARCH_QUERY, JOB_SEARCH_LOCATION).
Both can be overridden at call time — used by POST /jobs/fetch/?query=...&location=...

Uses Django ORM get_or_create for clean upsert-by-external_id deduplication.
Returns number of NEW jobs stored.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

import httpx
from django.conf import settings
from django.utils import timezone as dj_timezone

from jobs.models import Job

logger = logging.getLogger(__name__)


# ── LinkedIn ──────────────────────────────────────────────────────────────────

def _fetch_linkedin(query: str | None = None, location: str | None = None) -> list[dict]:
    url = "https://linkedin-scraper-api-real-time-fast-affordable.p.rapidapi.com/jobs/search"
    headers = {
        "X-RapidAPI-Key": settings.RAPIDAPI_KEY,
        "X-RapidAPI-Host": "linkedin-scraper-api-real-time-fast-affordable.p.rapidapi.com",
    }
    params = {
        "query": query or settings.JOB_SEARCH_QUERY,
        "location": location or settings.JOB_SEARCH_LOCATION,
        "page": "1",
    }
    with httpx.Client(timeout=30) as client:
        resp = client.get(url, headers=headers, params=params)
        resp.raise_for_status()
    raw_jobs = resp.json().get("data", {}).get("jobs", [])
    return [_normalize_linkedin(j) for j in raw_jobs]


def _normalize_linkedin(raw: dict[str, Any]) -> dict:
    company = raw.get("company", {})
    company_name = company.get("name", "") if isinstance(company, dict) else str(company)

    location = raw.get("location", {})
    location_str = location.get("city", "") if isinstance(location, dict) else str(location or "")

    posted = raw.get("posted_at") or raw.get("listed_at") or raw.get("date")
    try:
        posted_dt = datetime.fromisoformat(str(posted).replace("Z", "+00:00")) if posted else None
    except (ValueError, TypeError):
        posted_dt = None

    return {
        "external_id": str(raw.get("id") or raw.get("job_id") or ""),
        "title": raw.get("title") or raw.get("job_title") or "",
        "company": company_name,
        "location": location_str,
        "description": raw.get("description") or raw.get("job_description") or "",
        "employment_type": raw.get("employment_type") or raw.get("job_type"),
        "seniority_level": raw.get("seniority_level") or raw.get("level"),
        "job_url": raw.get("url") or raw.get("job_url") or raw.get("apply_url"),
        "posted_at": posted_dt,
    }


# ── JSearch ───────────────────────────────────────────────────────────────────

def _fetch_jsearch(query: str | None = None, location: str | None = None) -> list[dict]:
    url = "https://jsearch.p.rapidapi.com/search"
    headers = {
        "X-RapidAPI-Key": settings.RAPIDAPI_KEY,
        "X-RapidAPI-Host": "jsearch.p.rapidapi.com",
    }
    effective_query    = query    or settings.JOB_SEARCH_QUERY
    effective_location = location or settings.JOB_SEARCH_LOCATION
    params = {
        "query": f"{effective_query} in {effective_location}",
        "page": "1",
        "num_pages": "1",
    }
    with httpx.Client(timeout=30) as client:
        resp = client.get(url, headers=headers, params=params)
        resp.raise_for_status()
    raw_jobs = resp.json().get("data", [])
    return [_normalize_jsearch(j) for j in raw_jobs]


def _normalize_jsearch(raw: dict[str, Any]) -> dict:
    city = raw.get("job_city") or ""
    state = raw.get("job_state") or ""
    country = raw.get("job_country") or ""
    location = ", ".join(filter(None, [city, state, country]))

    posted = raw.get("job_posted_at_datetime_utc")
    try:
        posted_dt = datetime.fromisoformat(str(posted).replace("Z", "+00:00")) if posted else None
    except (ValueError, TypeError):
        posted_dt = None

    return {
        "external_id": str(raw.get("job_id") or ""),
        "title": raw.get("job_title") or "",
        "company": raw.get("employer_name") or "",
        "location": location,
        "description": raw.get("job_description") or "",
        "employment_type": raw.get("job_employment_type"),
        "seniority_level": None,
        "job_url": raw.get("job_apply_link") or raw.get("job_google_link"),
        "posted_at": posted_dt,
    }


# ── Main entry point ──────────────────────────────────────────────────────────

def fetch_and_store(query: str | None = None, location: str | None = None) -> int:
    """
    Fetch jobs from the configured provider and upsert into the DB.

    Args:
        query:    search term override (e.g. "Java Developer").
                  Falls back to JOB_SEARCH_QUERY from .env when None.
        location: location override (e.g. "Tel Aviv").
                  Falls back to JOB_SEARCH_LOCATION from .env when None.

    Returns the number of NEW jobs inserted (duplicates skipped by external_id).
    """
    provider = settings.JOB_API_PROVIDER.lower()
    logger.info(
        "Fetching jobs via provider=%s query=%s location=%s",
        provider, query or settings.JOB_SEARCH_QUERY, location or settings.JOB_SEARCH_LOCATION,
    )

    try:
        jobs_data = (
            _fetch_jsearch(query=query, location=location)
            if provider == "jsearch"
            else _fetch_linkedin(query=query, location=location)
        )
    except httpx.HTTPError as exc:
        logger.error("API request failed: %s", exc)
        return 0

    now = dj_timezone.now()
    new_count = 0

    for jd in jobs_data:
        if not jd.get("external_id"):
            continue

        # First insert: set all fields.
        # Subsequent fetches: only touch last_seen_at + is_active.
        job, created = Job.objects.get_or_create(
            external_id=jd["external_id"],
            defaults={
                "title": jd["title"],
                "company": jd["company"],
                "location": jd.get("location") or "",
                "description": jd.get("description") or "",
                "employment_type": jd.get("employment_type"),
                "seniority_level": jd.get("seniority_level"),
                "job_url": jd.get("job_url"),
                "posted_at": jd.get("posted_at"),
                "fetched_at": now,
                "last_seen_at": now,
                "is_active": True,
            },
        )
        if created:
            new_count += 1
        else:
            # Job already exists — stamp it as still live this cycle
            job.last_seen_at = now
            job.is_active = True
            job.save(update_fields=["last_seen_at", "is_active"])

    # NOTE: we intentionally do NOT mark unseen jobs as is_active=False.
    # We only fetch page 1 of search results (~25-50 jobs), so absence from
    # the current page does not mean a job is closed — it may just be ranked
    # lower. is_active should only flip to False when the provider explicitly
    # signals the posting is closed (requires a per-job status check endpoint
    # that we do not currently call).

    logger.info("Fetched %d jobs, %d new", len(jobs_data), new_count)
    return new_count
