# Modal developer notes

## Introduction

This repository is a basic mono repo. It contains all 3 parts that need development: A frontend, a backend and an agent that
will enable the frontend to pick a folder from the file system. 

Starting the application aa a user is different from starting the different parts of the application as a developer. When 
you start as a developer, all code is run locally on your computer. That means that the frontend code can just talk to 
the running backend service using `localhost`. 

When run as a user, the code will run inside a docker container. So the frontend docker container will have to talk to 
the backend container, with the agent, etc. but from inside the container. Communication between all parts will be different. 

That is why starting up everything for development requires a flag. 

## Starting the services for development

### On the use of venv

In order to not interfere with anything python related on our personal computers, we use venv, a virtual environment where
a developer can install any requirements without interfering with the OS. 

### Agent
For development, the agent should be starting up everything for our users, but that is
not something we want while developing. Therefore, we need to start the agent manually, with a development flag --dev.

Here is what needs to be done to start up the agent directory:

```bash
cd agent
python3 -m venv venv    # In case there is no virtual environment yet. 
source venv/bin/activate        # on Windows: venv\Scripts\activate
pip install -r requirements.txt
python agent.py --dev
```

### Backend

#### Using Alembic

Make sure that the database container has started!
When you develop for the first time on this project or you have new migration files, please execute the following:

```bash
 cd backend                                                                                                                                                                                                
DATABASE_URL=postgresql://archiveuser:archivepass@localhost:5442/modaldb venv/bin/alembic upgrade head
```

Starting up the backend service

```bash
cd backend
python3 -m venv venv    # In case there is no virtual environmnet yet
pip install -r requirements.txt
venv/bin/uvicorn app.main:app --reload   #if you are working with a virtual environment called venv
```

#### The .env file

The backend needs to support two environments for DATABASE_URL:

- In Docker: postgresql+asyncpg://archiveuser:archivepass@db:5432/modaldb
- Local dev: postgresql+asyncpg://archiveuser:archivepass@localhost:5442/modaldb

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

#### Running the test suite locally (one-time setup)

`backend/tests/` is split into `unit/`, `integration/` and `e2e/`. The latter two need
a couple of things that the Dockerfile already sets up for the running app, but that a
fresh local conda/venv environment does **not** have by default:

- **`DATABASE_URL_SYNC` must use the `+psycopg` scheme, not `+psycopg2`.**
  `requirements.txt` installs `psycopg[binary]` (psycopg v3 — the package is literally
  named `psycopg`). The legacy `psycopg2` package is never installed, so a
  `DATABASE_URL_SYNC=postgresql+psycopg2://...` URL fails with
  `ModuleNotFoundError: No module named 'psycopg2'` the moment a sync test/script tries
  to connect. Use `postgresql+psycopg://...` instead (see `.env.example`).
  `DATABASE_URL_SYNC` is only read by dev scripts (`scripts/*.py`) and the
  `db_conn`/`async_db_session` fixtures in `tests/conftest.py` — the running app never
  uses it, so this has no effect on the release/Docker image.

- **The spaCy Dutch model (`nl_core_news_lg`) must be downloaded once per environment:**
  ```bash
  python -m spacy download nl_core_news_lg
  ```
  The Dockerfile already runs this during image build (`RUN python -m spacy download
  nl_core_news_lg`), so this is a release/Docker non-issue — it only needs to be done
  manually in a local dev environment that wasn't built from the Dockerfile.

- If you see `ImportError: DLL load failed ... geblokkeerd door een beleid voor
  toepassingsbeheer` when importing spaCy on Windows, that's unrelated to the project —
  it's a local endpoint-security policy (Smart App Control / HP Wolf Security / similar)
  blocking spaCy's compiled `.pyd` files. `tests/unit/test_ner_engine.py` and
  `tests/e2e/test_ner_e2e.py` catch this specific `ImportError` and skip with a message
  pointing at Smart App Control, instead of failing the whole collection.

#### NER column naming (fixed 2026-06-16)

`ner_engine.run_ner()`, the `ner` DB table (migration `0005_add_ner_table.py`) and
`NerRepository` all use the plural form `persons_count` / `locations_count`. The three
NER test files still used the old singular `person_count` / `location_count` from
before that rename, which is why they failed with `KeyError`/`UndefinedColumn` — the
tests were outdated, not the production code or the DB schema (already on Alembic
revision `0007`, no migration was missing).

While fixing the tests, an actual production bug surfaced: `ner_engine.py`'s
`_LABEL_MAP` mapped spaCy's `"PER"` label to `"persons"`, but `nl_core_news_lg`
actually emits `"PERSON"` for person entities. Every detected person was silently
falling through to the `misc` bucket instead of `persons`. Fixed in
`app/create_ner_for_archive/ner_engine.py`.

### Frontend

The frontend is the easiest one to start. Do mind that a `ngingx.conf` is set up which will proxy the calls to the backend,
circumventing problems with CORS. 

```bash
cd frontend
npm install
npm start
```