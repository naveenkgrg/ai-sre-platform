# Architecture and monitoring flow

```text
client --POST /generate--> FastAPI --HTTP--> Ollama (qwen3:0.6b)
                              |                  |
                              |<--response--------|
                              v
                         /metrics
                              ^
                              | scrape every 5 s
                         Prometheus <---- Grafana dashboard queries
                              ^
                              | alert rule: 5m timeout percentage
                              v
                         Grafana Alerting --authenticated webhook-->
                         FastAPI notifier --osascript--> macOS notification
```

FastAPI sends a non-streaming request to Ollama and returns the response, input/output token counts, and Ollama's reported total duration. Prometheus is outside that request path: it pulls `GET /metrics` every five seconds. Grafana queries Prometheus, not FastAPI.

## Metrics emitted by the API

| Metric | Labels | Meaning |
|---|---|---|
| `llm_requests_total` | `model`, `http_status` | Request outcomes: 200, 499, 500, 502, 503, and 504. |
| `llm_request_duration_seconds` | `model`, `http_status` | End-to-end API duration. |
| `llm_input_tokens_total` / `llm_output_tokens_total` | `model` | Token counts from successful Ollama responses. |
| `llm_timeouts_total` | `model` | HTTPX phase timeouts and overall request deadlines that became 504 responses. |
| `llm_cancellations_total` | `model` | Detected client disconnects or cancelled handlers. |
| `llm_downstream_failures_total` | `model`, `reason` | Counted breaker failures: `http_5xx`, `connection_error`, or `timeout`. |
| `llm_circuit_breaker_state` | `model` | Current breaker state: 0 closed, 1 open, 2 half-open. |
| `llm_active_inference_requests` | `model` | Ollama requests currently holding an inference slot. |
| `llm_inference_queue_timeouts_total` | `model` | Requests that timed out waiting for an inference slot. |

FastAPI counters reset on an API restart. Prometheus history can also be lost because the current Compose file has no Prometheus data volume.

## Timeout and cancellation paths

The API configures HTTPX phase timeouts from environment variables: connection 2 seconds, write 10 seconds, read 60 seconds, and pool 5 seconds by default. It also enforces a separate 90-second end-to-end request deadline. `OLLAMA_CONNECT_TIMEOUT_SECONDS`, `OLLAMA_WRITE_TIMEOUT_SECONDS`, `OLLAMA_READ_TIMEOUT_SECONDS`, `OLLAMA_POOL_TIMEOUT_SECONDS`, and `OLLAMA_REQUEST_TIMEOUT_SECONDS` override these positive-second defaults. If Ollama exceeds either the HTTPX phase limit or overall deadline, FastAPI records 504 and increments `llm_timeouts_total`. While waiting, it checks for client disconnects; if one is found, it cancels the HTTPX task and records 499 plus `llm_cancellations_total`. A disconnected caller cannot receive that 499 response.

## Inference queue backpressure

Each API process limits calls that reach Ollama with an `asyncio.Semaphore`.
`MAX_CONCURRENT_INFERENCE` is a positive integer and defaults to 3. Callers
wait up to the positive-second `INFERENCE_QUEUE_TIMEOUT` (default 5) for a
slot. A caller that cannot obtain one receives HTTP 503, increments
`llm_inference_queue_timeouts_total`, and does not count as a circuit-breaker
failure. `llm_active_inference_requests` reports the number of currently held
slots.

## Circuit breaker

Five consecutive counted downstream failures open the in-process circuit breaker for 30 seconds. Counted failures are Ollama HTTP 5xx responses, network connection errors, and timeouts. Downstream HTTP 4xx responses and frontend cancellations do not count as breaker failures.

While open, `/generate` returns HTTP 503 without contacting Ollama. After 30 seconds, the breaker becomes half-open and permits exactly one recovery request. A successful response closes it; a counted failure reopens it for another 30 seconds. The breaker state is exported as `llm_circuit_breaker_state`.

The notifier is a separate host process at `http://host.docker.internal:8001/notify`. Grafana reaches it from its Docker container, authenticating with `Authorization: Bearer <token>`. The notifier accepts only firing and resolved alert instances and invokes macOS `osascript` to display them.
