"""
TDD tests for the jobs API endpoints.
All DB tests use @pytest.mark.django_db — pytest-django handles test DB lifecycle.
"""
import json
import pytest
from jobs.models import Job, Skill, JobSkill


# ── GET /jobs/ ─────────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_list_jobs_empty(api_client):
    resp = api_client.get("/jobs/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["results"] == []
    assert data["count"] == 0


@pytest.mark.django_db
def test_list_jobs_returns_job(api_client, sample_job):
    resp = api_client.get("/jobs/")
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 1
    assert results[0]["title"] == "Python Backend Developer"
    assert results[0]["company"] == "Acme Ltd"


@pytest.mark.django_db
def test_list_jobs_includes_description(api_client, sample_job):
    resp = api_client.get("/jobs/")
    assert resp.status_code == 200
    item = resp.json()["results"][0]
    assert "description" in item


@pytest.mark.django_db
@pytest.mark.django_db
def test_list_jobs_pagination(api_client):
    for i in range(5):
        Job.objects.create(
            external_id=f"ext-{i}", title=f"Job {i}", company="Co", location="IL"
        )
    resp = api_client.get("/jobs/?page_size=2")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["results"]) == 2
    assert data["count"] == 5
    assert data["next"] is not None


@pytest.mark.django_db
def test_list_jobs_has_skill_summary(api_client, sample_job, mock_redis, mock_summarizer):
    """skill_summary appears in the paginated list response."""
    resp = api_client.get("/jobs/")
    assert resp.status_code == 200
    data = resp.json()
    assert "skill_summary" in data
    assert "tech" in data["skill_summary"]
    assert "soft" in data["skill_summary"]


@pytest.mark.django_db
def test_list_jobs_filter_by_city(api_client):
    Job.objects.create(external_id="j1", title="Job TLV", company="Co", city="Tel Aviv")
    Job.objects.create(external_id="j2", title="Job Haifa", company="Co", city="Haifa")
    resp = api_client.get("/jobs/?city=Tel Aviv")
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 1
    assert results[0]["title"] == "Job TLV"


@pytest.mark.django_db
def test_list_jobs_filter_by_state(api_client):
    Job.objects.create(external_id="j1", title="Job A", company="Co", state="Israel")
    Job.objects.create(external_id="j2", title="Job B", company="Co", state="Germany")
    resp = api_client.get("/jobs/?state=Israel")
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 1
    assert results[0]["title"] == "Job A"


@pytest.mark.django_db
def test_list_jobs_filter_by_region(api_client):
    Job.objects.create(external_id="j1", title="Job Center", company="Co", region="Center")
    Job.objects.create(external_id="j2", title="Job North", company="Co", region="North")
    resp = api_client.get("/jobs/?region=Center")
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 1
    assert results[0]["title"] == "Job Center"


@pytest.mark.django_db
def test_list_jobs_filter_combined(api_client):
    Job.objects.create(external_id="j1", title="Match", company="Co",
                       city="Tel Aviv", state="Israel", region="Tel Aviv District")
    Job.objects.create(external_id="j2", title="No Match", company="Co",
                       city="Haifa", state="Germany", region="Bavaria")
    resp = api_client.get("/jobs/?city=Tel Aviv&region=Tel Aviv District")
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 1
    assert results[0]["title"] == "Match"


@pytest.mark.django_db
def test_list_jobs_filter_city_fallback_to_raw_location(api_client):
    """
    Unsummarized jobs (city=null) should still be found via raw location fallback.
    A job with city=null but location='Tel Aviv, Israel' must appear in ?city=Tel Aviv.
    """
    # Summarized job — AI has set city
    Job.objects.create(external_id="j1", title="Summarized TLV", company="Co",
                       city="Tel Aviv", location="Tel Aviv, Israel")
    # Unsummarized job — city is null, but raw location contains Tel Aviv
    Job.objects.create(external_id="j2", title="Unsummarized TLV", company="Co",
                       city=None, location="Tel Aviv, Israel")
    # Different city entirely — should NOT appear
    Job.objects.create(external_id="j3", title="Haifa Job", company="Co",
                       city="Haifa", location="Haifa, Israel")

    resp = api_client.get("/jobs/?city=Tel Aviv")
    assert resp.status_code == 200
    results = resp.json()["results"]
    titles = [r["title"] for r in results]
    assert "Summarized TLV" in titles    # matched by city field
    assert "Unsummarized TLV" in titles  # matched by raw location fallback
    assert "Haifa Job" not in titles     # correctly excluded


