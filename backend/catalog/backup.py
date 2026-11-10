"""Library backup as JSON: export, preview and restore.

The backup is ``dumpdata`` output for the library models and is loaded with ``loaddata``
by the ``library_restore`` job. Rows that already exist are left alone, which respects
the append-only tables and never overwrites an edit. A backup that clashes with this
library (see :func:`check_fits`) is refused as a whole.
"""

import json
import tempfile
from collections import defaultdict
from io import StringIO
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, cast

from django.contrib.auth.models import User
from django.core import serializers as django_serializers
from django.core.exceptions import FieldDoesNotExist
from django.core.management import call_command
from django.core.serializers.base import DeserializationError
from django.db.models import Model
from django.http import HttpResponse
from django.utils import timezone
from django.utils.translation import gettext as _
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiResponse, extend_schema
from rest_framework import serializers, status
from rest_framework.parsers import MultiPartParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from activity.services import log_activity
from core.serializers import DetailSerializer
from jobs import runner
from jobs.serializers import JobRunSerializer

#: Library models, in dependency order. History tables are left out: they point to users
#: that do not exist on another installation.
LIBRARY_MODELS = (
    "catalog.artist",
    "catalog.album",
    "catalog.albumartist",
    "catalog.recording",
    "catalog.recordingartist",
    "catalog.track",
    "catalog.blockeditem",
    "catalog.download",
)

#: What the preview counts.
PREVIEW_MODELS = {
    "artists": "catalog.artist",
    "albums": "catalog.album",
    "tracks": "catalog.track",
    "downloads": "catalog.download",
}

#: Prefix of the uploaded files the restore job accepts.
UPLOAD_PREFIX = "vibratto-restore-"


class BackupError(ValueError):
    """The file is not a valid library backup."""


def export_library() -> str:
    """The whole library as ``dumpdata`` JSON."""
    out = StringIO()
    call_command("dumpdata", *LIBRARY_MODELS, format="json", stdout=out)
    return out.getvalue()


def parse_backup(data: bytes) -> list[tuple[dict[str, Any], Model]]:
    """Validate a backup and return each entry with its unsaved object.

    Raises:
        BackupError: It is not JSON, it holds other models, or a field does not fit.
    """
    try:
        entries = json.loads(data)
    except ValueError:
        raise BackupError(_("The file is not valid JSON.")) from None
    if not isinstance(entries, list) or not all(
        isinstance(e, dict)
        and e.get("model") in LIBRARY_MODELS
        and isinstance(e.get("fields"), dict)
        for e in entries
    ):
        raise BackupError(_("The file is not a library backup."))
    if not all(_inside_library(e) for e in entries if e["model"] == "catalog.download"):
        # Deleting or relocating such a download would touch a file outside the library.
        raise BackupError(_("The backup has download paths outside the library."))
    try:
        objects = [d.object for d in django_serializers.deserialize("python", entries)]
    except (DeserializationError, FieldDoesNotExist) as error:
        message = _("The backup has invalid data: %(error)s") % {"error": error}
        raise BackupError(message) from None
    return list(zip(entries, objects, strict=True))


def _inside_library(entry: dict[str, Any]) -> bool:
    """Whether a download path is relative and stays inside the library."""
    path = entry["fields"].get("file_path")
    if not isinstance(path, str) or not path:
        return False
    return not any(
        flavour.is_absolute() or flavour.drive or ".." in flavour.parts
        for flavour in (PurePosixPath(path), PureWindowsPath(path))
    )


#: What identifies a row besides its ``pk``, for the models without an external id.
NATURAL_KEYS: dict[str, tuple[str, ...]] = {
    "catalog.albumartist": ("album_id", "artist_id"),
    "catalog.recordingartist": ("recording_id", "artist_id"),
    "catalog.track": ("album_id", "disc_number", "track_number"),
    "catalog.blockeditem": ("kind", "external_id"),
    "catalog.download": ("track_id", "file_path"),
}

NEW, EXISTING, CLASH = "new", "existing", "clash"


