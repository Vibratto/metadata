"""Root URL configuration."""

from django.conf import settings
from django.urls import include, path, re_path
from django.views.decorators.csp import csp_override
from drf_spectacular.views import SpectacularAPIView, SpectacularSwaggerView

from core.views import spa

API_APPS = ["accounts", "catalog", "jobs", "watches", "proxies", "activity", "preferences"]

urlpatterns = [
    path("api/schema/", SpectacularAPIView.as_view(), name="schema"),
    path("api/", include("core.urls")),
    *(path(f"api/v1/{app}/", include(f"{app}.urls")) for app in API_APPS),
]

if settings.DEBUG:
    # Swagger UI starts with an inline script and style, which the strict policy blocks.
    # It is relaxed for this view alone, and only in development.
    _csp_swagger = csp_override(
        {
            "default-src": ["'self'"],
            "script-src": ["'self'", "'unsafe-inline'"],
            "style-src": ["'self'", "'unsafe-inline'"],
            "img-src": ["'self'", "data:"],
        }
    )
    urlpatterns.append(
        path("api/docs/", _csp_swagger(SpectacularSwaggerView.as_view(url_name="schema")))
    )

# Last: everything outside the API belongs to the built frontend.
urlpatterns.append(re_path(r"^(?!api/).*$", spa))
