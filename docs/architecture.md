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
```

FastAPI sends a non-streaming request to Ollama and returns the response, input/output token counts, and Ollama's reported total duration. Prometheus is outside that request path: it pulls `GET /metrics` every five seconds. Grafana queries Prometheus, not FastAPI.

## Metrics emitted by the API

| Metric | Labels | Meaning |
|---|---|---|
| `llm_requests_total` | `model`, `http_status` | Request outcomes: 200, 504, 499, and 500. |
| `llm_request_duration_seconds` | `model`, `http_status` | End-to-end API duration. |
| `llm_input_tokens_total` / `llm_output_tokens_total` | `model` | Token counts from successful Ollama responses. |
| `llm_timeouts_total` | `model` | HTTPX timeouts that became 504 responses. |
| `llm_cancellations_total` | `model` | Detected client disconnects or cancelled handlers. |

FastAPI counters reset on an API restart. Prometheus history can also be lost because the current Compose file has no Prometheus data volume.

## Timeout and cancellation paths

The API uses `httpx.AsyncClient(timeout=1)`. If Ollama is slower, FastAPI records 504 and increments `llm_timeouts_total`. While waiting, it checks for client disconnects; if one is found, it cancels the HTTPX task and records 499 plus `llm_cancellations_total`. A disconnected caller cannot receive that 499 response.
