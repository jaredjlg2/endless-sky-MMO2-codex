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


## Deploy on Render

### Option A: Blueprint (recommended)

1. Push this repo to GitHub.
2. In Render, choose **New +** → **Blueprint**.
3. Select your repo and point Render to `multiplayer/render.yaml`.
4. Deploy. Render will create:
   - a web service named `endless-sky-mmo-server`
   - a persistent disk mounted at `/var/data` for SQLite

### Option B: Manual Web Service

1. In Render, choose **New +** → **Web Service** and select your repo.
2. Set **Root Directory** to `multiplayer`.
3. Set **Runtime** to Python.
4. Set **Build Command** to `echo "No build step required"`.
5. Set **Start Command** to `python server.py`.
6. Set **Health Check Path** to `/healthz`.
7. Add a **Persistent Disk** mounted at `/var/data` and set env var `ES_MMO_DB=/var/data/multiplayer.db`.
8. Add env vars:
   - `ES_MMO_HOST=0.0.0.0`
   - `ES_MMO_TOKEN_TTL=604800`
   - `ES_MMO_SECRET=<long random string>`

> Render injects a `PORT` environment variable automatically; `server.py` now honors it.

## Next step to make in-game shared universe

Hook Endless Sky client state to this service (or a future authoritative simulation server) so pilots share position, combat, trading, and mission state.
