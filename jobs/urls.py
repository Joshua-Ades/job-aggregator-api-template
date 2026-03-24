from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import JobViewSet, TaskStatusView, TrendingSkillsView

router = DefaultRouter()
router.register(r"jobs", JobViewSet, basename="job")

urlpatterns = [
    path("", include(router.urls)),
    path("jobs/tasks/<str:task_id>/", TaskStatusView.as_view(), name="task-status"),
    path("skills/trending/", TrendingSkillsView.as_view(), name="skills-trending"),
    path("health/", lambda request: __import__("django.http", fromlist=["JsonResponse"]).JsonResponse({"status": "ok"})),
]