def _classify(parsed: list[tuple[dict[str, Any], Model]]) -> list[str]:
    """Whether each entry is new, already stored, or clashes with a different row here.

    The ``pk`` alone cannot tell: on another installation the same ``pk`` is another
    item. Models with an external id compare it. An id is never changed or cleared, only
    assigned later, so a stored id missing from the backup is fine, but a different one,
    or a backup id held by another row, is a clash. The other models compare their
    natural key; one that exists under another ``pk`` (credits are recreated when
    edited) counts as stored.

    shortcut: a row with no external id at all, such as a guest artist named only in a
    title, is matched by ``pk`` alone because its name may have been edited. A clash
    there goes unnoticed unless a credit pointing to it clashes. Compare names if that
    ever bites.
    """
    by_model: dict[type[Model], list[Model]] = defaultdict(list)
    for _entry, obj in parsed:
        by_model[type(obj)].append(obj)
    status: dict[int, str] = {}
    for model, objs in by_model.items():
        fields = getattr(model, "immutable_fields", None)
        if fields:
            # Every row at once: a huge ``pk__in`` would exceed SQLite's parameter limit.
            stored = {row[0]: row[1:] for row in model._default_manager.values_list("pk", *fields)}
            owner = {
                (field, value): pk
                for pk, values in stored.items()
                for field, value in zip(fields, values, strict=True)
                if value is not None
            }
            for obj in objs:
                ids = [(f, getattr(obj, f)) for f in fields if getattr(obj, f) is not None]
                # Each backup id must belong to the row with the same ``pk`` or, when
                # there is no such row, to none.
                expected = obj.pk if obj.pk in stored else None
                if any(owner.get(pair) != expected for pair in ids):
                    status[id(obj)] = CLASH
                else:
                    status[id(obj)] = EXISTING if obj.pk in stored else NEW
        else:
            key = NATURAL_KEYS[model._meta.label_lower]
            rows = {row[0]: row[1:] for row in model._default_manager.values_list("pk", *key)}
            keys = set(rows.values())
            for obj in objs:
                mine = tuple(getattr(obj, f) for f in key)
                if obj.pk in rows:
                    status[id(obj)] = EXISTING if rows[obj.pk] == mine else CLASH
                else:
                    status[id(obj)] = EXISTING if mine in keys else NEW
    return [status[id(obj)] for _entry, obj in parsed]


def check_fits(parsed: list[tuple[dict[str, Any], Model]]) -> list[str]:
    """Classify the entries, refusing the backup if any of them clashes.

    Raises:
        BackupError: The backup clashes with rows of this library.
    """
    statuses = _classify(parsed)
    clashes = [entry for (entry, _obj), st in zip(parsed, statuses, strict=True) if st == CLASH]
    if clashes:
        first = clashes[0]
        message = _(
            "The backup clashes with this library: %(count)d items match different ones "
            "(for example, %(model)s #%(pk)s). Restore it on an empty installation or on "
            "the one it came from."
        ) % {"count": len(clashes), "model": first["model"], "pk": first["pk"]}
        raise BackupError(message)
    return statuses


def preview(parsed: list[tuple[dict[str, Any], Model]]) -> dict[str, dict[str, int]]:
    """How many items of each kind the backup holds, and how many already exist.

    Raises:
        BackupError: The backup clashes with this library.
    """
    counts = {key: {"total": 0, "existing": 0} for key in PREVIEW_MODELS}
    labels = {label: key for key, label in PREVIEW_MODELS.items()}
    for (entry, _obj), st in zip(parsed, check_fits(parsed), strict=True):
        if key := labels.get(entry["model"]):
            counts[key]["total"] += 1
            counts[key]["existing"] += st == EXISTING
    return counts


def restore(parsed: list[tuple[dict[str, Any], Model]]) -> dict[str, int]:
    """Load the entries the library lacks.

    Returns:
        How many entries were created and how many were skipped.

    Raises:
        BackupError: The backup clashes with this library.
    """
    flags = zip(parsed, check_fits(parsed), strict=True)
    new = [entry for (entry, _obj), st in flags if st == NEW]
    if new:
        # ``loaddata`` only reads files, but it takes care of the transaction, the
        # loading order and the id sequences.
        with tempfile.TemporaryDirectory() as folder:
            fixture = Path(folder) / "library.json"
            fixture.write_text(json.dumps(new))
            call_command("loaddata", str(fixture), verbosity=0)
    return {"created": len(new), "skipped": len(parsed) - len(new)}


