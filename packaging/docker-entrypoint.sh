#!/bin/sh
# Container start-up: generates the secrets once, updates the database and starts the server.
set -e

# Docker creates a missing bind-mounted folder as root. Hand the data and music folders to
# the unprivileged user and carry on as that user.
if [ "$(id -u)" = 0 ]; then
  mkdir -p /data/music
  chown vibratto:vibratto /data /data/music
  # setpriv keeps root's HOME, where the server cannot write its control socket.
  HOME=/data exec setpriv --reuid=vibratto --regid=vibratto --init-groups "$0" "$@"
fi

# The secret key and the setup code are generated on the first start and kept with the data,
# so they survive when the container is recreated. Values passed to the container win.
secrets=/data/secrets.env
if [ ! -f "$secrets" ]; then
  (
    umask 077
    python - > "$secrets" <<'PY'
import secrets

print(f"DJANGO_SECRET_KEY={secrets.token_urlsafe(48)}")
print(f"VIBRATTO_SETUP_CODE={secrets.token_urlsafe(18)}")
PY
  )
fi
while IFS='=' read -r key value; do
  eval "current=\${$key:-}"
  [ -n "$current" ] || export "$key=$value"
done < "$secrets"

python manage.py migrate --noinput

# Until the account exists, the web interface asks for this code to create it.
if python manage.py shell -c 'from django.contrib.auth.models import User; raise SystemExit(User.objects.exists())' >/dev/null; then
  echo "Setup code: $VIBRATTO_SETUP_CODE"
fi

# A single worker: background jobs run inside the process.
exec gunicorn config.wsgi:application --workers 1 --threads 8 --bind 0.0.0.0:8000
