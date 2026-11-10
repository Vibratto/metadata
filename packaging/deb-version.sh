#!/usr/bin/env bash
# Debian version from a tag: v1.2.0 -> 1.2.0, v1.2.0-rc.1 -> 1.2.0~rc.1 ("~" sorts before the final one).
# Usage: packaging/deb-version.sh <tag>
set -euo pipefail

[[ "${1:-}" =~ ^v([0-9]+\.[0-9]+\.[0-9]+)(-([0-9A-Za-z.]+))?$ ]] || { echo "invalid tag: ${1:-}" >&2; exit 1; }
echo "${BASH_REMATCH[1]}${BASH_REMATCH[3]:+~${BASH_REMATCH[3]}}"
