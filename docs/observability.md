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

Ollama requests that exceed an HTTPX phase timeout or the configured overall request deadline produce HTTP 504 and increment both metrics. The defaults are a 60-second read timeout and 90-second overall deadline:

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

## Inference queue backpressure

Each API process permits three concurrent Ollama requests by default. Configure
`MAX_CONCURRENT_INFERENCE` and `INFERENCE_QUEUE_TIMEOUT` (seconds) to suit the
host. A request that cannot get a slot within the queue timeout receives HTTP
503 and increments `llm_inference_queue_timeouts_total`; current slot use is
reported by `llm_active_inference_requests`.

## Circuit breaker

Five consecutive downstream failures open the circuit breaker. The counted categories are visible in Prometheus:

```promql
sum by (reason) (llm_downstream_failures_total)
```

When open, `/generate` returns HTTP 503 immediately and does not call Ollama. Check its state with:

```promql
llm_circuit_breaker_state
```

`0` is closed, `1` is open, and `2` is half-open. The breaker stays open for 30 seconds, then permits one probe request. A successful probe closes it; a timeout, connection error, or downstream HTTP 5xx reopens it. Frontend cancellations and downstream HTTP 4xx responses do not contribute to the failure count.

## Dashboard provisioning check

Grafana reads its datasource and dashboard-provider definitions from `observability/grafana/provisioning/`. The dashboard JSON uses datasource UID `prometheus`.

After changing any provisioned dashboard file, wait for the provider's configured refresh interval (10 seconds) or recreate Grafana:

```bash
docker compose -f observability/docker-compose.yml up -d --force-recreate grafana
```

Open the dashboard and select a model if needed. It covers totals, successes, timeouts, latency, status rates, and throughput.

## Reproducible Grafana alerting and macOS notifications

`observability/grafana/provisioning/alerting/llm-alerts.yml` is the Monitoring-as-Code definition for the already-tested alert:

- folder **AI Observability**, group **llm-monitoring**;
- rule UID `dg1g374u3fqpsf`, evaluated every minute and pending for one minute;
- a five-minute timeout percentage (`504` requests / all requests), gated by at least five requests, then firing only above 20%;
- direct rule-level route to contact point **Mac Desktop Notifications** (receiver UID `cg1g8mwzdtssge`), which POSTs to `http://host.docker.internal:8001/notify` and includes resolved alerts.

The stable UIDs reproduce the existing UI-created objects when the current `grafana-data` volume is reused, rather than creating a second alert or contact point. The direct receiver is intentional: Grafana bypasses the global notification-policy tree for this alert, so no broad default route is changed.

### Supply the secret without committing it

Grafana cannot recover an existing contact-point credential in plaintext from its encrypted database. Use one newly generated token for both sides instead:

```bash
cp observability/.env.example observability/.env
# Put the output of this command after GRAFANA_WEBHOOK_TOKEN= in observability/.env
openssl rand -hex 32

set -a
source observability/.env
set +a
WEBHOOK_SECRET="$GRAFANA_WEBHOOK_TOKEN" \
  python -m uvicorn notifications.macos_notifier:app --host 0.0.0.0 --port 8001
```

`observability/.env` is ignored by Git and is injected only into the Grafana container. The provisioning file references `$GRAFANA_WEBHOOK_TOKEN` through the webhook's `secure_settings.authorization_credentials`; Grafana recognizes that setting as sensitive and encrypts it in its own database without placing it in the repository. Then apply the definitions without deleting the persistent volume:

```bash
docker compose -f observability/docker-compose.yml up -d --force-recreate grafana
```

If the UI-created contact point used a token that is no longer known, this deliberate token rotation is required. Do not copy Grafana's encrypted credential into a file and do not add it to source control.

### Verify the complete path

1. Confirm the notifier is listening: `curl http://localhost:8001/docs` should return the FastAPI docs page.
2. In Grafana, open **Alerting → Alert rules → AI Observability** and verify one **High LLM Timeout Rate** rule with the UID above. Its state can initially be `Normal (MissingSeries)` until Prometheus has samples; that is expected and is not a firing alert.
3. Generate enough requests to satisfy the five-request guard, then induce/observe 504s. The rule is evaluated each minute and must remain above 20% for the one-minute pending period before it fires.
4. Verify a macOS notification on firing and another on resolution. macOS may require enabling notifications for the terminal, Python, or automation host in **System Settings → Notifications**.

Use Grafana's contact-point test only after the notifier has been started with the same token. A `2xx` response means Grafana delivered the webhook; the native notification additionally depends on macOS permission.
