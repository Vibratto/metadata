"""URLs of the catalogue API."""

from django.urls import URLPattern, URLResolver, path
from rest_framework.routers import SimpleRouter

from .backup import LibraryBackupPreviewView, LibraryExportView, LibraryRestoreView
from .search import CatalogSearchView
from .upload import TrackUploadView
from .video import TrackVideoView
from .views import (
    AlbumViewSet,
    ArtistLookupView,
    ArtistViewSet,
    BlockedItemViewSet,
    LibrarySummaryView,
    RecordingViewSet,
    TrackViewSet,
)

router = SimpleRouter()
router.register("artists", ArtistViewSet, basename="artist")
router.register("albums", AlbumViewSet, basename="album")
router.register("recordings", RecordingViewSet, basename="recording")
router.register("tracks", TrackViewSet, basename="track")
router.register("blocked", BlockedItemViewSet, basename="blocked")

urlpatterns: list[URLPattern | URLResolver] = [
    path("summary/", LibrarySummaryView.as_view(), name="library-summary"),
    path("search/", CatalogSearchView.as_view(), name="catalog-search"),
    path("ytmusic/artists/", ArtistLookupView.as_view(), name="ytmusic-artist-lookup"),
    path("tracks/<int:pk>/upload/", TrackUploadView.as_view(), name="track-upload"),
    path("tracks/<int:pk>/video/", TrackVideoView.as_view(), name="track-video"),
    path("backup/", LibraryExportView.as_view(), name="library-export"),
    path("backup/preview/", LibraryBackupPreviewView.as_view(), name="library-backup-preview"),
    path("backup/restore/", LibraryRestoreView.as_view(), name="library-restore"),
    *router.urls,
]
