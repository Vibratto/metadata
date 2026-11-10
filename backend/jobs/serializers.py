"""Task API serializers."""

from typing import Any

from rest_framework import serializers

from jobs import registry
from jobs.models import JobRun, JobRunLine


class JobRunSerializer(serializers.ModelSerializer[JobRun]):
    """State and progress of a run, read only."""

    user = serializers.CharField(source="user.username", read_only=True, default=None)

    class Meta:
        """Todo es de solo lectura: All read only: the engine writes it."""

        model = JobRun
        fields = [
            "id",
            "kind",
            "params",
            "user",
            "status",
            "started_at",
            "finished_at",
            "done",
            "total",
            "current",
            "summary",
        ]
        read_only_fields = fields


class JobRunLineSerializer(serializers.ModelSerializer[JobRunLine]):
    """One log line of a run."""

    class Meta:
        """Lines are immutable."""

        model = JobRunLine
        fields = ["position", "level", "message", "created_at"]
        read_only_fields = fields


class JobStartSerializer(serializers.Serializer[Any]):
    """Request to start a task."""

    kind = serializers.CharField(help_text="Tipo registrado. / Registered kind.")
    params = serializers.DictField(required=False, default=dict, help_text="JSON parameters.")

    def validate_kind(self, value: str) -> str:
        """Accepts registered kinds only."""
        if value not in registry.kinds():
            raise serializers.ValidationError(f"Tipo desconocido: {value}.")
        return value
