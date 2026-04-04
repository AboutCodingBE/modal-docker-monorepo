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
3. Open the browser to `http://localhost:4200`

Press `Ctrl+C` to stop everything.


## Development

### On the use of venv

For development, we need a virtual environment. The agent should be starting up everything for our users, but that is 
not something we want while developing. Therefore, we need to start the agent manually, with a development flag --dev. In order
to not interfere with anything python related on our personal computers, we use venv. Here is the setup for 
From the agent directory:

```bash
cd agent
python3 -m venv venv
source venv/bin/activate        # on Windows: venv\Scripts\activate
pip install -r requirements.txt
python agent.py --dev
```

The "command not found" is likely because either python isn't on your PATH (some systems only have python3) or Flask isn't installed globally — which is exactly what the venv solves.
For packaging: PyInstaller bundles everything — your code, Python itself, and all installed packages — into a single standalone binary. It doesn't use or need the venv at runtime. The venv is purely a development tool. When you run pyinstaller --onefile agent.py, it inspects the current environment, grabs all dependencies, and bakes them into the executable. The end user just double-clicks the binary. No Python, no venv, nothing to install.
So the two worlds are completely separate: venv for development, PyInstaller binary for distribution. They don't interfere with each other.
One small tip: when you eventually build the binary, do it from inside the venv so PyInstaller only picks up the agent's dependencies (Flask, flask-cors) and not anything else you might have installed globally. Keeps the binary lean.

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

