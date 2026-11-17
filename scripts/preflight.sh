#!/bin/sh
set -eu

cd "$(dirname "$0")/.."

required_files="env/n8n.env env/postgres.env env/pgadmin.env env/proxy.env env/line-gateway.env config/caddy/Caddyfile config/postgres/01-create-chat-app.sh compose.yaml services/line-signature-gateway/app.py services/line-signature-gateway/Dockerfile migration/n8n-data.tar.gz migration/postgres.dump migration/SHA256SUMS"
for file in $required_files; do
  if [ ! -f "$file" ]; then
    echo "Missing required file: $file" >&2
    exit 1
  fi
done

if grep -E 'REPLACE_WITH|automation\.example\.com|admin@example\.com' \
  env/n8n.env env/postgres.env env/pgadmin.env env/proxy.env >/dev/null; then
  echo "Replace all example domains, emails, and passwords before deployment." >&2
  exit 1
fi

if grep -E 'REPLACE_WITH' env/line-gateway.env >/dev/null; then
  echo "Replace the example LINE channel secret before deployment." >&2
  exit 1
fi

for file in env/n8n.env env/postgres.env env/pgadmin.env env/proxy.env env/line-gateway.env; do
  chmod 600 "$file"
done

if command -v sha256sum >/dev/null 2>&1; then
  (cd migration && sha256sum -c SHA256SUMS)
else
  (cd migration && shasum -a 256 -c SHA256SUMS)
fi
docker compose config --quiet
echo "Preflight checks passed."
