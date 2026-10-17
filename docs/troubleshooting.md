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

## Grafana webhook returns HTTP 401

The notifier requires exactly `Authorization: Bearer <token>`. In the Grafana webhook contact point, configure **Authentication scheme** as `Bearer` and put only the token value in **Credentials**—do not put `Bearer ` in the credentials field. The provisioned equivalent is `authorization_scheme: Bearer` plus `secureSettings.authorization_credentials: $GRAFANA_WEBHOOK_TOKEN`.

The notifier's `WEBHOOK_SECRET` and Grafana's `GRAFANA_WEBHOOK_TOKEN` must be the same value. In the provisioning file, Grafana reads it from `secure_settings.authorization_credentials`. Reloading `observability/.env` does not change a running process; restart both the notifier and the Grafana container after rotating the token.

## Grafana cannot reach the macOS notifier

`localhost` inside Grafana's container is the container itself. On Docker Desktop for macOS, the provisioned contact point uses `http://host.docker.internal:8001/notify` to reach the notifier on the host. Confirm the notifier is listening on `0.0.0.0:8001`, not only a different loopback or port.

On native Linux Docker, `host.docker.internal` may not exist. Use a host address reachable from the Grafana container (or add Docker's host-gateway mapping) and update the contact-point URL deliberately; do not change the Mac-specific provisioning value by accident.

## Alert remains Normal (MissingSeries)

This state means the rule does not yet have a series to evaluate, commonly because Prometheus has not scraped the API or there have been no requests. Check the `llm-api` target, send requests, then wait for the next scrape and one-minute rule evaluation. It is not equivalent to a firing timeout alert.

## macOS notification does not appear

First use Grafana's contact-point test and confirm the notifier returns `{"status":"ok"}`. Then check **System Settings → Notifications** and allow notifications for the terminal, Python, or automation process that ran `osascript`. Start the notifier from the logged-in desktop session; a background or remote session may not be allowed to present a native notification.
