"""Settings for the test suite."""

import os

os.environ.setdefault("DJANGO_SECRET_KEY", "test-only-insecure-key")

from .base import *  # noqa: E402, F403

# Fast hashing: password strength is not what these tests exercise.
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# Hosts the models some tests need, such as a concrete ``AppendOnlyModel``.
INSTALLED_APPS = [*INSTALLED_APPS, "tests.testapp"]  # noqa: F405

# The test client speaks HTTP. Cookies keep their Secure flag so tests can assert it.
SECURE_SSL_REDIRECT = False

# Jobs run in the test's own thread, so they share its transaction.
JOBS_SYNCHRONOUS = True

# Tests call the API directly; the frontend-only restriction has its own tests.
API_FRONTEND_ONLY = False
