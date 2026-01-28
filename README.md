# Sanctions Screening PoC

A production-ready proof of concept for sanctions screening, featuring automated evidence collection and AI-powered risk analysis.

## 🏗️ Architecture

```text
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   Next.js       │────▶│   FastAPI       │────▶│   DO Spaces     │
│   Frontend      │     │   Backend       │     │   (S3)          │
│   :3000         │     │   :8000         │     │                 │
└─────────────────┘     └─────────────────┘     └─────────────────┘
                               │
                    ┌──────────┼──────────┐
                    ▼          ▼          ▼
              ┌──────────┐ ┌──────────┐ ┌──────────┐
              │ EU API   │ │ UN XML   │ │ OpenAI   │
              │ + Screen │ │ Parser   │ │ Analysis │
              └──────────┘ └──────────┘ └──────────┘
```

## ✨ Features

- **EU Sanctions Map Integration**: API queries + Playwright screenshots
- **UN Security Council**: XML parsing with 24h caching
- **Stateless Storage**: All evidence stored in DigitalOcean Spaces
- **AI Risk Analysis**: GPT-powered risk scoring and summaries
- **Presigned URLs**: Secure, temporary access to evidence files
- **Docker Ready**: Production-optimized containers for DigitalOcean

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose v2+
- DigitalOcean Spaces bucket
- OpenAI API key (optional, for AI analysis)

### Local Development Setup

1. **Clone and configure:**

   ```bash
   cp .env.example .env
   # Edit .env with your credentials
   ```

2. **Run with Docker:**

   ```bash
   docker-compose up --build
   ```

3. **Access:**
   - Frontend: <http://localhost:3000>
   - Backend API: <http://localhost:8000>
   - API Docs: <http://localhost:8000/docs>

### Development Without Docker

**Backend:**

```bash
cd backend
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
playwright install chromium
uvicorn main:app --reload
```

**Frontend:**

```bash
cd frontend
npm install
npm run dev
```

## ☁️ DigitalOcean Deployment

### Option 1: DigitalOcean Droplet (Recommended)

Deploy to a Droplet with Docker pre-installed.

#### 1. Create a Droplet

- Choose **Docker** from the Marketplace
- Recommended: 2GB RAM / 1 vCPU minimum (4GB recommended for Playwright)
- Enable monitoring and backups

#### 2. Initial Server Setup

```bash
# SSH into your droplet
ssh root@your-droplet-ip

# Clone the repository
git clone https://github.com/your-repo/cloud-sanctions-audit.git
cd cloud-sanctions-audit

# Create environment file
cp .env.example .env
nano .env  # Edit with your production values
```

#### 3. Configure Environment

Update `.env` with production values:

```bash
# DigitalOcean Spaces
DO_SPACES_KEY=your_spaces_access_key
DO_SPACES_SECRET=your_spaces_secret_key
DO_SPACES_ENDPOINT=https://nyc3.digitaloceanspaces.com
DO_SPACES_REGION=nyc3
DO_BUCKET_NAME=sanctions-audit

# OpenAI
OPENAI_API_KEY=sk-your-production-key

# Frontend URLs (use your domain or droplet IP)
NEXT_PUBLIC_BACKEND_URL=https://your-domain.com
BACKEND_URL=http://backend:8000
```

#### 4. Deploy with Docker Compose

```bash
# Build and start containers
docker-compose up -d --build

# Check status
docker-compose ps

# View logs
docker-compose logs -f
```

#### 5. Set Up Reverse Proxy (Optional but Recommended)

Install Nginx for SSL termination:

```bash
apt install nginx certbot python3-certbot-nginx

# Configure Nginx
cat > /etc/nginx/sites-available/sanctions-audit << 'EOF'
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    location /api {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
EOF

# Enable site and get SSL certificate
ln -s /etc/nginx/sites-available/sanctions-audit /etc/nginx/sites-enabled/
certbot --nginx -d your-domain.com
systemctl reload nginx
```

### Option 2: DigitalOcean App Platform

Deploy using DigitalOcean's managed container platform.

#### 1. Push to Container Registry

