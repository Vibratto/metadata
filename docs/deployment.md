# Deployment guide

[Español](deployment.es.md)

Vibratto Metadata is a single process that serves the web interface and the API on one port
and keeps everything in one data folder. There is no separate database or web server to run.

## What you need

- A machine that stays on, with internet access. A Raspberry Pi 4 is enough.
- **Docker**, on any system (images for amd64 and arm64), **or** Debian 13 / Ubuntu 24.04 or
  later for the `.deb` (it needs Python 3.12 or later).
- Disk space for your music.

## Docker

```sh
mkdir vibratto && cd vibratto
curl -O https://raw.githubusercontent.com/Vibratto/metadata/main/docker-compose.yml
docker compose up -d
docker compose logs | grep "Setup code"
```

Open `http://<your-server>:8000` and create your account with the setup code.

| What | Where |
| --- | --- |
| Database, secret key and setup code | the `data` volume (`/data` in the container) |
| Music | `./music`, next to `docker-compose.yml` |
| Settings | the `environment:` section of `docker-compose.yml` |

To keep the music somewhere else, change the left side of the `./music:/data/music` line,
for example `/srv/music:/data/music`.

**Update:** `docker compose pull && docker compose up -d`. The database is migrated on start.

**Uninstall:** `docker compose down`. Add `-v` to delete the database as well. Your music
folder is never deleted.

## Debian and Ubuntu (.deb)

Download the `.deb` from the [latest release](https://github.com/Vibratto/metadata/releases/latest):

```sh
sudo apt install ./vibratto-metadata_*_all.deb
```

The installer creates a `vibratto-metadata` system user, installs the Python dependencies in
their own environment, prepares the database, starts the service and prints the setup code.
To see the code again:

```sh
sudo grep VIBRATTO_SETUP_CODE /etc/vibratto-metadata/vibratto-metadata.env
```

| What | Where |
| --- | --- |
| Program | `/opt/vibratto-metadata` |
| Database and music | `/var/lib/vibratto-metadata` (music in `music/`) |
| Settings | `/etc/vibratto-metadata/vibratto-metadata.env` |
| Service | `systemctl status vibratto-metadata` |
| Logs | `journalctl -u vibratto-metadata` |

To keep the music somewhere else, set an absolute **Download folder** in Settings and make
it writable by the service: `sudo chown vibratto-metadata: /srv/music`.

**Update:** install the newer `.deb` the same way. Your settings and data are kept.

**Uninstall:**

```sh
sudo apt remove vibratto-metadata   # keeps the database, the music and the settings
sudo apt purge vibratto-metadata    # deletes them too, and the system user
```

## Settings

Environment variables: in `docker-compose.yml` with Docker, in
`/etc/vibratto-metadata/vibratto-metadata.env` with the `.deb` (then
`sudo systemctl restart vibratto-metadata`).

| Variable | Meaning |
| --- | --- |
| `DJANGO_ALLOWED_HOSTS` | Names and addresses the app answers to, comma-separated. The `.deb` fills in the machine's name and IPs; add your domain. Docker accepts any by default. |
| `DJANGO_ALLOW_INSECURE_HTTP=1` | Allow plain HTTP. On by default in both packages; remove it once you serve HTTPS. |
| `DJANGO_TRUST_PROXY_SSL_HEADER=1` | Trust `X-Forwarded-Proto` from your reverse proxy. |
| `DJANGO_AXES_TRUST_FORWARDED_FOR=1` | Use the address your reverse proxy reports for the sign-in lockout. |
| `DJANGO_SESSION_IDLE_SECONDS` | Seconds of inactivity before the session expires (default 1800). |
| `VIBRATTO_BIND` | (`.deb` only) Address and port, default `0.0.0.0:8000`. With Docker change the `ports:` line. |
| `VIBRATTO_SETUP_CODE` | Code asked to create the account. Generated on install. |
| `DJANGO_SECRET_KEY` | Signs the sessions. Generated on install; keep it secret. |

Everything else (download format and folder, naming template, proxies, lyrics, the threshold
for suggesting related artists) is changed from the web interface.

## HTTPS behind a reverse proxy

Sign-in is protected against guessing (five failed attempts lock the address out for
15 minutes), but passwords travel in clear text over plain HTTP. If the app is reachable
from outside your home network, put it behind a reverse proxy with HTTPS:

1. Remove `DJANGO_ALLOW_INSECURE_HTTP`.
2. Set `DJANGO_TRUST_PROXY_SSL_HEADER=1` and `DJANGO_AXES_TRUST_FORWARDED_FOR=1`.
3. Add your domain to `DJANGO_ALLOWED_HOSTS`.
4. With the `.deb`, set `VIBRATTO_BIND=127.0.0.1:8000` so only the proxy reaches it.

Caddy, for example, needs only this:

```
music.example.com {
    reverse_proxy 127.0.0.1:8000
}
```

## Backups

- **Library backup** (More → Utilities → Library backup) saves artists, albums, tracks and
  downloads to a JSON file that can be imported into this or another installation.
- For a full copy, stop the app and copy the data folder (`/var/lib/vibratto-metadata`, or
  the `data` volume) and your music folder.

## Troubleshooting

- **"Bad Request (400)"**: the name or address you are using is missing from
  `DJANGO_ALLOWED_HOSTS`.
- **Sign-in sends you back to the sign-in page over HTTP**: `DJANGO_ALLOW_INSECURE_HTTP=1`
  is missing, or you removed it without serving HTTPS.
- **Downloads fail**: update the package or image; YouTube changes often and the downloader
  is refreshed on every install. If your address is being rate-limited, add proxies under
  More → Proxies.
- **Lost password**: with the `.deb`,
  `sudo -u vibratto-metadata sh -c 'set -a; . /etc/vibratto-metadata/vibratto-metadata.env; cd /opt/vibratto-metadata/backend; ../venv/bin/python manage.py changepassword <user>'`.
  With Docker, `docker compose exec -u vibratto vibratto-metadata sh -c '. /data/secrets.env; export DJANGO_SECRET_KEY; python manage.py changepassword <user>'`.
