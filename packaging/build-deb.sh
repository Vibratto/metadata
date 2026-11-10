#!/usr/bin/env bash
# Builds dist/vibratto-metadata_<version>_all.deb from the current tree.
# Requires: a built frontend/dist, dpkg-deb and gettext.
# Usage: packaging/build-deb.sh <version>
set -euo pipefail

version="${1:?usage: build-deb.sh <version>}"
name=vibratto-metadata
root="$(cd "$(dirname "$0")/.." && pwd)"
pkg="$root/dist/pkg"
app="$pkg/opt/$name"

[ -f "$root/frontend/dist/index.html" ] || { echo "frontend/dist is missing; run npm run build" >&2; exit 1; }

rm -rf "$pkg" && mkdir -p "$app" "$pkg/DEBIAN" "$pkg/lib/systemd/system" "$pkg/etc/$name"

# Compile the translations before copying.
for po in "$root"/backend/locale/*/LC_MESSAGES/*.po; do msgfmt -o "${po%.po}.mo" "$po"; done

# Backend without tests or local artifacts.
tar -C "$root/backend" -c \
  --exclude='__pycache__' --exclude='tests' --exclude='.venv' --exclude='staticfiles' \
  --exclude='*.sqlite3*' --exclude='.mypy_cache' --exclude='.pytest_cache' --exclude='.ruff_cache' \
  --exclude='requirements-dev.txt' --exclude='music' . | { mkdir "$app/backend" && tar -C "$app/backend" -x; }
cp -r "$root/frontend/dist" "$app/frontend-dist"

install -m 644 "$root/packaging/$name.service" "$pkg/lib/systemd/system/$name.service"
install -m 644 "$root/packaging/$name.env" "$pkg/etc/$name/$name.env"
for script in postinst prerm postrm; do install -m 755 "$root/packaging/$script" "$pkg/DEBIAN/$script"; done
echo "/etc/$name/$name.env" > "$pkg/DEBIAN/conffiles"

cat > "$pkg/DEBIAN/control" <<CTL
Package: $name
Version: $version
Architecture: all
Maintainer: Vibratto <hello.vibratto@pm.me>
Depends: python3 (>= 3.12), python3-venv, ffmpeg, adduser
Section: web
Priority: optional
Homepage: https://github.com/Vibratto/metadata
Description: Self-hosted music library built from YouTube Music
 Give it an artist and it brings in their albums, songs, covers and lyrics,
 downloads the audio and keeps the files tagged and organised.
 .
 Django backend and built web interface, served by a systemd service
 (gunicorn) on a single port. Python dependencies are installed into
 /opt/vibratto-metadata/venv on install.
CTL

# No "~" in the file name: GitHub rewrites special characters in release assets.
dpkg-deb --root-owner-group --build "$pkg" "$root/dist/${name}_${version//\~/-}_all.deb"
