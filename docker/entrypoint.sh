#!/usr/bin/env bash
# Bootstraps the demo data on first boot, then hands off to the container command.
#
# Only the API container should bootstrap (SQLPILOT_BOOTSTRAP=1); the UI shares
# the image but talks to the API over HTTP and never touches the database.
set -euo pipefail

if [ "${SQLPILOT_BOOTSTRAP:-0}" = "1" ]; then
  db_path="${SQLITE_DB_PATH:-data/demo.db}"
  chroma_dir="${CHROMA_PERSIST_DIR:-data/chroma}"

  if [ ! -f "$db_path" ]; then
    echo "[entrypoint] seeding demo database at $db_path"
    python scripts/seed_database.py
  else
    echo "[entrypoint] demo database already present at $db_path"
  fi

  # chroma writes chroma.sqlite3 on first index; its absence means "not indexed yet"
  if [ ! -f "$chroma_dir/chroma.sqlite3" ]; then
    echo "[entrypoint] indexing RAG collections into $chroma_dir"
    python scripts/index_rag.py
  else
    echo "[entrypoint] RAG index already present at $chroma_dir"
  fi
fi

exec "$@"
