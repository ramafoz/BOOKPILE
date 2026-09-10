FROM postgres:17.6-bookworm AS postgres-tools

FROM python:3.13.7-slim-bookworm AS builder
ENV PIP_DISABLE_PIP_VERSION_CHECK=1 PIP_NO_CACHE_DIR=1
WORKDIR /build
COPY server/pyproject.toml ./
COPY server/src ./src
RUN python -m pip wheel --wheel-dir /wheels .

FROM python:3.13.7-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PATH=/opt/bookpile/bin:$PATH
RUN apt-get update \
    && apt-get install --yes --no-install-recommends libpq5 libzstd1 liblz4-1 \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --system --gid 10001 bookpile \
    && useradd --system --uid 10001 --gid bookpile --home-dir /nonexistent --shell /usr/sbin/nologin bookpile \
    && mkdir -p /opt/bookpile /var/lib/bookpile/operational-backups \
    && chown -R bookpile:bookpile /opt/bookpile /var/lib/bookpile
COPY --from=postgres-tools /usr/lib/postgresql/17/bin/pg_dump /usr/local/bin/pg_dump
COPY --from=postgres-tools /usr/lib/postgresql/17/bin/pg_restore /usr/local/bin/pg_restore
COPY --from=builder /wheels /wheels
RUN python -m venv /opt/bookpile \
    && /opt/bookpile/bin/pip install --no-cache-dir /wheels/* \
    && rm -rf /wheels
USER 10001:10001
ENTRYPOINT ["bookpile-operational-backup"]
CMD ["--help"]
