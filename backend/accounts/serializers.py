"""Serializers of the account and session API."""

from typing import Any

from django.conf import settings
from django.contrib.auth import authenticate, password_validation
from django.contrib.auth.models import User
from django.utils.translation import gettext_lazy as _
from rest_framework import serializers


class CredentialsSerializer(serializers.Serializer[Any]):
    username = serializers.CharField(max_length=150)
    password = serializers.CharField(write_only=True, trim_whitespace=False)


class NewAccountSerializer(CredentialsSerializer):
    """Creation of the account, validated with Django's own username and password rules."""

    code = serializers.CharField(
        required=False,
        allow_blank=True,
        write_only=True,
        help_text="Setup code, when the server requires one.",
    )

    def validate_username(self, value: str) -> str:
        # No account exists yet, so there is nothing to be unique against.
        User(username=value).full_clean(exclude=["password"], validate_unique=False)
        return value

    def validate_password(self, value: str) -> str:
        password_validation.validate_password(value)
        return value


class _CurrentPasswordSerializer(serializers.Serializer[Any]):
    """Asks for the current password, so a hijacked session cannot change credentials."""

    current_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_current_password(self, value: str) -> str:
        request = self.context["request"]
        # Through ``authenticate`` rather than ``check_password``, so django-axes counts
        # the failures and a hijacked session cannot guess the password without limit.
        user = authenticate(request._request, username=request.user.get_username(), password=value)
        if user is None:
            raise serializers.ValidationError(_("The current password is not correct."))
        return value


class PasswordChangeSerializer(_CurrentPasswordSerializer):
    new_password = serializers.CharField(write_only=True, trim_whitespace=False)

    def validate_new_password(self, value: str) -> str:
        password_validation.validate_password(value, self.context["request"].user)
        return value


class UsernameChangeSerializer(_CurrentPasswordSerializer):
    username = serializers.CharField(max_length=150)

    def validate_username(self, value: str) -> str:
        user = self.context["request"].user
        user.username = value
        user.full_clean(exclude=["password"])
        return value


class ProfileSerializer(serializers.Serializer[Any]):
    username = serializers.CharField()
    language = serializers.CharField(allow_blank=True)


class MeSerializer(ProfileSerializer):
    failed_attempts = serializers.IntegerField(
        help_text="Failed sign-in attempts since the last successful one."
    )


class LanguageSerializer(serializers.Serializer[Any]):
    language = serializers.ChoiceField(choices=settings.LANGUAGES)


class SetupStatusSerializer(serializers.Serializer[Any]):
    needed = serializers.BooleanField(help_text="The account has not been created yet.")
    code_required = serializers.BooleanField(help_text="Creating it needs the setup code.")
