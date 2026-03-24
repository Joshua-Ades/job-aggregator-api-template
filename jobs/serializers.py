from rest_framework import serializers
from .models import Job, JobSkill


class JobListSerializer(serializers.ModelSerializer):
    """List view — includes description and extracted skills (tech/soft separated)."""
    skills = serializers.SerializerMethodField()

    class Meta:
        model = Job
        fields = [
            "id", "title", "company", "location", "description",
            "employment_type", "seniority_level",
            "job_url", "posted_at", "fetched_at",
            "last_seen_at", "is_active", "remote_type",
            "city", "state", "region",
            "skills",
        ]

    def get_skills(self, obj):
        links = JobSkill.objects.filter(job=obj).select_related("skill")
        return {
            "tech": [l.skill.name for l in links if l.skill.category == "tech"],
            "soft": [l.skill.name for l in links if l.skill.category == "soft"],
        }


class JobDetailSerializer(serializers.ModelSerializer):
    """Full detail with tech and soft skills as a nested object."""
    skills = serializers.SerializerMethodField()

    class Meta:
        model = Job
        fields = [
            "id", "title", "company", "location", "description",
            "employment_type", "seniority_level",
            "job_url", "posted_at", "fetched_at",
            "last_seen_at", "is_active", "remote_type",
            "city", "state", "region",
            "skills",
        ]

    def get_skills(self, obj):
        links = JobSkill.objects.filter(job=obj).select_related("skill")
        return {
            "tech": [l.skill.name for l in links if l.skill.category == "tech"],
            "soft": [l.skill.name for l in links if l.skill.category == "soft"],
        }


class JobSummarySerializer(serializers.Serializer):
    """Structured AI summary: overview + skills + location intelligence."""
    job_id     = serializers.IntegerField()
    summary    = serializers.CharField()
    tech_skills = serializers.ListField(child=serializers.CharField())
    soft_skills = serializers.ListField(child=serializers.CharField())
    remote_type = serializers.CharField(allow_null=True, required=False)
    city        = serializers.CharField(allow_null=True, required=False)
    state       = serializers.CharField(allow_null=True, required=False)
    region      = serializers.CharField(allow_null=True, required=False)
    cached      = serializers.BooleanField()


class FetchResponseSerializer(serializers.Serializer):
    new_jobs  = serializers.IntegerField()
    provider  = serializers.CharField()
    message   = serializers.CharField()


class TrendingSkillSerializer(serializers.Serializer):
    id       = serializers.IntegerField()
    name     = serializers.CharField()
    category = serializers.CharField()
    count    = serializers.IntegerField()
