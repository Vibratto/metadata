"""Settings shared by every environment."""

import os
from datetime import timedelta
from pathlib import Path

from django.utils.csp import CSP

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# No default: starting without a secret key must fail rather than run insecurely.
SECRET_KEY = os.environ["DJANGO_SECRET_KEY"]
DEBUG = False
ALLOWED_HOSTS = [h for h in os.environ.get("DJANGO_ALLOWED_HOSTS", "").split(",") if h]

INSTALLED_APPS = [
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "rest_framework",
    "drf_spectacular",
    "drf_spectacular_sidecar",
    "django_filters",
    "simple_history",
    "django_db_logger",
    "axes",
    "core",
    "accounts",
    "catalog",
    "jobs",
    "watches",
    "proxies",
    "activity",
    "preferences",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.csp.ContentSecurityPolicyMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "core.session.IdleSessionMiddleware",
    # After the session and before CommonMiddleware, as Django requires.
    "django.middleware.locale.LocaleMiddleware",
    # After the locale, so it rejects in the requested language; before CSRF and auth.
    "core.api_guard.FrontendOnlyMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    # Last, so it sees the final response and can lock out.
    "axes.middleware.AxesMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

# --- Data ---

# Where the database lives. The packages point this at a persistent folder.
DATA_DIR = Path(os.environ.get("VIBRATTO_DATA_DIR", BASE_DIR))
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": DATA_DIR / "db.sqlite3",
        "OPTIONS": {
            # Background jobs write while the web interface reads. WAL lets readers carry
            # on during a write, and the timeout makes a second writer wait its turn
            # instead of failing with "database is locked".
            "init_command": "PRAGMA journal_mode=WAL; PRAGMA synchronous=NORMAL;",
            "timeout": 30,
            "transaction_mode": "IMMEDIATE",
        },
    }
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Language ---

# English first; Spanish is selected through the Accept-Language header.
LANGUAGE_CODE = "en"
LANGUAGES = [("en", "English"), ("es", "Español")]
LOCALE_PATHS = [BASE_DIR / "locale"]
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# --- Static files and frontend ---

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# The application serves the built frontend itself, so no web server is needed in front.
FRONTEND_DIST = Path(os.environ.get("VIBRATTO_FRONTEND_DIR", BASE_DIR.parent / "frontend" / "dist"))
if FRONTEND_DIST.is_dir():
    WHITENOISE_ROOT = FRONTEND_DIST

# --- API ---

# The API exists for the frontend only; see core/api_guard.py.
API_FRONTEND_ONLY = True

REST_FRAMEWORK: dict[str, object] = {
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "EXCEPTION_HANDLER": "core.exceptions.api_exception_handler",
    # Session cookie plus the X-CSRFToken header, and closed unless a view says otherwise.
    "DEFAULT_AUTHENTICATION_CLASSES": ["rest_framework.authentication.SessionAuthentication"],
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.IsAuthenticated"],
}

SPECTACULAR_SETTINGS = {
    "TITLE": "Vibratto Metadata API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    # Separate types for what is sent and what is received, e.g. for write-only fields.
    "COMPONENT_SPLIT_REQUEST": True,
    # Swagger UI served from static files rather than a CDN, which the CSP would block.
    "SWAGGER_UI_DIST": "SIDECAR",
}

# --- Account and sign-in ---

AUTHENTICATION_BACKENDS = [
    "axes.backends.AxesStandaloneBackend",
    "django.contrib.auth.backends.ModelBackend",
]

AXES_FAILURE_LIMIT = 5
AXES_COOLOFF_TIME = timedelta(minutes=15)
# Locked per username and origin, so an attacker cannot lock the owner out from elsewhere.
AXES_LOCKOUT_PARAMETERS = [["username", "ip_address"]]
AXES_RESET_ON_SUCCESS = True

