# Archive Analysis App

A hybrid Docker + native agent application for ingesting, analyzing, and browsing file archives using Apache Tika, NER, and other NLP tools.

## Architecture

```
Browser (Angular) → Python Backend (Docker) → Local Agent (native) → Filesystem
                  → Tika Server (Docker)
                  → PostgreSQL (Docker)
```

- **Frontend**: Angular, served via nginx in Docker
- **Backend**: Python (FastAPI), runs in Docker
- **Tika**: Apache Tika, official Docker image
- **Database**: PostgreSQL in Docker
- **Agent**: Lightweight native Python script — filesystem bridge + app launcher

See `docs/architecture-summary.md` for the full architecture overview.

## Project Structure

```
archive-app/
├── frontend/           # Angular application
│   ├── Dockerfile
│   ├── nginx.conf
│   └── src/
├── backend/            # Python FastAPI backend
│   ├── Dockerfile
│   ├── requirements.txt
│   └── app/
├── agent/              # Native launcher + filesystem bridge
│   ├── agent.py
│   ├── config.json
│   ├── requirements.txt
│   └── build.sh
├── docker-compose.yml
└── .github/workflows/  # CI/CD pipelines (path-filtered)
    ├── frontend.yml
    ├── backend.yml
    └── agent.yml
```

## Quick Start

### Prerequisites

- Docker Desktop (running)
- Python 3.12+ (for the agent, or use the pre-built binary)

### Option A: Using the agent as launcher (recommended)

```bash
# Install agent dependencies (one-time)
cd agent
pip install -r requirements.txt

# Start everything
python agent.py
```

This will:
1. Start all Docker services (frontend, backend, Tika, PostgreSQL)
2. Start the filesystem bridge API on `localhost:9090`
3. Open the browser to `http://localhost:4200`

Press `Ctrl+C` to stop everything.

### Option B: Manual startup

```bash
# Start Docker services
docker compose up -d

# Start the agent separately
cd agent
python agent.py --no-docker  # TODO: implement flag
```

## Development

### Backend

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### Frontend

```bash
cd frontend
npm install
ng serve
```

### Agent

```bash
cd agent
pip install -r requirements.txt
python agent.py
```

## Building the Agent Binary

```bash
cd agent
pip install pyinstaller
bash build.sh
# Output: dist/archive-agent
```

## CI/CD

Each component has its own GitHub Actions pipeline, triggered only by changes to its directory:

| Pipeline | Trigger path | Output |
|----------|-------------|--------|
| Frontend | `frontend/**` | Docker image |
| Backend  | `backend/**`  | Docker image |
| Agent    | `agent/**`    | Native binary (Linux, macOS, Windows) |
