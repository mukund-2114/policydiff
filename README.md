# Policy Diff

Finds places where a company's policies contradict each other. Self-hosted: documents, vectors and findings stay in your own Postgres. Model calls use your own API key.

Status: Phase 1 (foundation). Login, health check and database are in place. Upload and scanning come in later phases.

## Run it

Requires Docker with Compose.

```bash
cp .env.example .env        # then edit: set passwords, SECRET_KEY, and one provider key
cd deploy
docker compose --env-file ../.env up -d --build
```

Open http://127.0.0.1:8080 and sign in with `ADMIN_EMAIL` and `ADMIN_PASSWORD` from `.env`.

Check status: http://127.0.0.1:8080/api/health (add `?deep=true` to make one small call to your model provider).

## Choose a model provider

Edit `models.yaml`, and put the matching key in `.env`:

| Provider | Key variable | Used for |
| --- | --- | --- |
| `openai` | `OPENAI_API_KEY` | chat, embeddings |
| `anthropic` | `ANTHROPIC_API_KEY` | chat |
| `ollama` | none | chat, embeddings, fully offline (set `egress.allow_cloud: false`) |

If you change the embedding model, set `embed.dims` and `EMBED_DIMS` to match, and re-embed your documents.

## Layout

```
api/      FastAPI app, database models, Alembic migrations, model adapters
web/      React front end (served by Caddy, which also proxies /api)
worker/   Background jobs (Phase 2)
evals/    Test corpus and accuracy measurements (Phase 1 to 4)
deploy/   docker-compose.yml
```

## Develop

Run the database in Docker, and the api and web app on your machine with hot reload.

```bash
# 1. Database (from policydiff/deploy). Publish its port for local use or run the full stack instead.
docker compose --env-file ../.env up -d db

# 2. API (needs Python 3.13 and uv), http://127.0.0.1:8000
cd api
uv sync
uv run alembic upgrade head
uv run uvicorn app.main:app --reload

# 3. Web (needs Node 22), http://127.0.0.1:5173, /api is proxied to port 8000
cd web
npm install
npm run dev

# Tests
cd api && uv run pytest
```

The web app is built with npm. `npm run build` type-checks and produces the static files that the Docker image serves with Caddy.

## License

MIT, see `LICENSE`.
