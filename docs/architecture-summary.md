# Archive Analysis App — Architecture Summary

## Problem Statement

We need an application that can:

- Browse and analyze files on local/external drives
- Perform Tika analysis, NER, and other NLP tasks on those files
- Use Angular as the frontend and Python as the backend
- Manage complex dependencies (Java JRE for Tika, Python ML libraries, etc.)

### The Conundrum

| Approach | Problem |
|----------|---------|
| **Standalone app (Tauri)** | Bundling all dependencies (JRE, Python, ML models) is error-prone and fragile |
| **Docker Compose** | Containers can't access the host filesystem freely, and browsers can't expose full file paths (security restriction) |

## Chosen Solution: Hybrid Architecture (Option B — Pull Model)

Combine Docker for heavy services with a lightweight native agent for filesystem access.

### Components

```
Browser (Angular) → Python Backend (Docker) → Local Agent (native) → Filesystem
                  → Tika Server (Docker)
```

1. **Angular Frontend** — served via nginx in Docker. Provides the UI for browsing previously ingested archives and triggering new ingestions.
2. **Python Backend** — runs in Docker. Orchestrates all processing: calls Tika, runs NER, stores results in the database. Communicates with the local agent to access files.
3. **Apache Tika** — runs in its own Docker container using the official `apache/tika` image (JRE included). The Python backend sends files to it over HTTP. No need to bundle Java in the Python container.
4. **Local Agent** — a small native Python script (~100 lines) running on the host machine. Exposes a REST API for filesystem browsing and file streaming.

### User Journeys

#### Browsing Existing Archives (no agent needed)

The user opens the Angular app, browses previously ingested archives, views extracted text, NER results, and metadata. Everything is served from the database via the Python backend. The local agent is not involved.

#### Ingesting a New Archive (agent required)

The user always selects a **folder**, never individual files. The local agent exposes an HTTP endpoint that the Angular app can reach directly for folder selection. Ingestion happens in two phases.

1. User clicks "Ingest New Archive" in the Angular app.
2. Angular calls the local agent's folder selection endpoint (`http://localhost:9090/pick-folder`).
3. The agent opens a **native folder picker dialog** (e.g., Tkinter's `askdirectory()`).
4. User selects a folder (e.g., `/media/usb-drive/case-2024-003/`).
5. The agent returns the selected path to Angular.
6. Angular tells the Python backend "please ingest from this path."

**Phase 1 — Inventory**: The backend walks the folder tree (via the agent's file-listing endpoint) and registers every file in the database: id, file name, path, parent folder, archive reference, file size, etc. This is fast (no content processing yet) and gives us:
- The total file count — used as the denominator for progress tracking
- A browsable file tree in the UI, visible immediately before analysis begins

**Phase 2 — Processing**: The backend iterates over the inventoried files, pulling each one from the agent on demand:
- `GET /file-content?path=...` — stream a specific file's contents
- Each file is sent to Tika for extraction, then NER and other analyses run
- Results are stored in the database and linked to the file record
- The Angular UI shows a **progress bar** (files processed / total files from Phase 1)

The archive is browsable in the Angular UI as soon as Phase 1 completes. Analysis results appear incrementally as Phase 2 progresses.

### Why Pull Model (not Push)?

Archives can be dozens of gigabytes in size. Copying an entire archive upfront before processing begins is not feasible. Instead, the backend drives the process using a **pull model** — it requests files from the agent one by one, streaming them on demand. This allows:

- Processing to start immediately without waiting for a full copy
- Progress tracking per file
- Resumption if processing is interrupted
- Manageable memory usage regardless of archive size

## Launcher / Startup

The local agent doubles as the **application launcher**. It is the single entry point for the user:

1. User double-clicks the agent executable.
2. The agent checks Docker is available.
3. Runs `docker compose up -d` to start all services.
4. Waits for services to be healthy.
5. Starts its own file-browsing REST API on `localhost:9090`.
6. Opens the browser to `http://localhost:4200` (Angular app).
7. On shutdown (Ctrl+C or system tray), runs `docker compose down`.

The user experience: **start one thing, everything works. Stop it, everything cleans up.**

### Agent Availability Handling

When the user clicks "Ingest New Archive," the Angular app first pings `http://localhost:9090/health`. If unreachable, it shows a message: *"Please start the Local Agent to ingest files from your machine"* with instructions. This makes the agent feel like an optional plugin rather than a hard dependency.

## CI/CD Implications

Two completely separate release cycles:

| Component | Changes | Release |
|-----------|---------|---------|
| **Docker images** (Angular, Python backend, Tika config) | Frequently — new features, bug fixes, model updates | Standard CI/CD pipeline. Users get updates on next `docker compose pull` / restart. |
| **Agent binary** | Almost never — only if the agent's API contract changes | Built and released separately, possibly manually. |

The agent can be made even more future-proof by loading its configuration (port, browser URL, endpoints) from a config file that ships alongside `docker-compose.yml` — updatable through normal CI/CD without rebuilding the binary.

## Logging

| Component | Log Access |
|-----------|------------|
| **Docker services** (backend, Tika, frontend) | `docker compose logs <service>` — captured automatically from stdout/stderr |
| **Local agent** | Writes to a local log file, e.g., `~/.archive-app/agent.log` |

### Recommended progression

- **Start simple**: Docker's built-in logging + agent log file covers most debugging needs.
- **If needed**: Add [Dozzle](https://dozzle.dev/) (lightweight Docker log viewer) — one extra container, five lines in docker-compose, gives a browser-based real-time log view.
- **If scaling**: ELK stack or Loki + Grafana (overkill for now, relevant for multi-user production deployment).

The launcher/agent could also expose a "Show Logs" option (system tray menu or CLI flag) that opens Dozzle or tails `docker compose logs`.

## Technology Choices Summary

| Role | Technology | Why |
|------|-----------|-----|
| Frontend | Angular (Docker, nginx) | Team preference |
| Backend | Python (Docker) | NLP ecosystem, ML libraries |
| Text extraction | Apache Tika (Docker, official image) | Handles 1000+ file formats, JRE included |
| NER / NLP | Python libraries in backend container | spaCy, transformers, etc. |
| Filesystem bridge | Local agent (native Python) | Only component that needs host access |
| Folder picker | Tkinter `askdirectory()` | Zero extra dependencies, cross-platform |
| Launcher | Agent binary (PyInstaller) | Single executable, manages entire lifecycle |
| Database | PostgreSQL or Supabase (Docker) | Stores ingested archive metadata and analysis results |

## Decisions Made

- **Database**: PostgreSQL in Docker, or the Docker version of Supabase (which includes Postgres under the hood).
- **Authentication**: Not needed. Single user on a local machine, no passwords or login required.
- **File watching**: Not needed. Archives are static and do not change after ingestion.
- **Selection granularity**: The user always selects entire folders, never individual files.
- **Data transfer model**: Pull model. The backend streams files from the agent on demand, because archives can be dozens of gigabytes.
- **Ingestion strategy**: Two-phase. Phase 1 inventories all files (fast, gives file count and tree structure). Phase 2 processes files through Tika/NER (slow, tracked via progress bar using Phase 1 totals).
- **Progress tracking**: Progress bar based on files processed vs. total files discovered during inventory.
- **Re-ingestion**: Re-ingesting an archive from the same path creates a **new version**, preserving previous results.

## Open Questions

- **Version management UI**: How should the user navigate between archive versions?
- **Partial re-ingestion**: If Phase 2 is interrupted, should it resume from where it left off or restart?
