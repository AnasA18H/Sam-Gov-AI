# DigitalOcean Deployment (Droplet + Managed PostgreSQL + Spaces)

This guide deploys:
- App services on one Droplet (`backend`, `frontend`, `celery`, `redis`, `caddy`)
- Database on DigitalOcean Managed PostgreSQL
- Document storage (PDF/Word/uploads) on DigitalOcean Spaces

## 1) Prerequisites

- Domain name ready (for example `app.example.com`)
- DigitalOcean account with:
  - 1 Ubuntu Droplet
  - 1 Managed PostgreSQL cluster
  - 1 Spaces bucket
- Local code pushed to GitHub

## 2) Create Infrastructure

### 2.1 Droplet
- Ubuntu 24.04 LTS, at least 2 vCPU / 4 GB RAM
- Add SSH key authentication
- Add DNS `A` record for your domain to droplet public IP

### 2.2 Managed PostgreSQL
- Create DB cluster in same region as droplet
- Create database user and DB name
- Add droplet IP to trusted sources
- Copy connection details and build URL:

```bash
postgresql://USER:PASSWORD@HOST:PORT/DB_NAME?sslmode=require
```

### 2.3 Spaces
- Create private bucket (recommended)
- Create Spaces access key + secret
- Note region endpoint, e.g. `https://nyc3.digitaloceanspaces.com`

## 3) Server Bootstrap

SSH to droplet and install Docker:

```bash
sudo apt-get update
sudo apt-get install -y ca-certificates curl gnupg
sudo install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
sudo chmod a+r /etc/apt/keyrings/docker.gpg
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo \"$VERSION_CODENAME\") stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
sudo apt-get update
sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
sudo usermod -aG docker $USER
newgrp docker
```

Set firewall:

```bash
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw enable
```

## 4) Clone Project and Configure

```bash
git clone <your-repo-url> sam-project
cd sam-project
mkdir -p deploy/secrets logs data
cp deploy/.env.prod.example deploy/.env.prod
```

Edit `deploy/.env.prod`:
- `DOMAIN`, `TLS_EMAIL`
- `DATABASE_URL` (Managed Postgres + `sslmode=require`)
- `SECRET_KEY`, `JWT_SECRET_KEY` (new random values)
- All API keys and OAuth secrets
- Spaces values:
  - `STORAGE_TYPE=s3`
  - `AWS_ACCESS_KEY_ID`
  - `AWS_SECRET_ACCESS_KEY`
  - `AWS_REGION`
  - `S3_BUCKET_NAME`
  - `AWS_S3_ENDPOINT_URL`

Add Google service account file:

```bash
scp ./path/to/google-service-account.json <user>@<droplet-ip>:/home/<user>/sam-project/deploy/secrets/google-service-account.json
chmod 600 deploy/secrets/google-service-account.json
```

## 5) Deploy Stack

From repo root:

```bash
cd deploy
docker compose -f docker-compose.prod.yml --env-file .env.prod build
docker compose -f docker-compose.prod.yml --env-file .env.prod up -d
```

Run migrations explicitly:

```bash
docker compose -f docker-compose.prod.yml --env-file .env.prod exec backend alembic upgrade head
docker compose -f docker-compose.prod.yml --env-file .env.prod exec backend alembic current
```

## 6) Data Migration (Local -> DO)

### 6.1 Database dump and restore

On local machine:

```bash
pg_dump "postgresql://samgov_user:samgov_password@localhost:5432/samgov_db" -Fc -f samgov_db.dump
```

Restore to Managed PostgreSQL (from local or droplet):

```bash
pg_restore \
  --no-owner \
  --no-privileges \
  --dbname "postgresql://USER:PASSWORD@HOST:PORT/DB_NAME?sslmode=require" \
  samgov_db.dump
```

Then run:

```bash
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod exec backend alembic upgrade head
```

### 6.2 File/object migration to Spaces

Install AWS CLI where source files exist:

```bash
aws configure
```

Sync documents and uploads:

```bash
aws s3 sync ./data/documents "s3://<bucket>/documents" --endpoint-url "https://<region>.digitaloceanspaces.com"
aws s3 sync ./data/uploads "s3://<bucket>/uploads" --endpoint-url "https://<region>.digitaloceanspaces.com"
```

## 7) Verification Checklist

Run these checks:

```bash
curl -I https://<your-domain>/health
curl -I https://<your-domain>/docs
```

And verify in app:
- Login works
- Create opportunity works
- Celery tasks process successfully
- Uploaded PDF/Word opens and downloads
- New uploads appear in Spaces bucket

## 8) Backups

- Enable automatic backups in Managed PostgreSQL settings
- Set Spaces lifecycle rules and versioning (optional but recommended)
- Keep weekly `pg_dump` exports to secure storage

## 9) Security Hardening

- Rotate all old local `.env` secrets before production use
- Use SSH keys only (disable password auth in sshd)
- Keep `5432` and `6379` closed publicly
- Keep bucket private, use presigned URLs for file access
- Set `CORS_ORIGINS` only to production domain
- Add Sentry DSN for backend runtime monitoring

## 10) Operations

View logs:

```bash
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod logs -f backend
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod logs -f celery
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod logs -f caddy
```

Rolling update:

```bash
git pull
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod build
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod up -d
docker compose -f deploy/docker-compose.prod.yml --env-file deploy/.env.prod exec backend alembic upgrade head
```