# ── GET /jobs/{id}/ ────────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_get_job_by_id(api_client, sample_job):
    resp = api_client.get(f"/jobs/{sample_job.pk}/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == sample_job.pk
    assert data["description"] == "We need a great Python/Django dev."
    assert "tech" in data["skills"]
    assert "soft" in data["skills"]


@pytest.mark.django_db
def test_get_job_skills_separated_by_category(api_client, sample_job):
    """Skills are split into tech/soft using the category field on Skill."""
    resp = api_client.get(f"/jobs/{sample_job.pk}/")
    skills = resp.json()["skills"]
    assert "Python" in skills["tech"]
    assert "Django" in skills["tech"]


@pytest.mark.django_db
def test_get_job_not_found(api_client):
    resp = api_client.get("/jobs/99999/")
    assert resp.status_code == 404


# ── GET /jobs/{id}/summary/ ────────────────────────────────────────────────────

@pytest.mark.django_db
def test_summary_calls_ai_on_cache_miss(api_client, sample_job, mock_summarizer, mock_redis):
    resp = api_client.get(f"/jobs/{sample_job.pk}/summary/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"] == "Mocked AI summary."
    assert data["cached"] is False
    assert "tech_skills" in data
    assert "soft_skills" in data
    mock_summarizer.assert_called_once()


@pytest.mark.django_db
def test_summary_returns_cached_on_second_call(api_client, sample_job, mock_summarizer, mock_redis):
    api_client.get(f"/jobs/{sample_job.pk}/summary/")  # populates cache
    mock_summarizer.reset_mock()

    resp = api_client.get(f"/jobs/{sample_job.pk}/summary/")
    assert resp.status_code == 200
    assert resp.json()["cached"] is True
    mock_summarizer.assert_not_called()


@pytest.mark.django_db
def test_summary_upserts_skills_to_db(api_client, sample_job, mock_summarizer, mock_redis):
    api_client.get(f"/jobs/{sample_job.pk}/summary/")
    skill_names = set(Skill.objects.values_list("name", flat=True))
    # Mock returns tech_skills=["Python","Django"] soft_skills=["Team player"]
    assert "Team player" in skill_names


@pytest.mark.django_db
def test_summary_serves_from_postgres_when_redis_empty(api_client, sample_job, mock_redis):
    """
    Layer 2: Redis is empty (e.g. after restart) but ai_summary already exists
    in Postgres. AI should NOT be called — summary is reconstructed from DB
    and Redis is re-warmed for the next request.
    """
    from unittest.mock import patch

    # Pre-populate the job with a stored summary (simulates previous AI call)
    sample_job.ai_summary = "Previously generated summary."
    sample_job.remote_type = "Hybrid"
    sample_job.location = "Tel Aviv"
    sample_job.save(update_fields=["ai_summary", "remote_type", "location"])

    _, fake_store = mock_redis

    with patch("jobs.services.summarizer.summarize") as mock_ai:
        resp = api_client.get(f"/jobs/{sample_job.pk}/summary/")

    assert resp.status_code == 200
    data = resp.json()
    assert data["summary"] == "Previously generated summary."
    assert data["cached"] is True          # came from Postgres, not AI
    mock_ai.assert_not_called()            # AI was never called
    assert f"summary:{sample_job.pk}" in fake_store  # Redis was re-warmed


@pytest.mark.django_db
def test_summary_job_not_found(api_client, mock_redis):
    resp = api_client.get("/jobs/99999/summary/")
    assert resp.status_code == 404


@pytest.mark.django_db
def test_summary_saves_city_state_region(api_client, sample_job, mock_summarizer, mock_redis):
    """After summarization, city/state/region are saved on the Job model."""
    api_client.get(f"/jobs/{sample_job.pk}/summary/")
    sample_job.refresh_from_db()
    assert sample_job.city == "Tel Aviv"
    assert sample_job.state == "Israel"
    assert sample_job.region == "Tel Aviv District"


# ── GET /jobs/?ordering= ───────────────────────────────────────────────────────

@pytest.mark.django_db
def test_list_jobs_ordering_by_posted_at(api_client):
    from django.utils import timezone
    from datetime import timedelta
    now = timezone.now()
    Job.objects.create(external_id="old", title="Old Job", company="Co",
                       posted_at=now - timedelta(days=10))
    Job.objects.create(external_id="new", title="New Job", company="Co",
                       posted_at=now - timedelta(days=1))
    resp = api_client.get("/jobs/?ordering=-posted_at")
    assert resp.status_code == 200
    titles = [j["title"] for j in resp.json()["results"]]
    assert titles.index("New Job") < titles.index("Old Job")


# ── POST /jobs/fetch/ ──────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_fetch_endpoint_returns_new_count(api_client):
    from unittest.mock import patch
    with patch("jobs.services.fetcher.fetch_and_store", return_value=3):
        resp = api_client.post("/jobs/fetch/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["new_jobs"] == 3
    assert "provider" in data
    assert "message" in data


@pytest.mark.django_db
def test_fetch_updates_last_seen_at_on_existing_job():
    """
    A job already in the DB should have last_seen_at updated on every fetch
    cycle — proving we know it's still live — without changing other fields.
    """
    from unittest.mock import patch
    from django.utils import timezone
    from datetime import timedelta
    from jobs.models import Job
    from jobs.services.fetcher import fetch_and_store

    old_time = timezone.now() - timedelta(hours=7)
    job = Job.objects.create(
        external_id="existing-job", title="Original Title",
        company="Co", is_active=True, last_seen_at=old_time,
    )

    fake_api_response = [{
        "external_id": "existing-job",
        "title": "Original Title", "company": "Co",
        "location": "", "description": "",
        "employment_type": None, "seniority_level": None,
        "job_url": None, "posted_at": None,
    }]

    with patch("jobs.services.fetcher._fetch_linkedin", return_value=fake_api_response):
        fetch_and_store()

    job.refresh_from_db()
    assert job.last_seen_at > old_time   # stamped with current cycle time
    assert job.title == "Original Title" # static fields untouched


@pytest.mark.django_db
def test_fetch_endpoint_uses_default_query(api_client):
    """POST /jobs/fetch/ with no params uses JOB_SEARCH_QUERY from settings."""
    from unittest.mock import patch, call
    with patch("jobs.services.fetcher.fetch_and_store", return_value=0) as mock_fetch:
        api_client.post("/jobs/fetch/")
    mock_fetch.assert_called_once_with(query=None, location=None)


@pytest.mark.django_db
def test_fetch_endpoint_accepts_custom_query(api_client):
    """POST /jobs/fetch/?query=Java+Developer overrides the default search query."""
    from unittest.mock import patch
    with patch("jobs.services.fetcher.fetch_and_store", return_value=5) as mock_fetch:
        resp = api_client.post("/jobs/fetch/?query=Java+Developer")
    assert resp.status_code == 200
    mock_fetch.assert_called_once_with(query="Java Developer", location=None)


@pytest.mark.django_db
def test_fetch_endpoint_accepts_custom_location(api_client):
    """POST /jobs/fetch/?location=Tel+Aviv overrides the default location."""
    from unittest.mock import patch
    with patch("jobs.services.fetcher.fetch_and_store", return_value=3) as mock_fetch:
        resp = api_client.post("/jobs/fetch/?location=Tel+Aviv")
    assert resp.status_code == 200
    mock_fetch.assert_called_once_with(query=None, location="Tel Aviv")


@pytest.mark.django_db
def test_fetch_endpoint_accepts_both_params(api_client):
    """POST /jobs/fetch/?query=...&location=... overrides both defaults."""
    from unittest.mock import patch
    with patch("jobs.services.fetcher.fetch_and_store", return_value=2) as mock_fetch:
        resp = api_client.post("/jobs/fetch/?query=AI+Engineer&location=Haifa")
    assert resp.status_code == 200
    mock_fetch.assert_called_once_with(query="AI Engineer", location="Haifa")


# ── GET /skills/trending/ ──────────────────────────────────────────────────────

# ── GET /jobs/?search= ─────────────────────────────────────────────────────────

@pytest.mark.django_db
def test_search_matches_title(api_client):
    """?search= returns jobs whose title contains the term."""
    Job.objects.create(external_id="j1", title="Python Backend Developer", company="Co")
    Job.objects.create(external_id="j2", title="iOS Developer", company="Co")
    resp = api_client.get("/jobs/?search=python")
    assert resp.status_code == 200
    titles = [r["title"] for r in resp.json()["results"]]
    assert "Python Backend Developer" in titles
    assert "iOS Developer" not in titles


@pytest.mark.django_db
def test_search_matches_description(api_client):
    """?search= returns jobs whose description contains the term."""
    Job.objects.create(external_id="j1", title="Backend Engineer", company="Co",
                       description="Must have strong Python experience.")
    Job.objects.create(external_id="j2", title="iOS Developer", company="Co",
                       description="Swift and Objective-C required.")
    resp = api_client.get("/jobs/?search=python")
    assert resp.status_code == 200
    titles = [r["title"] for r in resp.json()["results"]]
    assert "Backend Engineer" in titles
    assert "iOS Developer" not in titles


@pytest.mark.django_db
def test_search_matches_skill(api_client):
    """?search= returns jobs that have a matching skill in JobSkill."""
    job_with_skill = Job.objects.create(external_id="j1", title="Dev A", company="Co",
                                        description="Generic role.")
    Job.objects.create(external_id="j2", title="Dev B", company="Co",
                       description="No relevant skills.")
    skill = Skill.objects.create(name="Django", category="tech")
    JobSkill.objects.create(job=job_with_skill, skill=skill)

    resp = api_client.get("/jobs/?search=django")
    assert resp.status_code == 200
    titles = [r["title"] for r in resp.json()["results"]]
    assert "Dev A" in titles
    assert "Dev B" not in titles


@pytest.mark.django_db
def test_search_excludes_non_matching(api_client):
    """?search= with no matches returns empty results."""
    Job.objects.create(external_id="j1", title="iOS Developer", company="Co",
                       description="Swift only.")
    resp = api_client.get("/jobs/?search=kubernetes")
    assert resp.status_code == 200
    assert resp.json()["results"] == []


@pytest.mark.django_db
def test_search_title_prioritized_over_description(api_client):
    """Title match should rank higher than description-only match."""
    j_desc = Job.objects.create(external_id="j1", title="Backend Engineer", company="Co",
                                description="Python experience required.")
    j_title = Job.objects.create(external_id="j2", title="Python Developer", company="Co",
                                 description="Great role.")
    resp = api_client.get("/jobs/?search=python")
    assert resp.status_code == 200
    ids = [r["id"] for r in resp.json()["results"]]
    assert ids.index(j_title.pk) < ids.index(j_desc.pk)


@pytest.mark.django_db
def test_search_skill_prioritized_over_description(api_client):
    """Skill match should rank higher than description-only match."""
    j_desc = Job.objects.create(external_id="j1", title="Engineer A", company="Co",
                                description="Django experience is a plus.")
    j_skill = Job.objects.create(external_id="j2", title="Engineer B", company="Co",
                                 description="Great team.")
    skill = Skill.objects.create(name="Django", category="tech")
    JobSkill.objects.create(job=j_skill, skill=skill)

    resp = api_client.get("/jobs/?search=django")
    assert resp.status_code == 200
    ids = [r["id"] for r in resp.json()["results"]]
    assert ids.index(j_skill.pk) < ids.index(j_desc.pk)


@pytest.mark.django_db
def test_search_combinable_with_location_filter(api_client):
    """?search= and ?city= can be combined."""
    Job.objects.create(external_id="j1", title="Python Dev", company="Co", city="Tel Aviv")
    Job.objects.create(external_id="j2", title="Python Dev", company="Co", city="Haifa")
    resp = api_client.get("/jobs/?search=python&city=Tel Aviv")
    assert resp.status_code == 200
    results = resp.json()["results"]
    assert len(results) == 1
    assert results[0]["city"] == "Tel Aviv"


# ── POST /jobs/summarize-bulk/ ────────────────────────────────────────────────

@pytest.mark.django_db
def test_summarize_bulk_returns_202(api_client):
    """POST /jobs/summarize-bulk/ returns 202 Accepted with a task_id immediately."""
    from unittest.mock import MagicMock, patch
    Job.objects.create(external_id="j1", title="Python Dev", company="Co")
    with patch("jobs.tasks.summarize_bulk_task.delay") as mock_delay:
        mock_delay.return_value = MagicMock(id="fake-task-id")
        resp = api_client.post("/jobs/summarize-bulk/")
    assert resp.status_code == 202
    data = resp.json()
    assert data["task_id"] == "fake-task-id"
    assert data["status"] == "queued"
    assert data["jobs_queued"] == 1


@pytest.mark.django_db
def test_summarize_bulk_skips_already_summarized(api_client):
    """Already summarized jobs are excluded from the bulk task."""
    from unittest.mock import MagicMock, patch
    Job.objects.create(external_id="j1", title="Done", company="Co",
                       ai_summary="already done")
    Job.objects.create(external_id="j2", title="Pending", company="Co")
    with patch("jobs.tasks.summarize_bulk_task.delay") as mock_delay:
        mock_delay.return_value = MagicMock(id="fake-task-id")
        resp = api_client.post("/jobs/summarize-bulk/")
    assert resp.status_code == 202
    assert resp.json()["jobs_queued"] == 1


@pytest.mark.django_db
def test_summarize_bulk_no_jobs_returns_200(api_client):
    """When nothing to summarize, return 200 with an informative message."""
    resp = api_client.post("/jobs/summarize-bulk/")
    assert resp.status_code == 200
    assert "No unsummarized" in resp.json()["message"]


@pytest.mark.django_db
def test_summarize_bulk_limit_param(api_client):
    """?limit=N caps how many jobs are queued."""
    from unittest.mock import MagicMock, patch
    for i in range(5):
        Job.objects.create(external_id=f"j{i}", title=f"Dev {i}", company="Co")
    with patch("jobs.tasks.summarize_bulk_task.delay") as mock_delay:
        mock_delay.return_value = MagicMock(id="fake-task-id")
        resp = api_client.post("/jobs/summarize-bulk/?limit=3")
    assert resp.status_code == 202
    assert resp.json()["jobs_queued"] == 3


@pytest.mark.django_db
def test_summarize_bulk_filter_by_single_location(api_client):
    """?locations=Tel+Aviv only queues jobs whose raw location contains Tel Aviv."""
    from unittest.mock import MagicMock, patch
    Job.objects.create(external_id="j1", title="Dev", company="Co",
                       location="Tel Aviv, Israel")
    Job.objects.create(external_id="j2", title="Dev", company="Co",
                       location="Haifa, Israel")
    with patch("jobs.tasks.summarize_bulk_task.delay") as mock_delay:
        mock_delay.return_value = MagicMock(id="fake-task-id")
        resp = api_client.post("/jobs/summarize-bulk/?locations=Tel+Aviv")
    assert resp.status_code == 202
    assert resp.json()["jobs_queued"] == 1


@pytest.mark.django_db
def test_summarize_bulk_filter_by_multiple_locations(api_client):
    """?locations=Tel+Aviv,Haifa queues jobs matching either location."""
    from unittest.mock import MagicMock, patch
    Job.objects.create(external_id="j1", title="Dev", company="Co",
                       location="Tel Aviv, Israel")
    Job.objects.create(external_id="j2", title="Dev", company="Co",
                       location="Haifa, Israel")
    Job.objects.create(external_id="j3", title="Dev", company="Co",
                       location="London, UK")
    with patch("jobs.tasks.summarize_bulk_task.delay") as mock_delay:
        mock_delay.return_value = MagicMock(id="fake-task-id")
        resp = api_client.post("/jobs/summarize-bulk/?locations=Tel+Aviv,Haifa")
    assert resp.status_code == 202
    assert resp.json()["jobs_queued"] == 2


@pytest.mark.django_db
def test_summarize_bulk_filter_by_single_search(api_client):
    """?search=python only queues jobs whose title or description contains python."""
    from unittest.mock import MagicMock, patch
    Job.objects.create(external_id="j1", title="Python Developer", company="Co",
                       location="Israel")
    Job.objects.create(external_id="j2", title="iOS Developer", company="Co",
                       location="Israel")
    with patch("jobs.tasks.summarize_bulk_task.delay") as mock_delay:
        mock_delay.return_value = MagicMock(id="fake-task-id")
        resp = api_client.post("/jobs/summarize-bulk/?search=python")
    assert resp.status_code == 202
    assert resp.json()["jobs_queued"] == 1


@pytest.mark.django_db
def test_summarize_bulk_filter_by_multiple_search(api_client):
    """?search=python,django queues jobs matching either term."""
    from unittest.mock import MagicMock, patch
    Job.objects.create(external_id="j1", title="Python Developer", company="Co")
    Job.objects.create(external_id="j2", title="Django Engineer", company="Co")
    Job.objects.create(external_id="j3", title="iOS Developer", company="Co")
    with patch("jobs.tasks.summarize_bulk_task.delay") as mock_delay:
        mock_delay.return_value = MagicMock(id="fake-task-id")
        resp = api_client.post("/jobs/summarize-bulk/?search=python,django")
    assert resp.status_code == 202
    assert resp.json()["jobs_queued"] == 2


@pytest.mark.django_db
def test_summarize_bulk_filter_combined_location_and_search(api_client):
    """?locations= and ?search= combined — must match both."""
    from unittest.mock import MagicMock, patch
    Job.objects.create(external_id="j1", title="Python Developer", company="Co",
                       location="Tel Aviv, Israel")      # ✅ matches both
    Job.objects.create(external_id="j2", title="Python Developer", company="Co",
                       location="London, UK")            # ❌ wrong location
    Job.objects.create(external_id="j3", title="iOS Developer", company="Co",
                       location="Tel Aviv, Israel")      # ❌ wrong tech
    with patch("jobs.tasks.summarize_bulk_task.delay") as mock_delay:
        mock_delay.return_value = MagicMock(id="fake-task-id")
        resp = api_client.post(
            "/jobs/summarize-bulk/?locations=Tel+Aviv,Israel&search=python,django"
        )
    assert resp.status_code == 202
    assert resp.json()["jobs_queued"] == 1


# ── GET /jobs/tasks/{task_id}/ ─────────────────────────────────────────────────

def test_task_status_queued(api_client):
    """PENDING state maps to 'queued' in the response."""
    from unittest.mock import MagicMock, patch
    with patch("jobs.views.AsyncResult") as mock_result_cls:
        mock_result_cls.return_value.state = "PENDING"
        resp = api_client.get("/jobs/tasks/fake-task-id/")
    assert resp.status_code == 200
    assert resp.json()["status"] == "queued"


def test_task_status_in_progress(api_client):
    """PROGRESS state exposes processed/total counters."""
    from unittest.mock import MagicMock, patch
    with patch("jobs.views.AsyncResult") as mock_result_cls:
        mock = MagicMock()
        mock.state = "PROGRESS"
        mock.info = {"processed": 8, "total": 20}
        mock_result_cls.return_value = mock
        resp = api_client.get("/jobs/tasks/fake-task-id/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "in_progress"
    assert data["processed"] == 8
    assert data["total"] == 20


def test_task_status_done(api_client):
    """SUCCESS state returns done with final counts."""
    from unittest.mock import MagicMock, patch
    with patch("jobs.views.AsyncResult") as mock_result_cls:
        mock = MagicMock()
        mock.state = "SUCCESS"
        mock.result = {"processed": 20, "total": 20}
        mock_result_cls.return_value = mock
        resp = api_client.get("/jobs/tasks/fake-task-id/")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "done"
    assert data["processed"] == 20


def test_task_status_failed(api_client):
    """FAILURE state returns 500 with an error message."""
    from unittest.mock import MagicMock, patch
    with patch("jobs.views.AsyncResult") as mock_result_cls:
        mock = MagicMock()
        mock.state = "FAILURE"
        mock.result = Exception("AI provider down")
        mock_result_cls.return_value = mock
        resp = api_client.get("/jobs/tasks/fake-task-id/")
    assert resp.status_code == 500
    assert "error" in resp.json()


# ── GET /skills/trending/ ──────────────────────────────────────────────────────

@pytest.mark.django_db
def test_trending_skills_empty(api_client):
    resp = api_client.get("/skills/trending/")
    assert resp.status_code == 200
    assert resp.json() == []


@pytest.mark.django_db
def test_trending_skills_ordered_by_frequency(api_client):
    """Skills are ordered by JobSkill count descending."""
    job1 = Job.objects.create(external_id="j1", title="Job 1", company="Co")
    job2 = Job.objects.create(external_id="j2", title="Job 2", company="Co")
    job3 = Job.objects.create(external_id="j3", title="Job 3", company="Co")

    skill_py = Skill.objects.create(name="Python", category="tech")
    skill_redis = Skill.objects.create(name="Redis", category="tech")
    skill_docker = Skill.objects.create(name="Docker", category="tech")

    # Python appears in 3 jobs, Redis in 2, Docker in 1
    for job in [job1, job2, job3]:
        JobSkill.objects.create(job=job, skill=skill_py)
    for job in [job1, job2]:
        JobSkill.objects.create(job=job, skill=skill_redis)
    JobSkill.objects.create(job=job1, skill=skill_docker)

    resp = api_client.get("/skills/trending/")
    assert resp.status_code == 200
    names = [s["name"] for s in resp.json()]
    assert names == ["Python", "Redis", "Docker"]


@pytest.mark.django_db
def test_trending_skills_limit_param(api_client):
    job = Job.objects.create(external_id="j1", title="Job 1", company="Co")
    for i in range(10):
        skill = Skill.objects.create(name=f"Skill{i}", category="tech")
        JobSkill.objects.create(job=job, skill=skill)
    resp = api_client.get("/skills/trending/?limit=3")
    assert resp.status_code == 200
    assert len(resp.json()) == 3
