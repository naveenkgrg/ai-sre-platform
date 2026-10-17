# Quickstart

Requires macOS or Linux, Python 3.10+, Docker Compose, and Ollama. Prometheus targets `host.docker.internal:8000`, which Docker Desktop provides on macOS and Windows. Native Linux Docker users must use another address reachable from the Prometheus container.

## 1. Prepare Ollama and the API

Start Ollama if needed, then download the model used by the API:

```bash
ollama pull qwen3:0.6b
```

From the repository root, create an environment, install dependencies, and start FastAPI:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install fastapi "uvicorn[standard]" httpx prometheus-client
python -m uvicorn apps.api.main:app --reload --port 8000
```

In a second terminal, confirm the service is reachable:

```bash
curl http://localhost:8000/health
curl -X POST http://localhost:8000/generate \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Explain Kubernetes in one sentence."}'
```

The generate request returns `response`, token counts, and `total_duration`. A 504 means Ollama exceeded the current one-second API timeout; see [troubleshooting](troubleshooting.md).

## 2. Configure alert notifications

The macOS notifier and Grafana must share one token. Create a local, ignored configuration file and choose a new token:

```bash
cp observability/.env.example observability/.env
# Edit observability/.env and replace the placeholder with the output of:
openssl rand -hex 32
```

In a separate terminal, load that token and start the notifier:

```bash
set -a
source observability/.env
set +a
WEBHOOK_SECRET="$GRAFANA_WEBHOOK_TOKEN" \
  python -m uvicorn notifications.macos_notifier:app --host 0.0.0.0 --port 8001
```

The notifier must run in the logged-in macOS desktop session so `osascript` can show notifications. The first notification may prompt for permission; allow it in **System Settings → Notifications** for the process that displays the alert.

## 3. Start the monitoring stack

From the repository root:

```bash
docker compose -f observability/docker-compose.yml up -d
```

Open:

- Prometheus: <http://localhost:9090/targets>
- Grafana: <http://localhost:3000>

For a **new Grafana data volume**, the local credentials are `admin` / `admin`. Existing `grafana-data` volumes preserve their current password. After up to five seconds, Prometheus's `llm-api` target should be `UP`.

Grafana provisions the Prometheus datasource, **LLM Observability | Ollama + FastAPI** dashboard, and **High LLM Timeout Rate** alert from `observability/grafana/`. Find the dashboard and alert folder in **AI Observability**; no manual import is needed. The alert evaluates every minute and sends to **Mac Desktop Notifications** directly when the five-minute timeout percentage is over 20% with at least five requests.

To stop the monitoring containers without deleting the Grafana volume:

```bash
docker compose -f observability/docker-compose.yml down
```
