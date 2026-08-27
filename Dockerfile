FROM python:3.11-slim AS dependencies

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY pyproject.toml ./
COPY src ./src
RUN pip install --upgrade pip && pip install ".[ml,streaming,dashboard]"

FROM dependencies AS test
COPY . .
RUN pip install ".[dev]"
CMD ["python", "-m", "pytest"]

FROM dependencies AS runtime
COPY . .
RUN useradd --create-home --uid 10001 fraud && chown -R fraud:fraud /app
USER fraud
EXPOSE 8000
CMD ["uvicorn", "apps.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
