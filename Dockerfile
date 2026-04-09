FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
# Stub so setuptools registers 'chalk' during editable install
RUN mkdir -p chalk && touch chalk/__init__.py
RUN pip install -e ".[dev]"
COPY . .
CMD sh -c "uvicorn chalk.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"
