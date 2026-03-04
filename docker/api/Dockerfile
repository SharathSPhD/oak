FROM python:3.11-slim
WORKDIR /app

# System deps for asyncpg, healthcheck, git worktrees, and harness launch
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc libpq-dev curl git ca-certificates gnupg \
    && install -m 0755 -d /etc/apt/keyrings \
    && curl -fsSL https://download.docker.com/linux/debian/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg \
    && echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/debian bookworm stable" > /etc/apt/sources.list.d/docker.list \
    && apt-get update && apt-get install -y --no-install-recommends docker-ce-cli \
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
    "sqlalchemy[asyncio]>=2.0" \
    "python-multipart>=0.0.9"

# Allow git operations on mounted host repos
RUN git config --global --add safe.directory '*'

# Copy application source
COPY api/ api/
COPY memory/ memory/

EXPOSE 8000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
