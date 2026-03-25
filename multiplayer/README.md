# Endless Sky multiplayer hosting bootstrap

This folder adds an **optional** standalone service you can host so multiple players can create accounts and log in at the same time.

It intentionally does **not** change single-player behavior in Endless Sky itself.

## What this provides now

- Account registration (`POST /register`)
- Login with bearer token session (`POST /login`)
- Session validation (`GET /whoami`)
- Health check (`GET /healthz`)

## Run locally

```bash
python3 multiplayer/server.py
```

Server listens on `0.0.0.0:8080` by default.

## Run with Docker

```bash
docker compose -f multiplayer/docker-compose.yml up --build -d
```

## Quick API test

```bash
curl -s http://127.0.0.1:8080/healthz
curl -s -X POST http://127.0.0.1:8080/register \
  -H 'content-type: application/json' \
  -d '{"username":"pilot1","password":"supersecret123"}'
curl -s -X POST http://127.0.0.1:8080/login \
  -H 'content-type: application/json' \
  -d '{"username":"pilot1","password":"supersecret123"}'
```

## Environment variables

- `ES_MMO_HOST` (default `0.0.0.0`)
- `ES_MMO_PORT` (default `8080`)
- `ES_MMO_DB` (default `multiplayer.db`)
- `ES_MMO_SECRET` (recommended in production)
- `ES_MMO_TOKEN_TTL` in seconds (default `604800`)

## Next step to make in-game shared universe

Hook Endless Sky client state to this service (or a future authoritative simulation server) so pilots share position, combat, trading, and mission state.
