"""The video a track would be downloaded from, to preview it first."""

import time
from typing import Any

from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from core.serializers import DetailSerializer
from integrations.youtube import NoProxyAvailable, YoutubeError, preview_embed_url
from proxies.routing import NoCompatibleProxy

from .models import Track
from .services.downloading import TrackNotDownloadable, build_pool, video_id_for


class VideoSerializer(serializers.Serializer[Any]):
    video_id = serializers.CharField()
    embed_url = serializers.URLField(help_text="URL for an iframe on youtube-nocookie.com.")


class TrackVideoView(APIView):
    """Returns the video a download would use.

    Tracks imported from YouTube Music answer at once with their own video. The rest are
    searched for, with the same rule the download applies.
    """

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={
            200: VideoSerializer,
            404: DetailSerializer,
            502: DetailSerializer,
            503: DetailSerializer,
        },
        tags=["catalog"],
    )
    def get(self, request: Request, pk: int) -> Response:
        track = get_object_or_404(Track.objects.select_related("album", "recording"), pk=pk)
        try:
            proxy = None if track.video_id else build_pool().acquire(time.monotonic())
            video_id = video_id_for(track, proxy)
        except TrackNotDownloadable:
            return _problem(_("No video matches the track."), status.HTTP_404_NOT_FOUND)
        except NoProxyAvailable:
            return _problem(_("Every proxy is cooling down."), status.HTTP_503_SERVICE_UNAVAILABLE)
        except NoCompatibleProxy as error:
            return _problem(str(error), status.HTTP_503_SERVICE_UNAVAILABLE)
        except YoutubeError:
            return _problem(_("The video search failed."), status.HTTP_502_BAD_GATEWAY)
        return Response({"video_id": video_id, "embed_url": preview_embed_url(video_id)})


def _problem(detail: str, code: int) -> Response:
    return Response({"detail": detail}, status=code)
