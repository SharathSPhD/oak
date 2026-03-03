FROM python:3.11-slim
WORKDIR /app

# System deps for asyncpg (C extension) and healthcheck curl
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
RUN pip install --no-cache-dir \
    "fastapi>=0.111" \
    "uvicorn[standard]>=0.29" \
    "pydantic>=2.7" \
    "pydantic-settings>=2.3" \
    "asyncpg>=0.29" \
    "psycopg2-binary>=2.9" \
    "pgvector>=0.3" \
    "redis>=5.0" \
    "httpx>=0.27" \
    "websockets>=12" \
    "sqlalchemy[asyncio]>=2.0"

# Copy application source
COPY api/ api/
COPY memory/ memory/

EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
