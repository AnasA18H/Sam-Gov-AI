# DigitalOcean App Platform Deployment Guide

This guide describes how to deploy the Sam Gov AI application to DigitalOcean using the **App Platform**. This is a fully managed service that handles scaling, SSL, and zero-downtime deployments.

## 1. Prerequisites

- A **GitHub** repository containing your code.
- A **DigitalOcean** account.
- Required API keys (Anthropic, Tavily, etc.).

## 2. Infrastructure Overview

The deployment consists of:
- **Web Service (`backend`)**: The FastAPI application.
- **Worker (`celery-worker`)**: Background task processor.
- **Static Site/Web Service (`frontend`)**: The React/Vite interface.
- **Managed PostgreSQL**: Relational database.
- **Managed Redis**: Message broker for Celery.
- **Spaces (S3)**: Object storage for documents.

---

## 3. Step-by-Step Deployment

### Step 3.1: Prepare Object Storage (Spaces)
1. Go to **Spaces** in your DigitalOcean dashboard.
2. Create a new bucket (e.g., `samgov-docs`).
3. Under **Settings** -> **CORS Configurations**, add your future app domain (or `*` for testing) to allow frontend access if needed.
4. Generate **Access Keys** in **API** -> **Spaces Access Keys**. Copy the **Key** and **Secret**.

### Step 3.2: Create the App
1. Go to **Apps** and click **Create App**.
2. Select **GitHub** as the source and select your repository.
3. App Platform will detect the repository. Click **Next**.
4. **Resources Configuration**:
   - The platform might try to auto-detect services. Click **Edit Spec** at the bottom or manually add:
     - **Service: `backend`** (HTTP port 8000, `Dockerfile.backend`).
     - **Service: `frontend`** (HTTP port 80, `Dockerfile.frontend`).
     - **Worker: `celery-worker`** (`Dockerfile.backend`, command: `celery -A backend.app.core.celery_app worker --loglevel=info`).
   - Add **Databases**:
     - Create a **Managed PostgreSQL** (select a size, e.g., Basic $15/mo).
     - Create a **Managed Redis** (select a size).

### Step 3.3: Environment Variables
Add these to the **App-level** settings so they are shared:

| Variable | Value |
| :--- | :--- |
| `SECRET_KEY` | (Generate a random string) |
| `JWT_SECRET_KEY` | (Generate a random string) |
| `STORAGE_TYPE` | `s3` |
| `AWS_ACCESS_KEY_ID` | (Your Spaces Key) |
| `AWS_SECRET_ACCESS_KEY` | (Your Spaces Secret) |
| `AWS_REGION` | `sfo3` |
| `S3_BUCKET_NAME` | `samgov-docs` |
| `AWS_S3_ENDPOINT_URL` | `https://sfo3.digitaloceanspaces.com` |
| `ANTHROPIC_API_KEY` | (Your Anthropic Key) |
| `TAVILY_API_KEY` | (Your Tavily Key) |
| `CORS_ORIGINS` | `https://www.GovOpsAi.com` |

**Automatic Bindings**:
App Platform automatically sets `DATABASE_URL` and `REDIS_URL` when you link the managed databases.

### Step 3.4: Database Migrations
To handle database updates automatically:
1. Add a **Job** component named `db-migrate`.
2. Set it as a **Pre-deploy** job.
3. Use `Dockerfile.backend`.
4. Set the command to: `alembic upgrade head`.

---

## 4. Manual Deployment via App Spec (Recommended)
Instead of the UI, you can use the provided spec file:
1. Copy the contents of `deploy/app-platform/app.yaml`.
2. In the DO App dashboard, go to **Settings** -> **App Spec**.
3. Click **Edit** and paste the YAML.
4. Replace the database placeholders with actual managed DB links if necessary.

---

## 5. Post-Deployment

### 5.1 Verify Health
- Check the `backend` service logs for `Application startup complete`.
- Visit `https://your-app-url.ondigitalocean.app/health`.

### 5.2 Custom Domain
1. In the App dashboard, go to **Settings** -> **Domains**.
2. Add your custom domain (e.g., `app.yourdomain.com`).
3. Follow the CNAME instructions. SSL will be provisioned automatically.

### 5.3 Data Migration
If you have local data to move:
- Use `pg_dump` to export your local DB and `pg_restore` to the Managed DO Postgres.
- Use `aws s3 sync` (with the Spaces endpoint) to move local documents to the Spaces bucket.

---

## 6. Troubleshooting

- **Memory Errors**: If the `celery-worker` crashes, increase the instance size (Basic-XS or higher).
- **Redis Connection**: Ensure `REDIS_CELERY_URL` starts with `rediss://` (double 's' for SSL) if using Managed Redis.
- **Migrations**: If the app fails to start, check the `db-migrate` job logs to see if migrations failed.