```bash
# Login to DigitalOcean Container Registry
doctl registry login

# Build and push images
docker build -t registry.digitalocean.com/your-registry/sanctions-backend:latest ./backend
docker build -t registry.digitalocean.com/your-registry/sanctions-frontend:latest ./frontend

docker push registry.digitalocean.com/your-registry/sanctions-backend:latest
docker push registry.digitalocean.com/your-registry/sanctions-frontend:latest
```

#### 2. Create App Spec

Create `app.yaml` in the project root:

```yaml
name: sanctions-audit
region: nyc
services:
  - name: backend
    image:
      registry_type: DOCR
      repository: sanctions-backend
      tag: latest
    instance_count: 1
    instance_size_slug: professional-xs
    http_port: 8000
    health_check:
      http_path: /health
    envs:
      - key: DO_SPACES_KEY
        scope: RUN_TIME
        type: SECRET
      - key: DO_SPACES_SECRET
        scope: RUN_TIME
        type: SECRET
      - key: DO_SPACES_ENDPOINT
        scope: RUN_TIME
        value: https://nyc3.digitaloceanspaces.com
      - key: DO_SPACES_REGION
        scope: RUN_TIME
        value: nyc3
      - key: DO_BUCKET_NAME
        scope: RUN_TIME
        value: sanctions-audit
      - key: OPENAI_API_KEY
        scope: RUN_TIME
        type: SECRET

  - name: frontend
    image:
      registry_type: DOCR
      repository: sanctions-frontend
      tag: latest
    instance_count: 1
    instance_size_slug: basic-xxs
    http_port: 3000
    routes:
      - path: /
    envs:
      - key: NEXT_PUBLIC_BACKEND_URL
        scope: RUN_AND_BUILD_TIME
        value: ${backend.PUBLIC_URL}
      - key: BACKEND_URL
        scope: RUN_TIME
        value: ${backend.PRIVATE_URL}
```

#### 3. Deploy

```bash
doctl apps create --spec app.yaml
```

### Deployment Checklist

- [ ] DigitalOcean Spaces bucket created and configured
- [ ] Environment variables set with production values
- [ ] Docker images built successfully
- [ ] Health checks passing (`/health` endpoint)
- [ ] SSL/TLS configured (if using custom domain)
- [ ] Firewall rules configured (ports 80, 443, 22)
- [ ] Monitoring enabled in DigitalOcean dashboard

## 📁 Project Structure

```text
cloud-sanctions-audit/
├── backend/
│   ├── main.py          # FastAPI application
│   ├── storage.py       # S3/Spaces utilities
│   ├── requirements.txt
│   ├── Dockerfile
│   └── .dockerignore
├── frontend/
│   ├── pages/
│   │   ├── index.js     # Search page
│   │   └── results.js   # Results display
│   ├── styles/
│   │   └── globals.css
│   ├── package.json
│   ├── Dockerfile
│   └── .dockerignore
├── docker-compose.yml
├── .env.example
└── README.md
```

## 🔧 Environment Variables

| Variable                  | Description                                 | Required |
| ------------------------- | ------------------------------------------- | -------- |
| `DO_SPACES_KEY`           | DigitalOcean Spaces access key              | Yes      |
| `DO_SPACES_SECRET`        | Spaces secret key                           | Yes      |
| `DO_SPACES_ENDPOINT`      | e.g., `https://nyc3.digitaloceanspaces.com` | Yes      |
| `DO_SPACES_REGION`        | e.g., `nyc3`                                | Yes      |
| `DO_BUCKET_NAME`          | Your bucket name                            | Yes      |
| `OPENAI_API_KEY`          | OpenAI API key for AI analysis              | No       |
| `NEXT_PUBLIC_BACKEND_URL` | Public backend URL for frontend             | Yes      |
| `BACKEND_URL`             | Internal backend URL (Docker networking)    | Yes      |

## 📊 API Endpoints

- `POST /search` - Main sanctions screening endpoint
- `GET /health` - Health check
- `GET /docs` - Interactive API documentation

## 🔒 Security Considerations

- Non-root users in Docker containers
- Health checks for container orchestration
- Environment-based configuration (12-factor app)
- Presigned URLs for temporary file access
- Network isolation via Docker networks

## 📝 License

MIT
