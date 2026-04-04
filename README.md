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

### Backend

```bash
cd backend
pip install -r requirements.txt
venv/bin/uvicorn app.main:app --reload   #if you are working with a virtual environment called venv
```

#### Using Alembic

Make sure that the database container has started! 
When you develop for the first time on this project or you have new migration files, please execute the following: 

```bash
 cd backend                                                                                                                                                                                                
DATABASE_URL=postgresql://archiveuser:archivepass@localhost:5432/modaldb venv/bin/alembic upgrade head 
```
#### The .env file

The backend needs to support two environments for DATABASE_URL:

- In Docker: postgresql+asyncpg://archiveuser:archivepass@db:5432/modaldb
- Local dev: postgresql+asyncpg://archiveuser:archivepass@localhost:5432/modaldb

I created a .env file in the backend directory with the local dev
DATABASE_URL. Updated app/config.py to load from .env using
pydantic-settings. Added .env to .gitignore. Added a .env.example
with the local dev defaults so other developers know what to set.

The docker-compose.yml should keep setting DATABASE_URL as an
environment variable, which will override the .env file when
running in Docker.

**How pydantic-settings uses it:** 
when your FastAPI app starts, pydantic-settings looks for values in this order (highest priority first):

1. Environment variables — set by Docker, the OS, or the command line
2. .env file — loaded from disk as a fallback

### Frontend

```bash
cd frontend
npm install
npm start
```

### Agent

```bash
cd agent
pip install -r requirements.txt
python agent.py  # activate virtual environment first if you have it. 
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

