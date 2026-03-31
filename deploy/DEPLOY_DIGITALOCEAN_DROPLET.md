## What you’ll deploy

- **Postgres**: `db`
- **Redis**: `redis`
- **FastAPI API**: `backend` (runs Alembic migrations on boot)
- **Celery worker**: `celery`
- **Frontend**: `frontend` (static build served by nginx inside the container)
- **HTTPS reverse proxy**: `caddy` (automatic Let’s Encrypt TLS)

This deployment uses Docker on a **DigitalOcean Droplet**.

---

## 1) Create the Droplet

- **Ubuntu**: 22.04 or 24.04 LTS
- **Size**: start with at least **2 vCPU / 4GB** (Playwright + OCR + LLM workloads can spike)
- **Add SSH key**

After creation, SSH in:

```bash
ssh root@YOUR_DROPLET_IP
```

---

## 2) Install Docker + docker compose

```bash
apt update
apt install -y ca-certificates curl gnupg

install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
chmod a+r /etc/apt/keyrings/docker.gpg

echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo $VERSION_CODENAME) stable" \
  > /etc/apt/sources.list.d/docker.list

apt update
apt install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

docker version
docker compose version
```

---

## 3) Point your domain to the Droplet

In DigitalOcean DNS (or your DNS provider):

- Create an **A record**: `your-domain.com` → `YOUR_DROPLET_IP`
- (Optional) also `www.your-domain.com` → `YOUR_DROPLET_IP`

Wait until DNS resolves:

```bash
dig +short your-domain.com
```

---

## 4) Put the project on the server

### Option A (recommended): Git clone

```bash
apt install -y git
mkdir -p /opt/sam-project
cd /opt/sam-project
git clone YOUR_REPO_URL .
```

### Option B: SCP upload

Upload your repo to `/opt/sam-project` (skip `node_modules`, `venv`, large data folders).

---

## 5) Create the production env file

```bash
cd /opt/sam-project
cp deploy/.env.prod.example deploy/.env.prod
nano deploy/.env.prod
```

Minimum values you must set:

- `DOMAIN`
- `ACME_EMAIL`
- `POSTGRES_PASSWORD`
- `SECRET_KEY`
- `JWT_SECRET_KEY`
- `FRONTEND_URL`
- `CORS_ORIGINS`

---

## 6) Start the stack

```bash
cd /opt/sam-project
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod up -d --build
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod ps
```

Check logs if something fails:

```bash
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod logs -f --tail=200 caddy
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod logs -f --tail=200 backend
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod logs -f --tail=200 celery
```

Once running, open:

- `https://your-domain.com`
- `https://your-domain.com/health`
- `https://your-domain.com/docs`

---

## 7) Server firewall (recommended)

```bash
ufw allow OpenSSH
ufw allow 80
ufw allow 443
ufw enable
ufw status
```

---

## 8) Updating the app

```bash
cd /opt/sam-project
git pull
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod up -d --build
```

---

## 9) Backups (minimum)

Create a daily Postgres dump (example):

```bash
mkdir -p /opt/backups/samgov
crontab -e
```

Cron line (runs at 3am):

```bash
0 3 * * * cd /opt/sam-project && docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod exec -T db pg_dump -U $POSTGRES_USER $POSTGRES_DB | gzip > /opt/backups/samgov/pg_$(date +\%F).sql.gz
```

---

## Notes / common gotchas

- **OAuth callbacks**: set `GOOGLE_REDIRECT_URI` / `MICROSOFT_REDIRECT_URI` to your HTTPS domain routes.
- **CORS**: must include exactly your frontend origin(s), e.g. `https://your-domain.com`.
- **Google Document AI**: if you enable it, don’t bake JSON keys into the repo. Prefer Docker secrets; otherwise copy key file to server and mount it.
