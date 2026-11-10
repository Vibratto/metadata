# Vibratto Metadata

[English](README.md)

Aplicación web autoalojada que crea y cuida tu biblioteca musical. Dale un artista de YouTube
Music y trae toda su discografía, descarga el audio y mantiene cada fichero etiquetado y
ordenado, listo para un reproductor como Navidrome o Jellyfin.

> Pensada para uso personal con contenido sobre el que tengas derechos.

## Qué hace

- **Importa un artista** por nombre o por enlace de YouTube Music: álbumes, sencillos, EP,
  canciones, créditos, imagen del artista y portadas.
- **Los artistas relacionados** se guardan como perfiles en su propia pestaña. A los grandes
  (por oyentes mensuales; el umbral es un ajuste) se les sugiere importar la discografía.
- **Descarga** el audio en mp3, m4a, opus o flac, etiquetado, con ReplayGain y con la
  plantilla de nombres que elijas.
- **Letras**, sincronizadas cuando las hay, de LRCLIB y YouTube Music.
- **Novedades**: vigila artistas y trae lo que publiquen, con descarga automática opcional.
- **Tu música de antes**: importa una carpeta que ya tengas o sube el audio de una canción.
- **Mantenimiento**: lista de bloqueados, copia de la biblioteca, historial de cambios,
  utilidades y registro de actividad.
- **Proxies**: todas las conexiones salientes pueden ir por una lista rotatoria de proxies.
- Interfaz en inglés y español, tema claro y oscuro, usable desde el móvil.

## Instalación

### Docker

```sh
curl -O https://raw.githubusercontent.com/Vibratto/metadata/main/docker-compose.yml
docker compose up -d
docker compose logs | grep "Setup code"
```

Abre <http://localhost:8000> y crea tu cuenta con el código de configuración. La música se
descarga en la carpeta `music`, junto al fichero compose.

Para desinstalar: `docker compose down` (añade `-v` para borrar también la base de datos).

### Debian y Ubuntu (.deb)

Descarga el paquete de la [última versión](https://github.com/Vibratto/metadata/releases/latest) y después:

```sh
sudo apt install ./vibratto-metadata_*_all.deb
```

El instalador muestra el puerto y el código de configuración. Abre `http://<tu-servidor>:8000`
y crea tu cuenta.

Para desinstalar: `sudo apt remove vibratto-metadata` conserva la base de datos, la música y
los ajustes; `sudo apt purge vibratto-metadata` los borra también.

La [guía de despliegue](docs/deployment.es.md) explica los ajustes, HTTPS detrás de un proxy
inverso, las actualizaciones y las copias de seguridad.

## Desarrollo

```sh
python -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements-dev.txt
npm --prefix frontend install
make migrate
make dev        # backend en :8000, frontend en :5173
make lint test
```

Backend: Django y Django REST Framework sobre SQLite. Frontend: Vue 3 con TypeScript.
Consulta [CONTRIBUTING.md](CONTRIBUTING.md).

## Licencia

[AGPL-3.0](LICENSE)
