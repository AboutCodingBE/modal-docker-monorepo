# Architecture

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

### Option A: Using the agent as launcher (recommended, but not during development)

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
3. Open the browser to `http://localhost:4210`

Press `Ctrl+C` to stop everything.
