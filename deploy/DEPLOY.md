# Putting Policy Diff online

This page explains where the app can run, how a release gets to a server, and the steps to go live. Nothing here has been run against a real server yet; the CI jobs and compose files were checked on a laptop only.

## What Cloudflare can and cannot do

Policy Diff is four long-running containers: Postgres with pgvector, the api, a background worker, and the web server. It also loads a small reranker model into memory. Cloudflare's free hosting (Pages and Workers) runs static files and short scripts. It cannot run Postgres, a Python worker or containers, so the app itself cannot live there.

What Cloudflare is good for here, and free:

- **Cloudflare Tunnel.** A small program on your server makes an outbound connection to Cloudflare. Visitors reach `https://policies.yourdomain.com`, Cloudflare provides the certificate, and the server opens no ports. This replaces a reverse proxy and a certificate setup.
- **Cloudflare Access.** Optional sign-in in front of the whole site (email codes or Google), free for a small team. It adds a second lock before the app's own login.
- **DNS** for your domain.
- **R2** (free tier) as the PDF store. The app already supports an S3-compatible bucket: set `STORAGE_BACKEND=s3`, `S3_ENDPOINT_URL`, `S3_BUCKET`, `S3_ACCESS_KEY` and `S3_SECRET_KEY`.

So the realistic setup is a small virtual machine you run Docker on, with Cloudflare in front of it.

## Where to run the machine

The stack needs about 2 GB of memory to run and 4 GB to be comfortable while a document is being embedded. Plan for 2 vCPU, 4 GB RAM and 20 GB of disk. Check each provider's current prices; they change.

| Option | Why choose it | Watch out for |
| --- | --- | --- |
| **AWS Lightsail** (4 GB plan) | The simplest AWS route: one flat monthly price, a static IP, a built-in firewall, snapshots for backups. No extra AWS concepts. | Not free after any trial credit. |
| **AWS EC2** (for example `t3.medium`) | Same Docker steps, plus the full AWS toolbox: an IAM role for Bedrock with no keys, S3 for PDFs, snapshots, CloudWatch. Best if you will use Bedrock or already have an AWS account. | More settings to get right. Costs more than a small VPS for the same size. |
| **Oracle Cloud Always Free** (Ampere ARM) | Free forever, with a lot of memory. | Capacity is hard to get in some regions. The images are built for x86 only for now, so ARM needs a multi-platform build first (not set up or tested). |
| **A small VPS** (Hetzner, DigitalOcean) | Usually the cheapest paid option for 4 GB. | Not AWS, so no IAM role for Bedrock. |

**Recommendation.** Start on one Lightsail or EC2 machine with a Cloudflare Tunnel in front. You pay for one machine and get HTTPS, a firewall with every port closed, and optional Access sign-in. Move to RDS for the database or ECS for the containers only if you outgrow one machine; the app does not need it yet.

If you want it free, use Oracle after the ARM build is done, or run it on a spare computer at home behind the same Cloudflare Tunnel.

## How a release reaches the server

```
 you push a tag v0.1.0
        |
        v
 release.yml builds the api and web images and publishes them to GHCR (GitHub's free registry)
        |
        v
 you press "Run workflow" on deploy.yml with version 0.1.0
        |
        v
 the server pulls those images and restarts (docker-compose.prod.yml)
```

Three workflows, each with one job:

| File | Runs when | Does |
| --- | --- | --- |
| `.github/workflows/ci.yml` | Every pull request and push to `main` | Lint, tests, web build, image build check, compose check, Trivy, Semgrep |
| `.github/workflows/release.yml` | You push a tag starting with `v` | Publishes the two images to GHCR |
| `.github/workflows/deploy.yml` | You start it by hand | Pulls a version on your server and restarts it |

Deploying is manual on purpose. A push never changes production. Add a required reviewer to the `production` environment (Settings, Environments) if you want an approval step as well.

## First-time setup

### 1. GitHub

1. Push the repository to GitHub. Open the Actions tab and confirm the `ci` run is green. Fix anything red before going on.
2. Under Settings, Branches, protect `main` and require the `api`, `web`, `images`, `trivy` and `semgrep` checks.
3. Push a tag to publish images: `git tag v0.1.0 && git push origin v0.1.0`.
4. The images are private by default. Under your profile, Packages, open each of `policydiff-api` and `policydiff-web`, then Package settings. Either make them public, or keep them private and run `docker login ghcr.io` on the server with a token that has `read:packages`.

### 2. The server

