#!/bin/sh
set -eu

cd "$(dirname "$0")/.."

docker compose ps
docker compose exec -T database sh -c 'pg_isready -U "$POSTGRES_USER" -d "$POSTGRES_DB"'
docker compose exec -T n8n n8n --version
docker compose exec -T n8n node -e "fetch('http://127.0.0.1:5678/healthz').then(async r => { console.log(await r.text()); process.exit(r.ok ? 0 : 1); }).catch(e => { console.error(e.message); process.exit(1); })"
docker compose exec -T line-signature-gateway python -c "import urllib.request; print(urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=5).read().decode())"

echo "Local container verification passed."
echo "Next, verify the public endpoint: curl -fsS https://YOUR_DOMAIN/healthz"
