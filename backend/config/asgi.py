"""ASGI entry point."""

import os

from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.base")

application = get_asgi_application()

# Once Django is loaded: this touches the database and starts the scheduler.
from jobs.startup import start  # noqa: E402

start()
