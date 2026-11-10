"""``watches`` app URLs."""

from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("", views.WatchViewSet, basename="watch")

urlpatterns = router.urls
