FROM node:22.15.0-alpine3.21 AS builder

WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend ./
RUN npm run build:server

FROM caddy:2.10.2-alpine AS runtime

RUN addgroup -S -g 10001 bookpile \
    && adduser -S -D -H -u 10001 -G bookpile bookpile \
    && chown -R bookpile:bookpile /config /data
COPY server/docker/Caddyfile /etc/caddy/Caddyfile
COPY --from=builder --chown=bookpile:bookpile /build/dist/server /srv

USER bookpile
EXPOSE 8080 8443
CMD ["caddy", "run", "--config", "/etc/caddy/Caddyfile", "--adapter", "caddyfile"]
