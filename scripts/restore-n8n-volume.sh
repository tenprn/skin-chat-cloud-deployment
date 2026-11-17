#!/bin/sh
set -eu

if [ "$#" -gt 1 ]; then
  echo "Usage: $0 [absolute/path/to/migration-directory]" >&2
  exit 1
fi

project_dir=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
migration_dir=${1:-"$project_dir/migration"}
archive="$migration_dir/n8n-data.tar.gz"
volume="skin-chat-n8n-data"

if [ ! -f "$archive" ]; then
  echo "Backup archive not found: $archive" >&2
  exit 1
fi

docker volume inspect "$volume" >/dev/null 2>&1 || docker volume create "$volume" >/dev/null

docker run --rm \
  -v "$volume:/target" \
  -v "$migration_dir:/migration:ro" \
  alpine:3.20 \
  sh -c 'test -z "$(ls -A /target)" || { echo "Target volume is not empty" >&2; exit 1; }; tar -xzf /migration/n8n-data.tar.gz -C /target'

echo "Restored n8n state into $volume."
