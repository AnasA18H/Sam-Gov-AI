# Deployment Guide - Digital Ocean

This guide covers deploying the Sam Gov AI application to Digital Ocean.

## Deployment Options

### Option 1: Digital Ocean App Platform (Recommended - Easiest)

Fully managed platform with automatic SSL, scaling, and database management.

### Option 2: Droplet + Docker Compose (More Control)

Self-managed server with Docker Compose for full control.

---

## Option 1: Digital Ocean App Platform

### Prerequisites

1. Digital Ocean account
2. GitHub repository (code pushed)
3. `doctl` CLI tool (optional)

### Steps

#### 1. Prepare Your Code

```bash
# Ensure all code is committed and pushed to GitHub
git add .
git commit -m "Prepare for deployment"
git push origin main
```

#### 2. Create Production Environment Variables

Copy `.env.production.example` to create your production secrets:

```bash
cp .env.production.example .env.production
```

Generate secure secrets:

```bash
# Generate SECRET_KEY
openssl rand -hex 32

# Generate JWT_SECRET_KEY
openssl rand -hex 32
```

#### 3. Update app.yaml

Edit `app.yaml`:
- Replace `YOUR_GITHUB_USERNAME/YOUR_REPO_NAME` with your actual GitHub repo
- Adjust region if needed (default: `nyc`)

#### 4. Deploy via Dashboard

1. Go to [Digital Ocean App Platform](https://cloud.digitalocean.com/apps)
2. Click "Create App"
3. Connect your GitHub repository
4. Select the repository and branch
5. Choose "App Spec File" and upload `app.yaml`
6. Configure environment variables in the dashboard:
   - `SECRET_KEY` (from step 2)
   - `JWT_SECRET_KEY` (from step 2)
7. Review and deploy

#### 5. Set Up Managed Database

1. In App Platform, go to "Components"
2. Add "Database" → PostgreSQL
3. Note the `DATABASE_URL` connection string
4. Update your backend service environment variables

#### 6. Set Up Managed Redis

1. In App Platform, go to "Components"
2. Add "Database" → Redis
3. Note the `REDIS_URL` connection string
4. Update your backend service environment variables

#### 7. Run Migrations

After deployment, run database migrations:

```bash
# Via App Platform console
alembic upgrade head
```

Or via doctl:

```bash
doctl apps logs <app-id> --component backend --follow
```

### App Platform Costs (Approximate)

- Basic App: $5-12/month per service
- Managed PostgreSQL: $15/month (starter)
- Managed Redis: $15/month (starter)
- **Total: ~$50-60/month for MVP**

---

## Option 2: Droplet + Docker Compose

### Prerequisites

1. Digital Ocean Droplet (Ubuntu 22.04 recommended)
   - Minimum: 2GB RAM, 1 vCPU ($12/month)
   - Recommended: 4GB RAM, 2 vCPU ($24/month)
2. Domain name (optional but recommended)
3. SSH access to droplet

### Steps

#### 1. Create Droplet

1. Go to Digital Ocean → Droplets → Create
2. Choose Ubuntu 22.04
3. Select size (minimum 2GB RAM)
4. Choose region
5. Add SSH key
6. Create droplet

#### 2. Initial Server Setup

```bash
# SSH into your droplet
ssh root@your-droplet-ip

# Update system
apt update && apt upgrade -y

# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sh get-docker.sh

# Install Docker Compose
apt install docker-compose-plugin -y

# Create application user (optional but recommended)
adduser samgov
usermod -aG docker samgov
```

#### 3. Deploy Application

```bash
# Switch to application user
su - samgov

# Clone repository
git clone https://github.com/yourusername/your-repo.git
cd your-repo

# Create production environment file
cp .env.production.example .env.production
nano .env.production  # Edit with your values

# Build and start services
docker compose up -d --build

# Check logs
docker compose logs -f
```

#### 4. Set Up Nginx (Reverse Proxy)

```bash
# Install Nginx
apt install nginx certbot python3-certbot-nginx -y

# Create Nginx configuration
nano /etc/nginx/sites-available/samgov
```

Add configuration:

```nginx
server {
    listen 80;
    server_name yourdomain.com www.yourdomain.com;

    location / {
        proxy_pass http://localhost:80;  # Frontend
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }

    location /api {
        proxy_pass http://localhost:8000;  # Backend
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

```bash
# Enable site
ln -s /etc/nginx/sites-available/samgov /etc/nginx/sites-enabled/
nginx -t
systemctl reload nginx

# Set up SSL (if you have domain)
certbot --nginx -d yourdomain.com -d www.yourdomain.com
```

#### 5. Set Up Firewall

```bash
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw enable
```

#### 6. Run Migrations

```bash
docker compose exec backend alembic upgrade head
```

### Droplet Costs

- Droplet (2GB): $12/month
- Droplet (4GB): $24/month
- Domain: $0-15/year
- **Total: ~$12-24/month** (more cost-effective but requires management)

---

## Production Checklist

Before deploying, ensure:

- [ ] All secrets are in environment variables (not hardcoded)
- [ ] `DEBUG=False` in production
- [ ] Strong `SECRET_KEY` and `JWT_SECRET_KEY` generated
- [ ] Database migrations tested
- [ ] CORS origins configured for your domain
- [ ] SSL certificates configured (App Platform does this automatically)
- [ ] Health checks configured
- [ ] Logs are being captured
- [ ] Backup strategy for database

## Monitoring

### App Platform

- Built-in monitoring dashboard
- Log aggregation
- Performance metrics

### Droplet

```bash
# View logs
docker compose logs -f

# Resource usage
htop

# Disk usage
df -h
```

## Updates and Maintenance

### App Platform

- Automatic deployments on git push (if configured)
- Or manual deployments via dashboard

### Droplet

```bash
# SSH into server
ssh samgov@your-droplet-ip

# Navigate to app directory
cd ~/your-repo

# Pull latest changes
git pull origin main

# Rebuild and restart
docker compose down
docker compose up -d --build

# Run migrations if needed
docker compose exec backend alembic upgrade head
```

## Troubleshooting

### Backend won't start

```bash
# Check logs
docker compose logs backend

# Check database connection
docker compose exec backend python -c "from backend.app.core.database import engine; engine.connect()"
```

### Frontend not loading

```bash
# Check frontend logs
docker compose logs frontend

# Verify nginx configuration
nginx -t
```

### Database connection issues

- Verify `DATABASE_URL` is correct
- Check database is running: `docker compose ps db`
- Test connection: `docker compose exec backend psql $DATABASE_URL`

## Support

For issues:
1. Check application logs
2. Review Digital Ocean status page
3. Check application health endpoints
4. Review this documentation

---

## Next Steps After Deployment

1. Set up automated backups for database
2. Configure monitoring and alerting
3. Set up CI/CD pipeline
4. Configure custom domain
5. Review security settings
6. Set up staging environment
