import json
import pytest
from unittest.mock import patch, MagicMock
from rest_framework.test import APIClient
from jobs.models import Job, Skill, JobSkill


@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def mock_summarizer():
    """Patches the summarize function used inside views."""
    with patch("jobs.services.summarizer.summarize") as mock:
        mock.return_value = {
            "summary": "Mocked AI summary.",
            "tech_skills": ["Python", "Django"],
            "soft_skills": ["Team player"],
            "remote_type": "Hybrid",
            "city": "Tel Aviv",
            "state": "Israel",
            "region": "Tel Aviv District",
        }
        yield mock


@pytest.fixture
def mock_redis():
    """Patches the Redis client returned by _get_redis() in views."""
    fake_store = {}

    mock = MagicMock()
    mock.get.side_effect = lambda key: fake_store.get(key)
    mock.setex.side_effect = lambda key, ttl, val: fake_store.update({key: val})

    with patch("jobs.views._get_redis", return_value=mock):
        yield mock, fake_store


@pytest.fixture
@pytest.mark.django_db
def sample_job(db):
    skill_py = Skill.objects.create(name="Python", category="tech")
    skill_dj = Skill.objects.create(name="Django", category="tech")

    job = Job.objects.create(
        external_id="ext-001",
        title="Python Backend Developer",
        company="Acme Ltd",
        location="Tel Aviv, Israel",
        description="We need a great Python/Django dev.",
        employment_type="Full-time",
        seniority_level="Mid-Senior",
        job_url="https://example.com/job/1",
        city="Tel Aviv",
        state="Israel",
        region="Tel Aviv District",
    )
    JobSkill.objects.create(job=job, skill=skill_py)
    JobSkill.objects.create(job=job, skill=skill_dj)
    return job
