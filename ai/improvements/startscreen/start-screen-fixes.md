# Use Case

Fix three issues with the backend Docker container startup:
1. Suppress the pip "Running as root" warning during spacy model check
2. Bake the spacy NLP model into the Docker image so it's not downloaded on every first container start (568 MB download)
3. Bake the nltk stopwords data into the Docker image so it's not downloaded on every first container start

# Current Behavior

When the backend container starts for the first time, `start.sh` runs:
```
python -m spacy download nl_core_news_lg --skip-existing
```

This triggers a 568 MB download on first start, making the backend slow to become healthy. It also produces this warning:
```
WARNING: Running pip as the 'root' user can result in broken permissions...
```

Additionally, somewhere in the application startup, nltk downloads stopwords:
```
[nltk_data] Downloading package stopwords to /root/nltk_data...
```

# Expected Behavior

- The spacy model and nltk data are pre-installed in the Docker image (no downloads at container startup)
- `start.sh` still checks the model exists (safety net) but without the root user warning
- Container startup is fast — just migrations, model check, and uvicorn

# Changes Required

## Change 1: Dockerfile — bake models into image

**File:** `backend/Dockerfile`

Add these lines after `pip install -r requirements.txt`:

```dockerfile
RUN pip install --no-cache-dir -r requirements.txt
RUN python -m spacy download nl_core_news_lg
RUN python -c "import nltk; nltk.download('stopwords')"
```

This bakes both the spacy model (~568 MB) and nltk stopwords into the Docker image layer. The image will be larger, but container startups will be instant.

## Change 2: start.sh — suppress root warning

**File:** `backend/start.sh`

Change the spacy download command to suppress the pip root user warning:

```bash
echo "Checking NLP model..."
python -m spacy download nl_core_news_lg --skip-existing --root-user-action=ignore
```

This line is now just a safety net — the model should already be in the image from the Dockerfile. The `--root-user-action=ignore` flag suppresses the root user warning since running as root inside a Docker container is expected.

## Change 3: Application code — prevent nltk runtime download

Find where nltk stopwords are downloaded at application startup (likely in an `__init__.py` or at module level in the NER code). The download call probably looks like:

```python
import nltk
nltk.download('stopwords')
```

This should be wrapped to only download if not already present:

```python
import nltk
try:
    nltk.data.find('corpora/stopwords')
except LookupError:
    nltk.download('stopwords', quiet=True)
```

Or better: since it's baked into the Docker image via the Dockerfile, just remove the runtime download entirely and rely on the import failing loudly if the data is missing. The Dockerfile guarantees it's there.

# Testing Notes

- Build the Docker image locally and verify the spacy model is included: `docker run --rm archive-app-backend python -c "import spacy; spacy.load('nl_core_news_lg')"`
- Build the Docker image locally and verify nltk stopwords are included: `docker run --rm archive-app-backend python -c "from nltk.corpus import stopwords; print(stopwords.words('dutch')[:5])"`
- Start the container and verify no download messages appear in the logs
- Verify no pip root user warnings appear
- Verify the backend still becomes healthy within the expected timeout