#!/bin/sh
set -eu

client="$(basename "$0")"
case "$client" in
  pg_dump|pg_restore) ;;
  *)
    echo "Invoke this helper through a pg_dump or pg_restore symlink." >&2
    exit 2
    ;;
esac

# GitHub's runner client may lag behind the PostgreSQL service.  Run the
# matching reviewed client image while preserving libpq environment secrets
# outside process arguments and sharing only pytest's temporary directory.
exec docker run --rm --network host \
  --volume /tmp:/tmp \
  --env PGHOST \
  --env PGPORT \
  --env PGUSER \
  --env PGPASSWORD \
  --env PGDATABASE \
  --env PGSSLMODE \
  --env PGSSLROOTCERT \
  --env PGSSLCERT \
  --env PGSSLKEY \
  postgres:17.6-alpine3.22 \
  "$client" "$@"
