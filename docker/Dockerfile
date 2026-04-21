FROM python:3.11-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml ./
COPY uv.lock ./

RUN pip install --no-cache-dir uv && uv pip install --system --no-cache -r <(uv pip compile pyproject.toml --quiet) || \
    pip install --no-cache-dir \
        "aiohttp>=3.13.5" "apscheduler>=3.10.4" "google-adk>=2.0.0a2,<3" \
        "httpx>=0.27.2" "nest-asyncio>=1.6.0" "psutil>=6.1.0" \
        "psycopg2-binary>=2.9.11" "pydantic>=2.13.2" "pydantic-settings>=2.13.1" \
        "python-dotenv>=1.2.2" "rich>=13.9.2" "sqlalchemy>=2.0.49" \
        "textual>=0.86.0" "websockets>=15.0.1"

COPY src/ ./src/

CMD ["python", "-m", "src.main", "--mode", "scheduler"]
