# OAK Quick Start

Get OAK running in under 5 minutes.

## Prerequisites

- **Docker 24+** and Docker Compose v2
- **NVIDIA GPU + drivers** (DGX/workstation) or CPU-only (cloud mode)
- **8 GB free RAM** minimum (16 GB recommended)

## Option A: All-in-One Container (Easiest)

```bash
docker run -d --name oak-aio \
  --gpus all \
  -p 8501:3000 -p 8000:8000 -p 9000:9000 \
  ghcr.io/sharathsphd/oak-aio:latest
```

Open **http://localhost:8501** in your browser.

## Option B: Multi-Service Stack (Recommended)

```bash
git clone https://github.com/SharathSPhD/oak.git && cd oak

# Create your environment file
cp .env.example .env
# Edit .env — set OAK_ROOT and OAK_WORKSPACE_BASE to your paths

# Start the stack
bash scripts/bootstrap.sh dgx   # DGX/workstation with NVIDIA GPU
# OR
bash scripts/bootstrap.sh mini  # Mac Mini M4 / Apple Silicon
# OR
bash scripts/bootstrap.sh cloud # Cloud with vLLM backend
```

Wait for all services to come up (1-3 minutes on first run, as Ollama pulls models).

Open **http://localhost:8501** in your browser.

## Your First Problem

### Via the Web UI

1. Navigate to **http://localhost:8501**
2. Click **Submit Problem** from the dashboard
3. Enter a title (e.g. "Iris Classification") and description
4. Optionally upload a CSV data file
5. Check "Start pipeline automatically" and click **Submit**
6. Monitor progress on the Problem Detail page (Tasks, Logs, Files tabs)

### Via the API

```bash
# Create a problem
curl -X POST http://localhost:8000/api/problems \
  -H "Content-Type: application/json" \
  -d '{"title": "Sales Analysis", "description": "Analyze Q4 sales data"}'

# Start the pipeline (use the UUID from the response above)
curl -X POST http://localhost:8000/api/problems/<UUID>/start
```

## Verify the Stack

```bash
# API health check
curl http://localhost:8000/health | python3 -m json.tool

# Check Ollama models
curl http://localhost:9000/v1/models | python3 -m json.tool
```

## Common Issues

| Symptom | Fix |
|---------|-----|
| "Cannot connect to OAK API" | Run `docker ps` to confirm oak-api is running |
| Models not loading | Run `docker exec oak-ollama ollama pull qwen3-coder` |
| Permission denied on workspace | Ensure OAK_WORKSPACE_BASE directory exists and is writable |
| Port 8501 in use | Change the port mapping in docker-compose.yml |
| GPU not detected | Check `nvidia-smi` works, then restart Docker daemon |

## Next Steps

- Read the [User Manual](USER_MANUAL.md) for full documentation
- Browse the [API docs](http://localhost:8000/docs) (auto-generated OpenAPI)
- Check [Telemetry](http://localhost:8501/telemetry) for agent performance metrics
