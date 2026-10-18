# AI SRE Platform

A local learning project for a reliable, observable Ollama-backed FastAPI service with Prometheus and Grafana.

The API records request status, end-to-end latency, token counts, timeouts, and client cancellations. Prometheus scrapes those metrics; Grafana displays the provisioned dashboard and evaluates a provisioned timeout alert. A local FastAPI webhook receiver turns firing and resolved Grafana alerts into native macOS notifications.

## Documentation

- [Architecture and data flow](docs/architecture.md)
- [Quickstart](docs/quickstart.md)
- [Monitoring and hands-on validation](docs/observability.md)
- [Troubleshooting](docs/troubleshooting.md)
- [Reliability and observability phase summary](docs/reliability-observability-phase.md)

## Learning checkpoint

The FastAPI → Ollama reliability and observability phase is complete. The API
now has configurable downstream timeouts and endpoint selection, an in-memory
circuit breaker, per-process inference backpressure, Prometheus metrics, a
provisioned Grafana dashboard and alert, and authenticated webhook-to-macOS
notifications. The phase summary records the verified configuration, observed
validation evidence, remaining test gaps, and the next learning phase. The
next phase is agent engineering and Kubernetes operations—not further inference
performance tuning.

Grafana dashboard, datasource, alert rule, and contact-point definitions are in `observability/grafana/provisioning/`. Copy `observability/.env.example` to `observability/.env` and set `GRAFANA_WEBHOOK_TOKEN` before starting Grafana; the token is deliberately not in Git. See [monitoring and validation](docs/observability.md) for notifier startup and the reproducible alerting setup.

The Grafana administrator credentials in `observability/docker-compose.yml` are intended only for local development. Change them before exposing Grafana beyond your machine.
