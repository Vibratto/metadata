"""``activity`` app URLs."""

from django.urls import URLPattern, URLResolver
from rest_framework.routers import SimpleRouter

from .views import ActivityViewSet

router = SimpleRouter()
router.register("entries", ActivityViewSet, basename="activity")

urlpatterns: list[URLPattern | URLResolver] = list(router.urls)