# Behind a reverse proxy every request arrives from the proxy's address, so five failures
# by anyone would lock everyone out. With DJANGO_AXES_TRUST_FORWARDED_FOR=1 axes uses the
# address the proxy appended to X-Forwarded-For; whatever the client sent sits to its left
# and is ignored. Unset, the header is not trusted, since a direct client could forge it.
# shortcut: a single trusted proxy; for a chain of proxies set AXES_IPWARE_PROXY_COUNT.
if os.environ.get("DJANGO_AXES_TRUST_FORWARDED_FOR") == "1":
    # axes silently ignores these settings without django-ipware; better not to start.
    import ipware  # noqa: F401

    AXES_IPWARE_PROXY_ORDER = "right-most"
    AXES_IPWARE_META_PRECEDENCE_ORDER = ["HTTP_X_FORWARDED_FOR"]

# One-time code required to create the account. The packages generate it on install;
# without it, whoever reached the web interface first would own the installation.
VIBRATTO_SETUP_CODE = os.environ.get("VIBRATTO_SETUP_CODE", "")

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": f"django.contrib.auth.password_validation.{name}"}
    for name in (
        "UserAttributeSimilarityValidator",
        "MinimumLengthValidator",
        "CommonPasswordValidator",
        "NumericPasswordValidator",
    )
]

# The session expires after this much inactivity; every request renews it.
SESSION_COOKIE_AGE = int(os.environ.get("DJANGO_SESSION_IDLE_SECONDS", 30 * 60))
SESSION_SAVE_EVERY_REQUEST = True
SESSION_COOKIE_SECURE = True
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
# The frontend reads the CSRF cookie and echoes it in a header, so it cannot be HttpOnly.
CSRF_COOKIE_SECURE = True
CSRF_COOKIE_SAMESITE = "Lax"

# --- Transport security ---

# Behind a proxy that terminates TLS its header must be trusted, or the redirect to HTTPS
# loops. Opt-in, because a direct client could forge the header.
if os.environ.get("DJANGO_TRUST_PROXY_SSL_HEADER") == "1":
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 365
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True

# Plain HTTP on a trusted local network. Opt-in: without HTTPS there can be no Secure
# cookies, no redirect and no HSTS.
if os.environ.get("DJANGO_ALLOW_INSECURE_HTTP") == "1":
    SESSION_COOKIE_SECURE = False
    CSRF_COOKIE_SECURE = False
    SECURE_SSL_REDIRECT = False
    SECURE_HSTS_SECONDS = 0

X_FRAME_OPTIONS = "DENY"

# No 'unsafe-inline' or 'unsafe-eval': the built frontend only loads its own files.
SECURE_CSP = {
    "default-src": [CSP.SELF],
    "script-src": [CSP.SELF],
    "style-src": [CSP.SELF],
    # Covers and artist pictures come from YouTube Music's image hosts.
    "img-src": [CSP.SELF, "data:", "https:"],
    "frame-src": ["https://www.youtube-nocookie.com"],
    "object-src": [CSP.NONE],
    "base-uri": [CSP.SELF],
    "form-action": [CSP.SELF],
    "frame-ancestors": [CSP.NONE],
}

# --- Logging ---

# With the formatter on, the message stored in the database includes the job id.
DJANGO_DB_LOGGER_ENABLE_FORMATTER = True

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "job_id": {"()": "activity.logs.JobIdFilter"},
        # Filters sit on each handler because a logger's filters do not apply to its
        # children.
        "sensitive": {"()": "activity.logs.SensitiveDataFilter"},
    },
    "formatters": {
        "plain": {"format": "%(asctime)s %(levelname)s [job %(job_id)s] %(name)s: %(message)s"},
        "db": {"format": "[job %(job_id)s] %(message)s"},
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "plain",
            "filters": ["job_id", "sensitive"],
        },
        "db": {
            "class": "django_db_logger.db_log_handler.DatabaseLogHandler",
            "level": "INFO",
            "formatter": "db",
            "filters": ["job_id", "sensitive"],
        },
    },
    "root": {"handlers": ["console", "db"], "level": "INFO"},
    # axes logs an INFO line while starting, before the log table exists on a fresh
    # database. Lockouts and failed sign-ins are WARNING and are still stored.
    "loggers": {"axes": {"level": "WARNING"}},
}

# --- Background jobs ---

# At most one job of each kind runs at a time, so a few threads are plenty.
JOBS_MAX_WORKERS = 4
# When True, jobs run in the thread that starts them. Used by the tests.
JOBS_SYNCHRONOUS = False
