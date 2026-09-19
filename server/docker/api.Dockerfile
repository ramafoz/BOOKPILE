FROM python:3.13.7-slim-bookworm AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY server/pyproject.toml ./
COPY server/src ./src
RUN python -m pip wheel --wheel-dir /wheels .

FROM python:3.13.7-slim-bookworm AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/bookpile/bin:$PATH

RUN groupadd --system --gid 10001 bookpile \
    && useradd --system --uid 10001 --gid bookpile --home-dir /nonexistent --shell /usr/sbin/nologin bookpile \
    && mkdir -p /opt/bookpile /var/lib/bookpile/private-objects /var/lib/bookpile/import-staging /var/lib/bookpile/export-staging \
    && chown -R bookpile:bookpile /opt/bookpile /var/lib/bookpile

COPY --from=builder /wheels /wheels
RUN python -m venv /opt/bookpile \
    && /opt/bookpile/bin/pip install --no-cache-dir /wheels/* \
    && rm -rf /wheels

WORKDIR /app
COPY --chown=bookpile:bookpile server/alembic.ini ./alembic.ini
COPY --chown=bookpile:bookpile server/migrations ./migrations

USER 10001:10001
EXPOSE 8100
CMD ["uvicorn", "bookpile_server.main:app", "--host", "0.0.0.0", "--port", "8100", "--workers", "2", "--no-access-log"]

