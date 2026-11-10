"""Sentences that tell the user why a job could not do something.

Exception texts are written for whoever maintains the server and stay in its log. The
user gets one of these sentences instead, in their language.
"""

import logging

import mutagen
import requests
from django.utils.translation import gettext as _

from catalog.services.downloading import TrackNotDownloadable
from integrations.audio import AudioError
from integrations.youtube import NoProxyAvailable, YoutubeError
from integrations.ytmusic import YTMusicError
from jobs import runner
from jobs.models import JobRun
from proxies.routing import NoCompatibleProxy

logger = logging.getLogger(__name__)


def reason_for(error: BaseException) -> str:
    """One translated sentence for ``error``, free of technical detail."""
    if isinstance(error, NoCompatibleProxy):
        return _("No proxy can be used for this request. Check the proxies.")
    if isinstance(error, NoProxyAvailable):
        return _("Every proxy is resting. Try again in a while.")
    if isinstance(error, TrackNotDownloadable):
        return _("No video matching this track was found.")
    if isinstance(error, YTMusicError):
        return _("YouTube Music did not answer as expected.")
    if isinstance(error, YoutubeError):
        return _("YouTube did not let it be downloaded.")
    if isinstance(error, AudioError | mutagen.MutagenError):
        return _("The audio file could not be processed.")
    if isinstance(error, requests.RequestException):
        return _("The connection failed.")
    if isinstance(error, OSError):
        return _("The file could not be read or written. Check the folder and its permissions.")
    return _("Something went wrong.")


def report(run: JobRun, item: str, error: BaseException) -> None:
    """Notes on the run that ``item`` failed, and logs the cause for the server."""
    logger.warning("%s: %s: %s", item, type(error).__name__, error)
    runner.problem(run, item, reason_for(error))