1. Create the machine (Ubuntu 24.04). Install Docker with the official script from docs.docker.com.
2. Close every inbound port except SSH for now. Step 3 opens 80 and 443 if you use Caddy; a Cloudflare Tunnel needs neither.
3. Create a folder, for example `/opt/policydiff`, and put three files in it:
   - `docker-compose.prod.yml` (from `deploy/`)
   - `models.yaml` (from the repository root)
   - `.env`, copied from `.env.example`. Set `POSTGRES_PASSWORD`, `SECRET_KEY`, `ADMIN_EMAIL`, `ADMIN_PASSWORD` and `OPENAI_API_KEY`, and leave `COOKIE_SECURE=true`. `chmod 600 .env`.
4. Start it once by hand: `docker compose -f docker-compose.prod.yml up -d`. Wait for `api` to show `healthy`. Test with `curl http://127.0.0.1:8080/api/health`.

### 3. HTTPS on your own subdomain (Caddy)

Use this when you keep your DNS where it is and only want one subdomain, for example `policies.yourdomain.com`. Nothing else on the domain changes.

1. In your DNS provider's panel, add an **A record**: name `policies`, value the server's static IP. Wait a few minutes, then check with `nslookup policies.yourdomain.com`.
2. In the Lightsail Networking tab, open ports **80 and 443** (Caddy needs 80 to prove you own the name).
3. In the server's `.env`, set `DOMAIN=policies.yourdomain.com` and `COMPOSE_PROFILES=caddy`, and leave `COOKIE_SECURE=true`.
4. Run `docker compose -f docker-compose.prod.yml up -d`. Caddy fetches the certificate on its own, which takes under a minute.
5. Open `https://policies.yourdomain.com` and sign in.

If the certificate fails, the cause is almost always the A record not yet pointing at the server, or port 80 closed. `docker compose -f docker-compose.prod.yml logs caddy` shows the reason.

### 3b. Alternative: Cloudflare Tunnel

Use this only if you are willing to move the whole domain's DNS to Cloudflare. It needs no open ports.

1. In the Cloudflare dashboard, open Zero Trust, Networks, Tunnels, and create a tunnel. Choose the Docker option and copy the token.
2. Add a public hostname, for example `policies.yourdomain.com`, with the service `http://web:8080`.
3. In the server's `.env`, set `TUNNEL_TOKEN=...` and `COMPOSE_PROFILES=tunnel`.
4. Run `docker compose -f docker-compose.prod.yml up -d`.
5. Optional: under Zero Trust, Access, Applications, add a self-hosted application for the same hostname and allow only your email addresses.

Choose one of the two. Do not set both profiles.

### 4. Let GitHub deploy

In the repository, Settings, Secrets and variables, Actions, add:

| Secret | Value |
| --- | --- |
| `DEPLOY_HOST` | The server's address |
| `DEPLOY_USER` | The SSH user, in the `docker` group |
| `DEPLOY_SSH_KEY` | A private key made only for this. Put its public half in that user's `~/.ssh/authorized_keys` |
| `DEPLOY_PATH` | `/opt/policydiff` |

Create the `production` environment under Settings, Environments. After that, Actions, deploy, Run workflow, version `0.1.0`.

If the server's SSH port is closed to the internet, this workflow cannot reach it. Either allow SSH from GitHub, or skip `deploy.yml` and run `docker compose -f docker-compose.prod.yml pull && docker compose -f docker-compose.prod.yml up -d` on the server yourself.

## Backups

Back up two Docker volumes, `policydiff_pgdata` (the database) and `policydiff_files` (the PDFs), or use R2 or S3 for the PDFs. On Lightsail or EC2, enable automatic snapshots. A plain database dump is also worth taking before an upgrade:

```bash
docker compose -f docker-compose.prod.yml exec -T db sh -c 'pg_dump -U "$POSTGRES_USER" "$POSTGRES_DB"' > backup.sql
```

Keep `SECRET_KEY` somewhere safe outside the server. Without it the keys saved on the Settings page cannot be decrypted.

## Using Bedrock on AWS

On EC2 or Lightsail with an IAM role (EC2) that allows `bedrock:InvokeModel`, set `AWS_REGION` in `.env` and pick Bedrock on the Settings page. No API key is stored. The Bedrock adapter has only been tested against a fake client, so try it with the Settings page Preview before relying on it.

## Not done yet

- No server has been set up from this guide, so the commands above are untested end to end.
- Images are built for x86 (amd64) only.
- Nothing watches the site for downtime. A free uptime check on `/api/health` (UptimeRobot or Cloudflare Health Checks) is a good first addition.
