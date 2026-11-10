# Builds the web interface. Its output is the same for every architecture, so it always
# runs natively.
FROM --platform=$BUILDPLATFORM node:22-slim AS frontend
WORKDIR /src
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.13-slim
# ffmpeg converts the downloaded audio; gettext compiles the translations.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg gettext \
    && rm -rf /var/lib/apt/lists/*

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    DJANGO_SETTINGS_MODULE=config.settings.base \
    DJANGO_ALLOWED_HOSTS=* \
    VIBRATTO_DATA_DIR=/data \
    VIBRATTO_FRONTEND_DIR=/app/frontend-dist

WORKDIR /app/backend
COPY backend/requirements.lock ./
# Exact, hash-checked versions; yt-dlp separately and current, because YouTube changes often.
RUN pip install --no-cache-dir --require-hashes -r requirements.lock \
    && pip install --no-cache-dir --upgrade yt-dlp

COPY backend/ ./
COPY --from=frontend /src/dist /app/frontend-dist
COPY packaging/docker-entrypoint.sh /app/entrypoint.sh
RUN DJANGO_SECRET_KEY=build python manage.py compilemessages -v0 \
    && DJANGO_SECRET_KEY=build python manage.py collectstatic --noinput -v0 \
    && useradd --system --uid 1000 --home-dir /data vibratto \
    && install -d -o vibratto -g vibratto /data

# Starts as root only to make the mounted folders writable, then drops to the vibratto user.
VOLUME /data
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s \
    CMD ["python", "-c", "import urllib.request as r; r.urlopen('http://127.0.0.1:8000/api/health/', timeout=4)"]
ENTRYPOINT ["/app/entrypoint.sh"]
