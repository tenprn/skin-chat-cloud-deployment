#!/bin/sh
set -eu

project_dir=$(CDPATH= cd -- "$(dirname "$0")/.." && pwd)
cd "$project_dir"

for name in n8n postgres pgadmin proxy line-gateway; do
  source_file="env/${name}.env.example"
  target_file="env/${name}.env"
  if [ ! -f "$target_file" ]; then
    cp "$source_file" "$target_file"
    chmod 600 "$target_file"
    echo "Created $target_file from its example. Edit it before deployment."
  else
    echo "Kept existing $target_file."
  fi
done
