# Vibratto Metadata

[Español](README.es.md)

A self-hosted web app that builds and looks after your music library. Give it a YouTube Music
artist and it brings in the whole discography, downloads the audio and keeps every file tagged
and organised, ready for a player such as Navidrome or Jellyfin.

> Meant for personal use with content you have the rights to.

## What it does

- **Import an artist** by name or YouTube Music link: albums, singles, EPs, tracks, credits,
  artist picture and cover art.
- **Related artists** are saved as profiles in their own tab. The big ones (by monthly
  listeners; the threshold is a setting) come with a suggestion to import their discography.
- **Download** the audio as opus (the default), mp3, m4a or flac, tagged, with ReplayGain and a naming
  template you choose.
- **Lyrics**, synced when available, from LRCLIB and YouTube Music.
- **New releases**: watch artists and bring in what they publish, optionally downloading it.
- **Your existing music**: import a folder you already have, or upload the audio of a track.
- **Housekeeping**: block list, library backup, change history, maintenance utilities and
  an activity log.
- **Proxies**: every outgoing connection can go through a rotating list of proxies.
- English and Spanish interface, light and dark theme, usable from a phone.

## Install

### Docker

```sh
curl -O https://raw.githubusercontent.com/Vibratto/metadata/main/docker-compose.yml
docker compose up -d
docker compose logs | grep "Setup code"
```

Open <http://localhost:8000> and create your account with the setup code. Music is
downloaded to the `music` folder next to the compose file.

To uninstall: `docker compose down` (add `-v` to delete the database too).

### Debian and Ubuntu (.deb)

Download the package from the [latest release](https://github.com/Vibratto/metadata/releases/latest), then:

```sh
sudo apt install ./vibratto-metadata_*_all.deb
```

The installer prints the port and the setup code. Open `http://<your-server>:8000` and
create your account.

To uninstall: `sudo apt remove vibratto-metadata` keeps your database, music and settings;
`sudo apt purge vibratto-metadata` deletes them as well.

The [deployment guide](docs/deployment.md) covers settings, HTTPS behind a reverse proxy,
updates and backups.

## Development

```sh
python -m venv .venv && . .venv/bin/activate
pip install -r backend/requirements-dev.txt
npm --prefix frontend install
make migrate
make dev        # backend on :8000, frontend on :5173
make lint test
```

Backend: Django and Django REST Framework over SQLite. Frontend: Vue 3 with TypeScript.
See [CONTRIBUTING.md](CONTRIBUTING.md).

## Licence

[AGPL-3.0](LICENSE)
