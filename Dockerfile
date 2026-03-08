FROM python:3.11-slim
WORKDIR /app
COPY pyproject.toml .
RUN pip install -e ".[dev]"
COPY . .
CMD sh -c "uvicorn chalk.api.main:app --host 0.0.0.0 --port ${PORT:-8000}"
