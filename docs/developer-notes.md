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
DATABASE_URL=postgresql://archiveuser:archivepass@localhost:5432/modaldb venv/bin/alembic upgrade head 
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

The frontend is the easiest one to start. Do mind that a `ngingx.conf` is set up which will proxy the calls to the backend,
circumventing problems with CORS. 

```bash
cd frontend
npm install
npm start
```