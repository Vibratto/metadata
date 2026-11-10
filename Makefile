.PHONY: dev lint test migrate api lock

# Starts the backend and the frontend.
dev:
	cd backend && python manage.py compilemessages -v0 && python manage.py runserver & \
	cd frontend && npm run dev

lint:
	cd backend && ruff check . && ruff format --check . && mypy .
	cd frontend && npm run lint && npm run typecheck

test:
	cd backend && python manage.py compilemessages -v0 && pytest
	cd frontend && npm test

migrate:
	cd backend && python manage.py migrate

# Regenerates the OpenAPI schema and the frontend types.
api:
	cd backend && python manage.py spectacular --file openapi.yaml --validate --fail-on-warn
	cd frontend && npm run api:types

# Hash-pinned versions for the .deb (yt-dlp goes apart, unpinned).
lock:
	cd backend && uv pip compile requirements.txt --universal --python-version 3.12 --generate-hashes --no-emit-package yt-dlp -o requirements.lock --quiet
