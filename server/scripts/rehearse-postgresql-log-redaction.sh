#!/bin/sh
set -eu

image="${BOOKPILE_POSTGRES_IMAGE:-postgres:17.6-alpine3.22}"
container="bookpile-postgres-redaction-$$"
sentinel="BOOKPILE_PRIVATE_SENTINEL"

cleanup() {
    docker rm -f "$container" >/dev/null 2>&1 || true
}
trap cleanup EXIT INT TERM

docker run -d --name "$container" \
    -e POSTGRES_PASSWORD=fixture-password \
    "$image" postgres \
    -c log_error_verbosity=terse \
    -c log_min_error_statement=panic \
    -c log_statement=none \
    -c log_parameter_max_length=0 \
    -c log_parameter_max_length_on_error=0 \
    >/dev/null

attempt=0
until docker exec "$container" pg_isready -U postgres >/dev/null 2>&1; do
    attempt=$((attempt + 1))
    if [ "$attempt" -ge 30 ]; then
        docker logs "$container" >&2
        exit 1
    fi
    sleep 1
done

docker exec "$container" psql -U postgres -v ON_ERROR_STOP=0 -c \
    "CREATE TABLE d3l_redaction_fixture(secret text UNIQUE);
     INSERT INTO d3l_redaction_fixture VALUES ('$sentinel');
     INSERT INTO d3l_redaction_fixture VALUES ('$sentinel');" \
    >/dev/null 2>&1 || true
sleep 1
logs="$(docker logs "$container" 2>&1)"

case "$logs" in
    *"$sentinel"*)
        echo "PostgreSQL retained the private sentinel" >&2
        exit 1
        ;;
esac
case "$logs" in
    *"duplicate key value violates unique constraint"*) ;;
    *)
        echo "expected minimized PostgreSQL error was not retained" >&2
        exit 1
        ;;
esac

printf '%s\n' \
    '{"postgres_error_retained":true,"private_value_absent":true,"statement_absent":true}'
