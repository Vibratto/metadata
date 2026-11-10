"""Merge two recordings, or split a track off the recording it shares.

The importer decides by video id which tracks share a recording. These two operations
let the user correct it: a single and its album sometimes use different videos for the
same song, and occasionally one video is reused for different edits.
"""

from django.db import transaction
from django.utils.translation import gettext as _

from catalog.models import Recording, RecordingArtist, Track


class RecordingError(ValueError):
    """The operation is not possible; the message is meant for the user."""


def merge_recordings(keep: Recording, absorbed: Recording) -> Recording:
    """Move the tracks of ``absorbed`` to ``keep`` and delete ``absorbed``.

    ``keep`` takes the duration and video id from ``absorbed`` when it lacks them.

    Raises:
        RecordingError: Both are the same recording, or both have a track on the same
            album (an album cannot hold one recording twice).
    """
    if keep.pk == absorbed.pk:
        raise RecordingError(_("A recording cannot be merged with itself."))
    albums = Track.objects.filter(recording=absorbed).values("album")
    if Track.objects.filter(recording=keep, album__in=albums).exists():
        raise RecordingError(_("Both recordings have a track on the same album."))
    duration, video_id = absorbed.duration, absorbed.video_id
    with transaction.atomic():
        Track.objects.filter(recording=absorbed).update(recording=keep)
        # Deleting it first frees its video id, which is unique.
        absorbed.delete()
        keep.duration = keep.duration or duration
        keep.video_id = keep.video_id or video_id
        keep.explicit = keep.explicit or absorbed.explicit
        keep.save()
    return keep


def split_track(track: Track) -> Recording:
    """Give ``track`` a recording of its own, copied from the one it shared.

    Title, duration, explicit flag and credits are copied. The video id is unique and
    stays with the original, so the new recording is downloaded by search.

    Raises:
        RecordingError: The recording has no other track.
    """
    original = track.recording
    if not Track.objects.filter(recording=original).exclude(pk=track.pk).exists():
        raise RecordingError(_("This is the recording's only track: there is nothing to split."))
    with transaction.atomic():
        copy = Recording.objects.create(
            title=original.title, duration=original.duration, explicit=original.explicit
        )
        RecordingArtist.objects.bulk_create(
            RecordingArtist(recording=copy, artist_id=c.artist_id, position=c.position)
            for c in original.credits.all()
        )
        track.recording = copy
        track.save(update_fields=["recording"])
    return copy
