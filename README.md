# AI SRE Platform

A local learning project for observing an Ollama-backed FastAPI service with Prometheus and Grafana.

The API records request status, end-to-end latency, token counts, timeouts, and client cancellations. Prometheus scrapes those metrics; Grafana displays the provisioned dashboard and evaluates a provisioned timeout alert. A local FastAPI webhook receiver turns firing and resolved Grafana alerts into native macOS notifications.

## Documentation

- [Architecture and data flow](docs/architecture.md)
- [Quickstart](docs/quickstart.md)
- [Monitoring and hands-on validation](docs/observability.md)
- [Troubleshooting](docs/troubleshooting.md)

Grafana dashboard, datasource, alert rule, and contact-point definitions are in `observability/grafana/provisioning/`. Copy `observability/.env.example` to `observability/.env` and set `GRAFANA_WEBHOOK_TOKEN` before starting Grafana; the token is deliberately not in Git. See [monitoring and validation](docs/observability.md) for notifier startup and the reproducible alerting setup.

The Grafana administrator credentials in `observability/docker-compose.yml` are intended only for local development. Change them before exposing Grafana beyond your machine.
