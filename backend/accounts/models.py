"""Models of the ``accounts`` app."""

from django.conf import settings
from django.db import models


class Profile(models.Model):
    """Personal preferences of the account."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    language = models.CharField(max_length=2, choices=settings.LANGUAGES, blank=True)

    def __str__(self) -> str:
        return f"{self.user_id}:{self.language or '-'}"
