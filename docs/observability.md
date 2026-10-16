# Monitoring and hands-on validation

After the [quickstart](quickstart.md), use this sequence to verify API metrics, Prometheus ingestion, and Grafana.

## Request counter

Capture the current counters:

```bash
curl -s http://localhost:8000/metrics | grep '^llm_requests_total'
```

Send three requests:

```bash
for i in 1 2 3; do
  curl -s -o /dev/null -w "request $i: HTTP %{http_code}\n" \
    -X POST http://localhost:8000/generate \
    -H 'Content-Type: application/json' \
    -d '{"prompt":"Explain Kubernetes in one sentence."}'
done
```

Inspect it again: the sum of `llm_requests_total` should rise by three, across the observed `http_status` labels. Wait five seconds, then run this in Prometheus:

```promql
sum(llm_requests_total)
```

The result should match the API's current counter sum. **Total LLM Requests** in Grafana uses the same metric; a scrape delay is normal.

## Latency

Latency includes the wait for Ollama. Use:

```promql
# Average duration over the last five minutes
sum(rate(llm_request_duration_seconds_sum[5m]))
/ sum(rate(llm_request_duration_seconds_count[5m]))
```

```promql
# P95 duration over the last five minutes
histogram_quantile(
  0.95,
  sum by (le) (rate(llm_request_duration_seconds_bucket[5m]))
)
```

Grafana has matching average- and P95-latency panels. Send a few requests before interpreting a five-minute rate.

## Timeouts and client cancellations

Ollama responses taking over one second produce HTTP 504 and increment both metrics:

```promql
sum(llm_requests_total{http_status="504"})
sum(llm_timeouts_total)
```

They should advance together. A specific prompt is not a guaranteed timeout test: model warm-up and host load matter.

To exercise the separate disconnect path, start a request with a very short client-side deadline:

```bash
curl --max-time 0.1 -X POST http://localhost:8000/generate \
  -H 'Content-Type: application/json' \
  -d '{"prompt":"Describe container orchestration in two paragraphs."}'
```

If FastAPI sees the disconnect before its upstream timeout, it records `llm_requests_total{http_status="499"}` and `llm_cancellations_total`. This is timing-sensitive; check the metric and API log, not curl output.

## Dashboard provisioning check

Grafana reads its datasource and dashboard-provider definitions from `observability/grafana/provisioning/`. The dashboard JSON uses datasource UID `prometheus`.

After changing any provisioned dashboard file, wait for the provider's configured refresh interval (10 seconds) or recreate Grafana:

```bash
docker compose -f observability/docker-compose.yml up -d --force-recreate grafana
```

Open the dashboard and select a model if needed. It covers totals, successes, timeouts, latency, status rates, and throughput.
