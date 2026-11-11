"""Models of the ``accounts`` app."""

from django.conf import settings
from django.contrib.auth.models import User
from django.db import models


class Profile(models.Model):
    """Personal preferences of the account."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    language = models.CharField(max_length=2, choices=settings.LANGUAGES, blank=True)

    def __str__(self) -> str:
        return f"{self.user_id}:{self.language or '-'}"


def language_of(user: User | None) -> str:
    """Interface language to write to ``user`` in.

    Work nobody started, such as a scheduled check, uses the language chosen in the
    application, which has a single account.
    """
    profiles = Profile.objects.exclude(language="")
    if user is not None:
        profiles = profiles.filter(user=user)
    chosen = profiles.values_list("language", flat=True).first()
    return chosen or settings.LANGUAGE_CODE[:2]
