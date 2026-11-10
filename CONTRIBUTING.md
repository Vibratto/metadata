# Contributing

[Español](#español)

- Short branches off `main`: `feat/…`, `fix/…`, `docs/…`, `chore/…`.
- Small pull requests, squash-merged.
- Before opening one: `make lint test` must pass. If you change the API, run `make api` to
  regenerate `backend/openapi.yaml` and the frontend types.
- Code, comments, tests and commit messages are written in English. Every text a user reads
  (interface, API messages, README and guides) exists in English and Spanish:
  `frontend/src/locales/{en,es}` and `backend/locale/es`.

## Environment

```sh
python -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements-dev.txt
npm --prefix frontend install
pre-commit install
make migrate
make dev
```

## Cutting a release

A release is published with a tag. CI runs every check, builds the `.deb`, attaches it to a
GitHub Release and pushes the Docker image to `ghcr.io/vibratto/metadata`:

```sh
git checkout main && git pull
git tag v1.2.3 && git push origin v1.2.3
```

A tag with a suffix (`v1.2.3-rc.1`) is published as a pre-release.

## Español

- Ramas cortas desde `main`: `feat/…`, `fix/…`, `docs/…`, `chore/…`.
- Pull requests pequeños, fusionados con squash.
- Antes de abrir uno: `make lint test` en verde. Si cambias la API, ejecuta `make api` para
  regenerar `backend/openapi.yaml` y los tipos del frontend.
- El código, los comentarios, los tests y los mensajes de commit se escriben en inglés. Todo
  texto que lee un usuario (interfaz, mensajes de la API, README y guías) existe en inglés y
  en español: `frontend/src/locales/{en,es}` y `backend/locale/es`.

El entorno y la publicación de versiones se preparan con las órdenes de las secciones
[Environment](#environment) y [Cutting a release](#cutting-a-release).
