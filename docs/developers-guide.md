# Development

This project is a monorepo. It contains the code of 3 particular pieces of software which work together to deliver all
the MODAL features and functionalities. This project relies on Docker to support the AI related features and the database. 

The database is a Postgres datebase with PgVector enabled:  pgvector/pgvector:pg16. 

## Developer guidelines

### DO NOT... 
- ever make changes to the database schema (like adding columns, new tables, indexes,... anything that is DDL) without
Alembic. The application is one that needs to run locally on the computer of other users. Changes you apply on your local
database do not get applied to the database of the user. Alembic is a library that makes sure that the databases of users
all have the same structure.
- work against the ORM that was introduced. We are using SQLAlchemy. You should not bypass this with raw SQL unless you really
have no other choice ( correcting the n+1 problem if it would happen is an example where raw sql is advised). The ORM and the
models ensure consistency and type safety. 
- ignore the repository pattern that was introduced. All DB queries go through a *Repository class that receives an AsyncSession. 
Business logic and routes should not query the database directly, they go through a repository.
- manually commit or rollback inside routes in the backend. The `get_db()` dependency manages this automatically.  
- ever commit the .env file using git. It is in the .gitignore file, it should stay there. This file manages manages local setings
that might be different for different developers. 
- call the backend from the frontend directly. There is an nginx configuration which will help with CORS issues.

### PLEASE DO...
- follow the **Vertical Slice design**. This means that every feature gets its own folder structure. We want to reuse as little
code as possible unless we are sure that the code can be reused without modifications. We haven't been super strict in following
VSA (Vertical Slice Architecture), but the slices itself are the main design decision here. It helps with building features 
in isolation and also it helps with using AI for development. 
- make use of virtual environments for Python. Venv helps with keeping a developers environment for python separated from 
for example the python things that run on your Linux or Mac installation. This is important because without venv you might
install or change libraries that are used by your system and thus break your Linux or Mac. 
- **download the spaCy Dutch model** for testing locally. You only need to do that once by doing the following from the root: 
```shell
cd backend
python3.12 -m venv venv    # In case there is no virtual environment yet.
source venv/bin/activate        # on Windows: venv\Scripts\activate
 python -m spacy download nl_core_news_lg
```

### On the use of venv

For development, we need a virtual environments. Like already stated, a virtual environment for python keeps your system
safe. We advise to use virtual environments whenever you are installing dependencies for either the backend or the agent. That
means 2 virtual environments. 

This might be confusing, because this is a monorepo and everything seems to be one big piece of code. However, this repository
does house 3 different applications, 2 of which are python applications. Therefor, create a virtual environment for both
the agent and the backend. 

Here is how it works. 
```shell
# Open a terminal window, preferably from within your IDE. When you use the IDE to open a terminal, the terminal will 
# at the project root folder already. If not using an IDE, open a terminal and go to the project root. 
# You start a virtual environment with the following commands: 
python3.12 -m venv venv    # check your python installation.
source venv/bin/activate        # on Windows: venv\Scripts\activate

# Starting a virtual environment for the backend: 
cd backend # from the project root folder
python3.12 -m venv venv    # In case there is no virtual environment yet.
source venv/bin/activate        # on Windows: venv\Scripts\activate

# Starting a virtual environment for the agent:
cd agent # from the porject root folder
python3.12 -m venv venv    # In case there is no virtual environment yet.
source venv/bin/activate        # on Windows: venv\Scripts\activate
```
This way you can safely install the requirements for both the agent and the backend: 
```shell
pip install -r requirements.txt
```


### starting the agent
The agent should be starting up everything for our users, but that is
not something we want while developing. Therefore, we need to start the agent manually, with a development flag --dev. In order
to not interfere with anything python related on our personal computers, we use venv. Here is the setup for
From the agent directory:

```bash
cd agent
python3.12 -m venv venv    # In case there is no virtual environment yet. 
source venv/bin/activate        # on Windows: venv\Scripts\activate
pip install -r requirements.txt
python agent.py --dev
```

_Remark: To get started on a windows 11 machine_
```bash
cd agent
py -m venv .venv
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python agent.py --dev
```

### Backend

```bash
cd backend
python3.12 -m venv venv    # In case there is no virtual environmnet yet
pip install -r requirements.txt
python -m spacy download nl_core_news_lg
venv/bin/uvicorn app.main:app --reload --port 8010   #if you are working with a virtual environment called venv
```

_Remark: To get started on a windows 11 machine
```bash
cd backend
py -m venv .venv
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope Process
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:DATABASE_URL="postgresql+asyncpg://archiveuser:archivepass@127.0.0.1:5442/modaldb"
uvicorn app.main:app --reload --port 8010
```

#### Using Alembic

Make sure that the database container has started!
When you develop for the first time on this project or you have new migration files, please execute the following:

```bash
cd backend                                                                                                                               
DATABASE_URL=postgresql+psycopg://archiveuser:archivepass@localhost:5442/modaldb venv/bin/alembic upgrade head
```

_Remark: To get started on a windows 11 machine. Run before running uvicorn_
```bash
cd backend
$env:DATABASE_URL="postgresql+psycopg://archiveuser:archivepass@localhost:5442/modaldb"
alembic upgrade head
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

### Frontend

Requires Node.js to be installed, https://nodejs.org/en/download
```bash
cd frontend
npm install
npm start
```