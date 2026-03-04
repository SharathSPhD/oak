#!/bin/bash
# OAK All-in-One Entrypoint
# Initializes DB, seeds skills, starts supervisord
set -e

echo "[oak-aio] Initializing PostgreSQL..."
if [ ! -f /var/lib/postgresql/16/main/PG_VERSION ]; then
    su postgres -c "/usr/lib/postgresql/16/bin/initdb -D /var/lib/postgresql/16/main"
fi

# Start postgres temporarily for init
su postgres -c "/usr/lib/postgresql/16/bin/pg_ctl -D /var/lib/postgresql/16/main -l /tmp/pg_init.log start"
sleep 3

# Create user and database
su postgres -c "psql -c \"CREATE USER oak WITH PASSWORD 'oak' SUPERUSER;\"" 2>/dev/null || true
su postgres -c "psql -c \"CREATE DATABASE oak OWNER oak;\"" 2>/dev/null || true

# Apply schema
su postgres -c "psql -U oak -d oak -f /opt/oak/api/db/schema.sql" 2>/dev/null || true

# Seed skills
su postgres -c "psql -U oak -d oak -f /opt/oak/scripts/seed_skills.sql" 2>/dev/null || true

# Stop temp postgres (supervisord will manage it)
su postgres -c "/usr/lib/postgresql/16/bin/pg_ctl -D /var/lib/postgresql/16/main stop"
sleep 2

echo "[oak-aio] Starting OAK services via supervisord..."
exec /usr/bin/supervisord -c /etc/supervisor/conf.d/oak.conf
