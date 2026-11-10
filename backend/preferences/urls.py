"""``preferences`` app URLs."""

from django.urls import path

from . import views

urlpatterns = [
    path("", views.PreferenceListView.as_view(), name="preference-list"),
    # Keys contain dots (e.g. ``download.format``); ``str`` matches them.
    path("<str:key>/", views.PreferenceDetailView.as_view(), name="preference-detail"),
]
