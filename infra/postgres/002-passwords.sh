#!/bin/sh
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v reader_pass="$READER_PASSWORD" -v audit_pass="$AUDIT_PASSWORD" <<'SQL'
ALTER ROLE analyst_reader PASSWORD :'reader_pass';
ALTER ROLE analyst_audit PASSWORD :'audit_pass';
SQL
