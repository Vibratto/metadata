"""``jobs`` app URLs."""

from rest_framework.routers import DefaultRouter

from .views import JobRunViewSet

router = DefaultRouter()
router.register("runs", JobRunViewSet, basename="run")

urlpatterns = router.urls
