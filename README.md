# Policy Diff

Finds places where a company's policies contradict each other. Self-hosted: documents, vectors and findings stay in your own Postgres. Model calls use your own API key, and the app makes no other outbound calls.

Upload PDFs. The app cuts them into numbered clauses, finds clauses in other documents that cover the same rule, asks a model whether each pair contradicts, and checks that every quote the model gives is really in the text. You review the results in a queue, side by side with the PDF pages.

## Install

You need Docker with Compose, about 2 GB of free disk, and an OpenAI API key (other providers are listed below). Allow 15 minutes.

```bash
git clone https://github.com/mukund-2114/policydiff.git
cd policydiff
cp .env.example .env
```

Edit `.env` and set these four values. The rest can stay as they are.

| Variable | Set it to |
| --- | --- |
| `POSTGRES_PASSWORD` | A long random password |
| `SECRET_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(48))"` |
| `ADMIN_EMAIL`, `ADMIN_PASSWORD` | The first admin account, created on first start |
| `OPENAI_API_KEY` | Your key. You can also leave it empty and add it on the Settings page |

Then start it:

```bash
cd deploy
docker compose --env-file ../.env up -d --build
```

The first build takes a few minutes. Open http://127.0.0.1:8080 and sign in.

### Try it on the demo policies

1. Open **Sample policies** and press **Load as documents**. This adds 15 PDFs from a made-up airline, Northwind Air, which hold 25 planted conflicts.
2. Open **Documents** and wait until each one reads Ready. All 15 take about 10 minutes, because every chunk gets a short model call for its key facts.
3. Open a document and press **Scan for conflicts**. A scan of one demo document takes a few minutes and about 90,000 tokens with `gpt-5-mini`.
4. Open **Findings**. Use `j` and `k` to move, `c` to confirm, `d` to dismiss.
5. Open **Answer key** to see which conflicts were planted and check what the scan found.

## Pages

| Page | What it does |
| --- | --- |
| Documents | Upload a PDF, watch it move through the pipeline, start a scan |
| Findings | The review queue. Filter by status, type and confidence. Export CSV. Each finding shows both quotes, the PDF pages, and a "Why this pair" panel |
| Ask | A chat over the policies. Answers stream in as they are written, cite their passages, remember the conversation for follow-ups, and list related findings. An "as of" date searches the versions in effect that day |
| Search | Try the hybrid search by hand and see which pairs would go to the judge |
| Compare | Two uploaded PDFs side by side |
| Sample policies, Answer key | The demo corpus and its planted conflicts |
| Status | Database, models and keys |
| Audit log (admin) | Who did what and when. Export CSV |
| Settings (admin) | Provider keys, which model each job uses, the reranker, and a Preview that tries your choices on 20 chunks |

## Models and keys

Out of the box the app uses OpenAI for embeddings, the judge, Q&A and figure reading, and a small reranker that runs inside the container and sends nothing out. Change this on the **Settings** page. A key is tested before it is saved, stored encrypted in your database, and never shown again. A key saved on the Settings page is used instead of the one in `.env`.

| Provider | Used for | Needs |
| --- | --- | --- |
| `openai` | Embeddings, judge, Q&A, figures | `OPENAI_API_KEY` |
| `anthropic` | Judge, Q&A, figures | `ANTHROPIC_API_KEY` |
| `bedrock` | Judge, Q&A, figures | An IAM role or AWS credentials, and `AWS_REGION` |
| `openai_compatible` | Judge, Q&A, figures | A server address (vLLM, LM Studio, a gateway) |
| `ollama` | Everything, fully offline | A running Ollama server |
| Cohere rerank | Reranker only | `COHERE_API_KEY`. Chunk text is sent to Cohere |

The starting choices come from `models.yaml`. To run with no data leaving your network, set `egress.allow_cloud: false` there: the app then refuses any provider that is not on a private address.

Changing the embedding model changes the vector size, so it is set in `models.yaml` and `EMBED_DIMS`, not on the Settings page. After changing it, press **Embed again** on each document.

## Cost and time

A scan reads about 5 candidate pairs per chunk. The Settings page **Preview** runs 20 random chunks through the real pipeline and prints the tokens used and a projection for your whole library, before you commit to a full scan. On the demo corpus (261 chunks) the projection is about 1.4 million tokens. Only new or changed documents are scanned afterwards: a pair that was judged before is skipped.

## Put it on a server

The containers listen on 127.0.0.1 only. To reach the app from other machines:

1. Put a reverse proxy with HTTPS in front of port 8080 (Caddy, nginx, a cloud load balancer). The proxy must pass `/` to the web container; the web container already proxies `/api`.
2. Set `COOKIE_SECURE=true` in `.env` so the session cookie is never sent over plain HTTP, then run `docker compose --env-file ../.env up -d` again.
3. Back up two Docker volumes: `policydiff_pgdata` (the database) and `policydiff_files` (the uploaded PDFs). Or set `STORAGE_BACKEND=s3` to keep PDFs in a bucket.
4. Keep `SECRET_KEY` safe. It signs sessions and it protects the keys saved on the Settings page. If it changes, everyone is signed out and the saved keys must be entered again.

To upgrade: `git pull`, then `docker compose --env-file ../.env up -d --build`. Database migrations run on start.

Five failed sign-ins for one email address in 15 minutes block that address for 15 minutes. Every sign-in, upload, scan, decision, settings change and question is written to the audit log, without keys or document text.

## How accurate is it

Measured on the Northwind Air demo corpus, with `gpt-5-mini`:

| Measure | Result | Target |
| --- | --- | --- |
| Candidate recall (the right partner reaches the judge) | 23 of 23 text and table conflicts | 90%+ |
| Table conflicts found | 5 of 5 | 4 of 5 |
| Figure conflicts found | 2 of 2 | none set |
| Planted conflicts found, any confidence | 12 of 14 scored | 80%+ |
| Precision with every finding shown | 36% | 80%+ |
| Precision and recall at confidence 90% or more | 79% and 79% | 80%+ |

The scored set is the four documents that were scanned for this measurement (14 conflicts). Findings that the answer key does not list count as wrong, even when they are real. The review queue hides findings under 90% confidence by default; lower it to see more. Two text conflicts are not found because their partner chunk never reaches the judge. A cabin bag drawing is read with one axis named wrongly, so figure results depend on how clearly the picture is labelled.

Reproduce the numbers:

```bash
cd deploy
docker compose --env-file ../.env exec -T api python - < ../evals/candidate_recall.py
docker compose --env-file ../.env exec -T api python - < ../evals/judge_eval.py
```

## Layout

```
api/      FastAPI app, database models, Alembic migrations, model adapters, pipeline stages
web/      React front end (served by Caddy, which also proxies /api)
worker/   Reserved. The worker runs from the api image (see deploy/docker-compose.yml)
evals/    The Northwind Air corpus, its PDFs and labels, and the accuracy scripts
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

# Tests and checks
cd api && uv run pytest && uv run ruff check .
cd web && npm run build
```

## License

MIT, see `LICENSE`.
