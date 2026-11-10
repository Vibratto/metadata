"""``proxies`` app URLs."""

from rest_framework.routers import SimpleRouter

from . import views

router = SimpleRouter()
router.register("", views.ProxyViewSet, basename="proxy")

urlpatterns = router.urls
