# AI SRE Platform

A local learning project for observing an Ollama-backed FastAPI service with Prometheus and Grafana.

The API records request status, end-to-end latency, token counts, timeouts, and client cancellations. Prometheus scrapes those metrics; Grafana displays the provisioned dashboard.

## Documentation

- [Architecture and data flow](docs/architecture.md)
- [Quickstart](docs/quickstart.md)
- [Monitoring and hands-on validation](docs/observability.md)
- [Troubleshooting](docs/troubleshooting.md)

The Grafana administrator credentials in `observability/docker-compose.yml` are intended only for local development. Change them before exposing Grafana beyond your machine.
