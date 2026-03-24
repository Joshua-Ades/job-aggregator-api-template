from django.contrib import admin

from .models import Job, JobSkill, Skill


class JobSkillInline(admin.TabularInline):
    """Show linked skills directly inside the Job detail page."""
    model = JobSkill
    extra = 0
    readonly_fields = ("skill",)
    can_delete = False


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    list_display = (
        "id", "title", "company", "location", "remote_type",
        "employment_type", "is_active", "fetched_at", "last_seen_at",
    )
    list_filter = ("is_active", "remote_type", "employment_type", "seniority_level")
    search_fields = ("title", "company", "location", "description")
    readonly_fields = (
        "id", "external_id", "fetched_at", "last_seen_at",
        "posted_at", "ai_summary",
    )
    ordering = ("-fetched_at",)
    inlines = [JobSkillInline]

    fieldsets = (
        ("Job Info", {
            "fields": ("id", "external_id", "title", "company", "job_url"),
        }),
        ("Location & Type", {
            "fields": ("location", "city", "state", "region", "remote_type", "employment_type", "seniority_level"),
        }),
        ("Status", {
            "fields": ("is_active", "posted_at", "fetched_at", "last_seen_at"),
        }),
        ("Content", {
            "fields": ("description", "ai_summary"),
            "classes": ("collapse",),
        }),
    )


@admin.register(Skill)
class SkillAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "category")
    list_filter = ("category",)
    search_fields = ("name",)
    ordering = ("name",)


@admin.register(JobSkill)
class JobSkillAdmin(admin.ModelAdmin):
    list_display = ("id", "job", "skill", "skill_category")
    list_filter = ("skill__category",)
    search_fields = ("job__title", "skill__name")
    raw_id_fields = ("job", "skill")

    @admin.display(description="Category")
    def skill_category(self, obj):
        return obj.skill.category
