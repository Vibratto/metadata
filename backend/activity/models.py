"""``activity`` app models."""

from django.conf import settings
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.db import models

from core.models import AppendOnlyModel


class ActivityLog(AppendOnlyModel):
    """Who did what and when.

    The username is stored too so the record still
    says who acted after the account is deleted.
    """

    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL
    )
    username = models.CharField(max_length=150, blank=True)
    action = models.CharField(max_length=100, db_index=True)
    content_type = models.ForeignKey(ContentType, null=True, blank=True, on_delete=models.SET_NULL)
    # Text rather than integer: related objects may have non-numeric keys.
    object_id = models.CharField(max_length=64, blank=True)
    target = GenericForeignKey("content_type", "object_id")
    detail = models.JSONField(default=dict, blank=True)

    class Meta:
        """Most recent first."""

        ordering = ["-created_at", "-id"]
