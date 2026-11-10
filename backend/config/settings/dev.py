"""Settings for local development."""

import os

os.environ.setdefault("DJANGO_SECRET_KEY", "dev-only-insecure-key")

from .base import *  # noqa: E402, F403

DEBUG = True
ALLOWED_HOSTS = ["localhost", "127.0.0.1"]

# No HTTPS locally: secure cookies and the redirect would make signing in impossible.
SECURE_SSL_REDIRECT = False
SESSION_COOKIE_SECURE = False
CSRF_COOKIE_SECURE = False
SECURE_HSTS_SECONDS = 0
