#!/bin/bash
# docker/init-db.sh
# PostgreSQL init script — runs on first container start.
# Mounted as /docker-entrypoint-initdb.d/init-db.sh in compose.
set -e
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" < /docker-entrypoint-initdb.d/schema.sql
echo "[init-db] OAK schema applied successfully."
