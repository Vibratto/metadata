#!/usr/bin/env bash
# Checks that a running installation serves the API and the web interface.
# Usage: packaging/smoke-test.sh <base url>
set -euo pipefail

base="${1:?usage: smoke-test.sh <base url>}"

for _ in $(seq 30); do
  if curl -fsS "$base/api/health/" >/dev/null 2>&1; then break; fi
  sleep 2
done

curl -fsS "$base/api/health/" | grep -q '"status":"ok"'
# The interface, and a deep link that the frontend's router resolves.
curl -fsS "$base/" | grep -q '<div id="app">'
curl -fsS "$base/library" | grep -q '<div id="app">'
# A fresh installation is waiting for its account, protected by the setup code.
curl -fsS -H 'X-Vibratto-Client: web' "$base/api/v1/accounts/setup/" | grep -q '"needed":true'
curl -fsS -H 'X-Vibratto-Client: web' "$base/api/v1/accounts/setup/" | grep -q '"code_required":true'
echo "ok: $base"
