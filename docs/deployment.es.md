# Guía de despliegue

[English](deployment.md)

Vibratto Metadata es un único proceso que sirve la interfaz web y la API en un solo puerto y
lo guarda todo en una carpeta de datos. No hay que montar aparte una base de datos ni un
servidor web.

## Qué necesitas

- Una máquina que esté siempre encendida, con acceso a internet. Basta una Raspberry Pi 4.
- **Docker**, en cualquier sistema (imágenes para amd64 y arm64), **o** Debian 13 / Ubuntu
  24.04 o posterior para el `.deb` (necesita Python 3.12 o posterior).
- Espacio en disco para tu música.

## Docker

```sh
mkdir vibratto && cd vibratto
curl -O https://raw.githubusercontent.com/Vibratto/metadata/main/docker-compose.yml
docker compose up -d
docker compose logs | grep "Setup code"
```

Abre `http://<tu-servidor>:8000` y crea tu cuenta con el código de configuración.

| Qué | Dónde |
| --- | --- |
| Base de datos, clave secreta y código de configuración | el volumen `data` (`/data` en el contenedor) |
| Música | `./music`, junto a `docker-compose.yml` |
| Ajustes | la sección `environment:` de `docker-compose.yml` |

Para guardar la música en otro sitio, cambia la parte izquierda de la línea
`./music:/data/music`; por ejemplo, `/srv/music:/data/music`.

**Actualizar:** `docker compose pull && docker compose up -d`. La base de datos se migra al
arrancar.

**Desinstalar:** `docker compose down`. Añade `-v` para borrar también la base de datos. Tu
carpeta de música no se borra nunca.

## Debian y Ubuntu (.deb)

Descarga el `.deb` de la [última versión](https://github.com/Vibratto/metadata/releases/latest):

```sh
sudo apt install ./vibratto-metadata_*_all.deb
```

El instalador crea un usuario de sistema `vibratto-metadata`, instala las dependencias de
Python en su propio entorno, prepara la base de datos, arranca el servicio y muestra el
código de configuración. Para volver a verlo:

```sh
sudo grep VIBRATTO_SETUP_CODE /etc/vibratto-metadata/vibratto-metadata.env
```

| Qué | Dónde |
| --- | --- |
| Programa | `/opt/vibratto-metadata` |
| Base de datos y música | `/var/lib/vibratto-metadata` (la música, en `music/`) |
| Ajustes | `/etc/vibratto-metadata/vibratto-metadata.env` |
| Servicio | `systemctl status vibratto-metadata` |
| Registros | `journalctl -u vibratto-metadata` |

Para guardar la música en otro sitio, pon una **carpeta de descarga** absoluta en Ajustes y
dale permiso de escritura al servicio: `sudo chown vibratto-metadata: /srv/music`.

**Actualizar:** instala el `.deb` nuevo de la misma forma. Se conservan los ajustes y los datos.

**Desinstalar:**

```sh
sudo apt remove vibratto-metadata   # conserva la base de datos, la música y los ajustes
sudo apt purge vibratto-metadata    # los borra también, junto con el usuario de sistema
```

## Ajustes

Variables de entorno: en `docker-compose.yml` con Docker, y en
`/etc/vibratto-metadata/vibratto-metadata.env` con el `.deb` (después,
`sudo systemctl restart vibratto-metadata`).

| Variable | Significado |
| --- | --- |
| `DJANGO_ALLOWED_HOSTS` | Nombres y direcciones a los que responde la aplicación, separados por comas. El `.deb` añade el nombre y las IP de la máquina; añade tu dominio. Docker acepta cualquiera por defecto. |
| `DJANGO_ALLOW_INSECURE_HTTP=1` | Permite HTTP sin cifrar. Activado por defecto en los dos paquetes; quítalo cuando sirvas HTTPS. |
| `DJANGO_TRUST_PROXY_SSL_HEADER=1` | Confía en la cabecera `X-Forwarded-Proto` de tu proxy inverso. |
| `DJANGO_AXES_TRUST_FORWARDED_FOR=1` | Usa la dirección que indica tu proxy inverso para el bloqueo de inicios de sesión. |
| `DJANGO_SESSION_IDLE_SECONDS` | Segundos de inactividad hasta que caduca la sesión (1800 por defecto). |
| `VIBRATTO_BIND` | (solo `.deb`) Dirección y puerto; por defecto `0.0.0.0:8000`. Con Docker, cambia la línea `ports:`. |
| `VIBRATTO_SETUP_CODE` | Código que se pide para crear la cuenta. Se genera al instalar. |
| `DJANGO_SECRET_KEY` | Firma las sesiones. Se genera al instalar; mantenla en secreto. |

Todo lo demás (formato y carpeta de descarga, plantilla de nombres, proxies, letras, umbral
para sugerir artistas relacionados) se cambia desde la interfaz web.

## HTTPS detrás de un proxy inverso

El inicio de sesión está protegido contra intentos repetidos (cinco fallos bloquean la
dirección durante 15 minutos), pero por HTTP las contraseñas viajan sin cifrar. Si la
aplicación es accesible desde fuera de tu red local, ponla detrás de un proxy inverso con
HTTPS:

1. Quita `DJANGO_ALLOW_INSECURE_HTTP`.
2. Activa `DJANGO_TRUST_PROXY_SSL_HEADER=1` y `DJANGO_AXES_TRUST_FORWARDED_FOR=1`.
3. Añade tu dominio a `DJANGO_ALLOWED_HOSTS`.
4. Con el `.deb`, pon `VIBRATTO_BIND=127.0.0.1:8000` para que solo llegue el proxy.

Con Caddy, por ejemplo, basta con esto:

```
music.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

## Copias de seguridad

- **Copia de la biblioteca** (Más → Utilidades → Copia de la biblioteca): guarda artistas,
  álbumes, canciones y descargas en un fichero JSON que se puede importar en esta u otra
  instalación.
- Para una copia completa, para la aplicación y copia la carpeta de datos
  (`/var/lib/vibratto-metadata`, o el volumen `data`) y tu carpeta de música.

## Problemas frecuentes

- **«Bad Request (400)»**: el nombre o la dirección que usas no está en
  `DJANGO_ALLOWED_HOSTS`.
- **Al entrar por HTTP vuelves a la pantalla de inicio de sesión**: falta
  `DJANGO_ALLOW_INSECURE_HTTP=1`, o lo quitaste sin servir HTTPS.
- **Fallan las descargas**: actualiza el paquete o la imagen; YouTube cambia a menudo y el
  descargador se renueva en cada instalación. Si tu dirección está limitada, añade proxies en
  Más → Proxies.
- **Contraseña olvidada**: con el `.deb`,
  `sudo -u vibratto-metadata sh -c 'set -a; . /etc/vibratto-metadata/vibratto-metadata.env; cd /opt/vibratto-metadata/backend; ../venv/bin/python manage.py changepassword <usuario>'`.
  Con Docker, `docker compose exec -u vibratto vibratto-metadata sh -c '. /data/secrets.env; export DJANGO_SECRET_KEY; python manage.py changepassword <usuario>'`.
