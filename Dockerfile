FROM python:3.11.15-slim

WORKDIR /app

# Install pinned dependencies first so this layer caches until the lockfile changes.
# requirements.txt is generated from pyproject.toml — see CONTRIBUTING.md to update it.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
RUN pip install --no-cache-dir --no-deps -e .

# Run as a non-root user. The image is read-only at runtime except NBA_API_CACHE_DIR,
# which defaults to .cache/ under /app (ephemeral on Railway).
RUN useradd --create-home --uid 1000 chalk && chown -R chalk:chalk /app
USER chalk

CMD sh -c "uvicorn chalk.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"
