# Archive Analysis App

A hybrid Docker + native agent application for ingesting, analyzing, and browsing file archives using Apache Tika, NER, and other NLP tools.

## Features

- Upload and ingest file archives for automated analysis
- Named entity recognition (NER) and NLP-based content analysis
- OCR support for image-based documents
- Category and file type filtering
- Browser-based interface for browsing and reviewing results

## Prerequisites

- [Docker Desktop](https://www.docker.com/products/docker-desktop/)
- [Python 3.12](https://www.python.org/downloads/)
- [Node.js](https://nodejs.org/en/download)

## Installation

Clone the repository:

```bash
git clone <repository-url>
cd modal-docker-monorepo
```

Refer to the [Developer's Guide](docs/developers-guide.md) for full setup instructions for the agent, backend, and frontend.

## Usage

Start the application using the agent with the `--dev` flag for local development:

```bash
cd agent
source venv/bin/activate
python agent.py --dev
```

Open your browser and navigate to `http://localhost:4210` (or the configured port).

## Configuration

The backend uses a `.env` file for local development. Copy the example and adjust as needed:

```bash
cp backend/.env.example backend/.env
```

See the [Developer's Guide](docs/developers-guide.md) for details on environment variables and database configuration.

## Architecture

For an overview of the system architecture, see [Architecture](docs/architecture.md).

## Contributing

See the [Developer's Guide](docs/developers-guide.md) for branching conventions, local setup, and contribution guidelines.

## License

Private — all rights reserved.
