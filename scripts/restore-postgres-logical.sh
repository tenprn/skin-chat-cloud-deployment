#!/bin/sh
set -eu

if [ "$#" -gt 1 ]; then
  echo "Usage: $0 [absolute/path/to/migration-directory]" >&2
  exit 1
fi

cd "$(dirname "$0")/.."
project_dir=$PWD
migration_dir=${1:-"$project_dir/migration"}
dump_file="$migration_dir/postgres.dump"

if [ ! -f "$dump_file" ]; then
  echo "PostgreSQL dump not found: $dump_file" >&2
  exit 1
fi

docker compose up -d database
docker compose cp "$dump_file" database:/tmp/postgres.dump

docker compose exec -T -u postgres database sh -c '
  pg_restore \
    -U "$POSTGRES_USER" \
    -d "$APP_DB_NAME" \
    --clean \
    --if-exists \
    /tmp/postgres.dump
'

docker compose exec -T -u postgres database sh -c '
  psql -U "$POSTGRES_USER" -d "$APP_DB_NAME" -c "\\dt public.*"
'

echo "PostgreSQL logical restore completed."
