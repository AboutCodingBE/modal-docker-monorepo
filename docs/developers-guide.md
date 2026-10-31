# Development

This project is a monorepo. It contains the code of 3 particular pieces of software which work together to deliver all
the MODAL features and functionalities. This project relies on Docker to support the AI related features and the database. 

The database is a Postgres datebase with PgVector enabled:  pgvector/pgvector:pg16. 

## Understand the following about this project...
There is a big difference between running the code locally as a developer and the application that runs on the computers
of users. When you run the code as a developer, you run the code as it is on your computer. That is a python application, 
which you can start using python start-up commands. You have a python developer setup on your computer. 

We don't know if users have that python environment. Even worse... we don't know anything about the computer system of
our users. So how do we make sure that the application can run on as many different kinds of computers? We do it by 
transforming out code into a **docker image**. There is a docker image for the frontend and there is one for the backend. 

Teh agent is an exception: that one is a native python application, needed to access the folders of computers. 

The big difference between running the application code versus users starting the application is docker. When starting the
code locally, the code does not run from inside a docker container. When a user runs the application, the code runs from 
a docker container. 


## Developer guidelines

### DO NOT... 
- ever use the production docker file for development (docker-compose.prod.yml). It works differently. During development, 
you run the different parts of the application directly on your computer. The production docker file is a configuration file 
that will end up on computers of the actual users. If you use the production docker file for development, you will feel the 
urge to change that file, but... by doing so, you will break the application that users gets via releases. 
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

### Using Alembic

Make sure that the database container has started!
When you develop for the backend for the first time on this project or there are new migration files, you have to 
execute the following:

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
#### Verions and migrations

Every migration file has a number. These version numbers are a sequence, meaning that the order of execution is important. This 
makes sense, since they perform changes on the structure of the database. If one migration creates a table with column X and Y, 
and in the next migration a column Z is added, it makes sense to run the first migration before hte other. 

The database of the application keeps track of last the version in the table `alembic_version`. This means that you can manually
undo the changes of a migration and then set the alembic_version to a previous number. 

#### Example of how to locally undo or fix a migration
Imagine ther are 2 migration files already. You have run alembic and thus the database is up to date. The alembic version in the `alembic_version`
table should show: 0002. You create a new migration file (0003) in which you create a new table. You run alembic and so the version now is 0003
in the database. 

You realize that you made a mistake. You have not created a release, so the mistake is only on your machine. How can you fix this?

You can manually connect to the database using a database manager like DBeaver or PGAdmin. Using the manager, you can delete / drop the 
new table manually. Then you update the alembic version manually and set it back from 0003 to 0002. Then you can fix your mistake in 
the migration file and run alembic again without troubles. 

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

## Starting the application locally

The first thing to do is to start up the required docker containers: That is ollama, the database and tika. On a **Linux or 
a macOs machine**, you can start all those containers at once using the docker-compose.yml file using the command line. 

You do this by navigating to the project root. Then you use the following command: 
```shell
cd <path-to-the-project-root>
docker compose up -d 
```
The result should be this: 

```shell
Container modal-docker-monorepo-tika-1    Started                                                                                                                                                                                   0.5s 
Container modal-docker-monorepo-db-1      Started                                                                                                                                                                                   0.6s 
Container modal-docker-monorepo-ollama-1  Started 
```

### Backend

Do the following steps to run the code locally. You will notice a download of spacy. This is a library we use
for doing NER analysis. You only have to do this **once**! 

Every time there is one or more new alembic migrations, you should also run alembic. That is the line with the 
DATABASE_URL. There is no harm in doing this every startup. Do mind that the line in the example below is making use
of a virtual environment!

```bash
cd backend  # from the project root you go to the backend folder
python3.12 -m venv venv    # In case there is no virtual environmnet yet
pip install -r requirements.txt
python -m spacy download nl_core_news_lg # Only needed the very first time you run the code!
DATABASE_URL=postgresql+psycopg://archiveuser:archivepass@localhost:5442/modaldb venv/bin/alembic upgrade head
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

### starting the agent
The agent should be starting up everything for our users, but that is
not something we want while developing. Therefore, we need to start the agent manually, with a development flag --dev. The
developer flag makes sure that the agent only starts the Flask filesystem bridge API on port 9090.  

From a different terminal window, starting from the project root: 

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

### Frontend

Requires Node.js to be installed, https://nodejs.org/en/download: 
```bash
cd frontend
npm install 
npm start
```