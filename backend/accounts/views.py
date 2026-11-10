"""Account and session views.

The application has a single account. It is created on first use through ``setup/``,
which closes for good once the account exists.
"""

import hmac
from typing import Any, cast

from axes.models import AccessAttempt
from django.conf import settings
from django.contrib.auth import authenticate, login, logout, update_session_auth_hash
from django.contrib.auth.models import User
from django.db import transaction
from django.db.models import Sum
from django.utils.decorators import method_decorator
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_protect, ensure_csrf_cookie
from drf_spectacular.utils import extend_schema
from rest_framework import status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from activity.services import log_activity
from core.serializers import DetailSerializer

from .models import Profile
from .serializers import (
    CredentialsSerializer,
    LanguageSerializer,
    MeSerializer,
    NewAccountSerializer,
    PasswordChangeSerializer,
    ProfileSerializer,
    SetupStatusSerializer,
    UsernameChangeSerializer,
)


def _me(request: Request) -> User:
    return cast(User, request.user)


def _profile(user: User) -> dict[str, str]:
    language = Profile.objects.filter(user=user).values_list("language", flat=True).first()
    return {"username": user.get_username(), "language": language or ""}


def _failed_attempts(username: str) -> int:
    """Failed sign-ins django-axes currently holds for that username."""
    total = AccessAttempt.objects.filter(username=username).aggregate(
        total=Sum("failures_since_start")
    )["total"]
    return total or 0


def _code_matches(given: object) -> bool:
    """Whether the code sent allows creating the account.

    Without a configured code anything matches. Otherwise it is compared in constant time.
    """
    expected: str = settings.VIBRATTO_SETUP_CODE
    if not expected:
        return True
    return isinstance(given, str) and hmac.compare_digest(given.encode(), expected.encode())


# DRF exempts views without session authentication from CSRF checks; signing in and
# creating the account must enforce them.
@method_decorator(csrf_protect, name="dispatch")
class _AnonymousView(APIView):
    permission_classes = [AllowAny]
    authentication_classes: list[Any] = []


class SetupView(_AnonymousView):
    """Reports whether the account exists and creates it the first time."""

    @extend_schema(responses=SetupStatusSerializer, tags=["accounts"])
    @method_decorator(ensure_csrf_cookie)
    def get(self, request: Request) -> Response:
        """Setup status. Also hands out the CSRF cookie the sign-in form needs."""
        return Response(
            {
                "needed": not User.objects.exists(),
                "code_required": bool(settings.VIBRATTO_SETUP_CODE),
            }
        )

    @extend_schema(
        request=NewAccountSerializer,
        responses={201: ProfileSerializer, 403: DetailSerializer},
        tags=["accounts"],
    )
    def post(self, request: Request) -> Response:
        """Create the account and sign it in."""
        serializer = NewAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        if not _code_matches(serializer.validated_data.get("code")):
            return Response(
                {"detail": _("The setup code is not correct.")},
                status=status.HTTP_403_FORBIDDEN,
            )
        # Checked and created in one transaction, so two simultaneous requests cannot
        # both create an account.
        with transaction.atomic():
            if User.objects.select_for_update().exists():
                return Response(
                    {"detail": _("The account has already been created.")},
                    status=status.HTTP_403_FORBIDDEN,
                )
            user = User.objects.create_superuser(
                serializer.validated_data["username"],
                password=serializer.validated_data["password"],
            )
        login(request._request, user, backend="django.contrib.auth.backends.ModelBackend")
        return Response(_profile(user), status=status.HTTP_201_CREATED)


class LoginView(_AnonymousView):
    """Signs in. django-axes locks out repeated failed attempts."""

    @extend_schema(
        request=CredentialsSerializer,
        responses={200: MeSerializer, 400: DetailSerializer},
        tags=["accounts"],
    )
    def post(self, request: Request) -> Response:
        serializer = CredentialsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        # Read before authenticating: a successful sign-in makes axes clear the attempts.
        failed = _failed_attempts(serializer.validated_data["username"])
        user = authenticate(request._request, **serializer.validated_data)
        if user is None:
            log_activity(
                None,
                "auth.login_failed",
                detail={"username": serializer.validated_data["username"]},
            )
            # The same message for an unknown username and a wrong password.
            return Response(
                {"detail": _("Wrong username or password.")},
                status=status.HTTP_400_BAD_REQUEST,
            )
        login(request._request, user)
        log_activity(user, "auth.login")
        return Response({**_profile(user), "failed_attempts": failed})


class LogoutView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=None, responses={204: None}, tags=["accounts"])
    def post(self, request: Request) -> Response:
        log_activity(_me(request), "auth.logout")
        logout(request._request)
        return Response(status=status.HTTP_204_NO_CONTENT)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(responses=MeSerializer, tags=["accounts"])
    def get(self, request: Request) -> Response:
        """The signed-in account and the failed attempts made during this session."""
        user = _me(request)
        return Response(
            {**_profile(user), "failed_attempts": _failed_attempts(user.get_username())}
        )


class PasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=PasswordChangeSerializer, responses={204: None}, tags=["accounts"])
    def post(self, request: Request) -> Response:
        serializer = PasswordChangeSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = _me(request)
        user.set_password(serializer.validated_data["new_password"])
        user.save()
        # Django invalidates every session when the password changes; this keeps the
        # caller's own session alive.
        update_session_auth_hash(request._request, user)
        return Response(status=status.HTTP_204_NO_CONTENT)


class UsernameChangeView(APIView):
    permission_classes = [IsAuthenticated]

    @extend_schema(request=UsernameChangeSerializer, responses=ProfileSerializer, tags=["accounts"])
    def post(self, request: Request) -> Response:
        serializer = UsernameChangeSerializer(data=request.data, context={"request": request})
        serializer.is_valid(raise_exception=True)
        user = _me(request)
        user.username = serializer.validated_data["username"]
        user.save(update_fields=["username"])
        return Response(_profile(user))


class LanguageView(APIView):
    """Stores the interface language chosen in the web application."""

    permission_classes = [IsAuthenticated]

    @extend_schema(request=LanguageSerializer, responses=LanguageSerializer, tags=["accounts"])
    def put(self, request: Request) -> Response:
        serializer = LanguageSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        Profile.objects.update_or_create(
            user=_me(request), defaults={"language": serializer.validated_data["language"]}
        )
        return Response(serializer.data)
