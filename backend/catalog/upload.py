"""Manual upload of the audio of a track that cannot be downloaded."""

import logging
import tempfile
from pathlib import Path
from typing import Any

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils.translation import gettext as _
from drf_spectacular.utils import extend_schema
from rest_framework import serializers, status
from rest_framework.exceptions import ValidationError
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from activity.services import log_activity
from core.serializers import DetailSerializer
from integrations.audio import AudioError, InvalidAudio, convert
from integrations.audio.validate import MAX_BYTES, validate_audio
from preferences.models import get_value

from .models import Download, Track
from .serializers import TrackSerializer
from .services import lyrics, replaygain
from .services.importing import FETCH_ERRORS
from .services.library import absolute, download_folder, store
from .views import _user

logger = logging.getLogger(__name__)

# Room for the multipart headers; a body larger than this is refused without being read.
MULTIPART_OVERHEAD = 1024 * 1024


class TrackUploadSerializer(serializers.Serializer[Any]):
    file = serializers.FileField(help_text="mp3, m4a, flac, opus, ogg or wav; 200 MB at most.")


class TrackUploadView(APIView):
    """Receives a track's audio and stores it exactly as a download would."""

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    @extend_schema(
        description=(
            "Validates the file (type and size), converts it to the configured format, tags "
            "it from the catalogue, files it with the naming template and records a "
            "download with no source URL."
        ),
        request={"multipart/form-data": TrackUploadSerializer},
        responses={
            201: TrackSerializer,
            400: DetailSerializer,
            404: DetailSerializer,
            413: DetailSerializer,
            422: DetailSerializer,
        },
        tags=["catalog"],
    )
    def post(self, request: Request, pk: int) -> Response:
        track = get_object_or_404(Track.objects.select_related("album", "recording"), pk=pk)
        # Checked before parsing: otherwise the whole body is spooled to disk first,
        # however large it is.
        declared = request.META.get("CONTENT_LENGTH", "")
        if declared.isdigit() and int(declared) > MAX_BYTES + MULTIPART_OVERHEAD:
            return Response(
                {"detail": _("The file is too large.")},
                status=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            )
        serializer = TrackUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        uploaded = serializer.validated_data["file"]
        fmt = get_value("download.format")
        folder = download_folder()
        # As with downloads, the work happens in a temporary folder and only the finished
        # file reaches the library.
        with tempfile.TemporaryDirectory() as tmp:
            work = Path(tmp)
            # Only the extension of the original name is used; the catalogue names the file.
            source = work / f"upload{Path(uploaded.name).suffix.lower()}"
            with source.open("wb") as out:
                for chunk in uploaded.chunks():
                    out.write(chunk)
            try:
                validate_audio(source, max_bytes=MAX_BYTES)
            except InvalidAudio as error:
                raise ValidationError(
                    {"file": [_("The file is not valid audio, or it is larger than 200 MB.")]}
                ) from error
            try:
                converted = convert(source, work, fmt, stem="track")
                loudness = replaygain.measure(converted)
                stored = store(
                    track,
                    converted,
                    folder=folder,
                    template=get_value("download.name_template"),
                    loudness=loudness,
                )
            except AudioError:
                return Response(
                    {"detail": _("The audio could not be converted.")},
                    status=status.HTTP_422_UNPROCESSABLE_ENTITY,
                )
        with transaction.atomic():
            download = Download.objects.create(track=track, file_path=stored, audio_format=fmt)
            replaygain.remember(download, loudness)
            log_activity(
                _user(request),
                "catalog.track.uploaded",
                track,
                {"file_path": stored, "audio_format": fmt},
            )
        # shortcut: lyrics are fetched inside the request and can add a few seconds; move
        # this to a background job if uploads start to feel slow.
        if get_value("lyrics.enabled"):
            try:
                lyrics.save_lyrics(track, absolute(stored), lyrics.lyrics_client())
            except (*FETCH_ERRORS, OSError):
                # Lyrics are an extra: the upload is done and must not fail because of them.
                logger.warning("No lyrics for track %s", track.pk, exc_info=True)
        return Response(
            TrackSerializer(Track.objects.with_downloaded().get(pk=track.pk)).data,
            status=status.HTTP_201_CREATED,
        )
