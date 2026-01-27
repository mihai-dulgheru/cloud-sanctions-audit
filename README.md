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
- **Docker Ready**: Production-optimized containers

## 🚀 Quick Start

### Prerequisites

- Docker & Docker Compose
- DigitalOcean Spaces bucket
- OpenAI API key (optional, for AI analysis)

### Setup

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

### Local Development

**Backend:**

```bash
cd backend
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

## 📁 Project Structure

```text
cloud-sanctions-audit/
├── backend/
│   ├── main.py          # FastAPI application
│   ├── storage.py       # S3/Spaces utilities
│   ├── requirements.txt
│   └── Dockerfile
├── frontend/
│   ├── pages/
│   │   ├── index.js     # Search page
│   │   └── results.js   # Results display
│   ├── styles/
│   │   └── globals.css
│   ├── package.json
│   └── Dockerfile
├── docker-compose.yml
├── .env.example
└── README.md
```

## 🔧 Environment Variables

| Variable             | Description                                 |
| -------------------- | ------------------------------------------- |
| `DO_SPACES_KEY`      | DigitalOcean Spaces access key              |
| `DO_SPACES_SECRET`   | Spaces secret key                           |
| `DO_SPACES_ENDPOINT` | e.g., `https://nyc3.digitaloceanspaces.com` |
| `DO_SPACES_REGION`   | e.g., `nyc3`                                |
| `DO_BUCKET_NAME`     | Your bucket name                            |
| `OPENAI_API_KEY`     | OpenAI API key for AI analysis              |

## 📊 API Endpoints

- `POST /search` - Main sanctions screening endpoint
- `GET /health` - Health check
- `GET /docs` - Interactive API documentation

## 🗄️ Storage Structure

```text
bucket/
├── cache/
│   └── consolidated.xml     # UN sanctions cache
└── audit_logs/
    └── {YEAR}/
        └── {MONTH}/
            └── {NAME}_{TIMESTAMP}/
                ├── evidence_eu.png
                ├── evidence_un.html
                ├── raw_data.json
                └── audit_log.txt
```

## 📝 License

MIT
