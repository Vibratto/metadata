"""Serializers shared by several apps; they describe responses in the OpenAPI schema."""

from typing import Any

from rest_framework import serializers


class HealthSerializer(serializers.Serializer[Any]):
    status = serializers.CharField()
    message = serializers.CharField()


class DetailSerializer(serializers.Serializer[Any]):
    """An error body with a readable message."""

    detail = serializers.CharField()