def upload_path(name: object) -> Path:
    """Path of an uploaded backup, always inside the temporary folder.

    Raises:
        BackupError: The name is not that of an upload.
    """
    if not isinstance(name, str) or not name.startswith(UPLOAD_PREFIX) or Path(name).name != name:
        raise BackupError(_("Unknown backup file."))
    return Path(tempfile.gettempdir()) / name


class BackupUploadSerializer(serializers.Serializer[Any]):
    file = serializers.FileField(help_text="An exported JSON backup.")


class BackupCountSerializer(serializers.Serializer[Any]):
    total = serializers.IntegerField()
    existing = serializers.IntegerField(help_text="Already in the library.")


class BackupPreviewSerializer(serializers.Serializer[Any]):
    artists = BackupCountSerializer()
    albums = BackupCountSerializer()
    tracks = BackupCountSerializer()
    downloads = BackupCountSerializer()


def _read_upload(request: Request) -> bytes:
    body = BackupUploadSerializer(data=request.data)
    body.is_valid(raise_exception=True)
    data: bytes = body.validated_data["file"].read()
    return data


def _bad_file(error: BackupError) -> Response:
    return Response({"detail": str(error)}, status=status.HTTP_400_BAD_REQUEST)


_INVALID = OpenApiResponse(DetailSerializer, description="Invalid file.")


class LibraryExportView(APIView):
    """Downloads the whole library as a JSON file."""

    permission_classes = [IsAuthenticated]

    @extend_schema(
        responses={
            (200, "application/json"): OpenApiResponse(
                OpenApiTypes.BINARY, description="Backup file."
            )
        },
        tags=["catalog"],
    )
    def get(self, request: Request) -> HttpResponse:
        response = HttpResponse(export_library(), content_type="application/json")
        name = f"vibratto-metadata-{timezone.localdate():%Y%m%d}.json"
        response["Content-Disposition"] = f'attachment; filename="{name}"'
        return response


class LibraryBackupPreviewView(APIView):
    """Counts what a backup holds and what already exists. Changes nothing."""

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    @extend_schema(
        request={"multipart/form-data": BackupUploadSerializer},
        responses={200: BackupPreviewSerializer, 400: _INVALID},
        tags=["catalog"],
    )
    def post(self, request: Request) -> Response:
        try:
            counts = preview(parse_backup(_read_upload(request)))
        except BackupError as error:
            return _bad_file(error)
        return Response(BackupPreviewSerializer(counts).data)


class LibraryRestoreView(APIView):
    """Validates a backup and starts the ``library_restore`` job.

    The job adds what is missing and never rewrites rows that exist.
    """

    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser]

    @extend_schema(
        request={"multipart/form-data": BackupUploadSerializer},
        responses={
            201: JobRunSerializer,
            400: _INVALID,
            409: OpenApiResponse(DetailSerializer, description="Another restore is running."),
        },
        tags=["catalog"],
    )
    def post(self, request: Request) -> Response:
        try:
            data = _read_upload(request)
            check_fits(parse_backup(data))
        except BackupError as error:
            return _bad_file(error)
        with tempfile.NamedTemporaryFile(prefix=UPLOAD_PREFIX, suffix=".json", delete=False) as out:
            out.write(data)
        user = cast(User, request.user)
        try:
            run = runner.start("library_restore", {"file": Path(out.name).name}, user)
        except runner.JobAlreadyRunning:
            Path(out.name).unlink()
            return Response(
                {"detail": _("A job of this kind is already running.")},
                status=status.HTTP_409_CONFLICT,
            )
        log_activity(user, "catalog.library.restore_started", run)
        return Response(JobRunSerializer(run).data, status=status.HTTP_201_CREATED)
