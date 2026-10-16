# Troubleshooting

## Docker daemon is not running

If `docker compose` cannot connect to the Docker daemon, start Docker Desktop (or the Linux Docker service), wait for the engine, and retry. This is a container-runtime issue, not a Prometheus or Grafana configuration failure.

## HTTPX timeout versus client disconnect

These are distinct outcomes:

- **HTTP 504 / `llm_timeouts_total`**: Ollama did not complete before `httpx.AsyncClient(timeout=1)` expired.
- **499 / `llm_cancellations_total`**: the caller disconnected or ASGI cancelled the handler, so FastAPI cancels the upstream task. The caller cannot receive the response.

For frequent 504s, first check Ollama and the `qwen3:0.6b` model. The one-second threshold is deliberately strict; change it in `apps/api/main.py` only after choosing a service latency budget.

## Interpreting Ollama runner CPU use

A busy Ollama runner generally means local inference is using CPU, not that it has failed. Compare it with request latency, host load, and token rate. Some tools report CPU per logical core, so a multi-core process can exceed 100%. High latency with low runner activity suggests startup, connectivity, or another bottleneck.

## Prometheus target is `DOWN`

Open <http://localhost:9090/targets> and inspect `llm-api`.

1. Confirm `curl http://localhost:8000/metrics` returns Prometheus text.
2. Confirm the configured target is reachable from the Prometheus container. `host.docker.internal:8000` is for Docker Desktop.
3. On native Linux Docker, use a reachable host address or container-network service name, then restart Prometheus.
4. Wait one scrape interval.

FastAPI can still serve requests while Prometheus is `DOWN`; only collection stops.

## Grafana has no data or no dashboard

The dashboard needs a working Prometheus target and datasource `Prometheus` (UID `prometheus`).

1. Verify the datasource points to `http://prometheus:9090` from Grafana's container network.
2. Run `sum(llm_requests_total)` in Prometheus to separate ingestion from dashboard issues.
3. Check the provisioning mounts and files under `observability/grafana/provisioning/`.
4. After changing provisioning, recreate Grafana:

   ```bash
   docker compose -f observability/docker-compose.yml up -d --force-recreate grafana
   ```

The file provider refreshes every 10 seconds. A manual import can coexist with the managed dashboard; check **AI Observability**.
