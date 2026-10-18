# Reliability and observability phase summary

## Outcome

This learning phase is complete: the local FastAPI service has bounded calls to
Ollama, process-local backpressure, a process-local circuit breaker, and an
observable alert path from Prometheus through Grafana to macOS notifications.
This document is a checkpoint, not a replacement for the [quickstart](quickstart.md),
[architecture](architecture.md), or [observability guide](observability.md).

## Hands-on checkpoints

Use these immutable commit links to follow the project in order. Check out a
checkpoint with `git switch --detach <commit-id>`, complete or inspect that
step, then move to the next one. Return to the current branch with
`git switch main`.

| Checkpoint | What you will have | Commit |
|---|---|---|
| 1. Local API | Minimal FastAPI wrapper around Ollama | [`7827a69`](https://github.com/naveenkgrg/ai-sre-platform/commit/7827a69c0555f1a8f98f65dc9672a799ced9bdc4) |
| 2. Inference timeouts | HTTP timeout handling | [`0df6295`](https://github.com/naveenkgrg/ai-sre-platform/commit/0df6295b04e8bed3594425c459855b456b4db8e2) |
| 3. Client cancellation | Upstream cancellation after client disconnect | [`fccbf63`](https://github.com/naveenkgrg/ai-sre-platform/commit/fccbf63b2de3fb01174d1ecd898a9072e3a1074d) |
| 4. Request logging | Structured request logs | [`8375db7`](https://github.com/naveenkgrg/ai-sre-platform/commit/8375db725e4a02777b642bd753ddc75e5c7a5d4d) |
| 5. API metrics | Prometheus metrics endpoint and instrumentation | [`90229c3`](https://github.com/naveenkgrg/ai-sre-platform/commit/90229c3218d743060980c53d052152bab563cdba) |
| 6. Monitoring stack | Prometheus and Grafana local stack | [`24637c5`](https://github.com/naveenkgrg/ai-sre-platform/commit/24637c5e3da54473a66e9ca10c067dd615498984) |
| 7. Alerting | Grafana timeout alert and macOS notifications | [`82c0a2e`](https://github.com/naveenkgrg/ai-sre-platform/commit/82c0a2ee6c2da9b1c4b4293ab5267b38e60b0746) |
| 8. Reliability controls | Circuit breaker, queue backpressure, tests, and final phase docs | [`b1dab1c`](https://github.com/naveenkgrg/ai-sre-platform/commit/b1dab1c65f83418ceed4f2f4e7447ddfa414f5df) |

## Verified implementation and configuration

The API reads `OLLAMA_GENERATE_URL`, defaulting to
`http://localhost:11434/api/generate`, so Ollama can run on a different host or
behind a proxy. The following environment variables configure the request
budget and local inference backpressure:

| Setting | Default | Purpose |
|---|---:|---|
| `OLLAMA_CONNECT_TIMEOUT_SECONDS` | 2 | Connect phase limit |
| `OLLAMA_WRITE_TIMEOUT_SECONDS` | 10 | Request-write phase limit |
| `OLLAMA_READ_TIMEOUT_SECONDS` | 60 | Response-read phase limit |
| `OLLAMA_POOL_TIMEOUT_SECONDS` | 5 | HTTP connection-pool wait limit |
| `OLLAMA_REQUEST_TIMEOUT_SECONDS` | 90 | End-to-end handler deadline |
| `MAX_CONCURRENT_INFERENCE` | 3 | Positive integer: per-process concurrent Ollama calls |
| `INFERENCE_QUEUE_TIMEOUT` | 5 | Seconds a request may wait for an inference slot |

The `CircuitBreaker` is in memory for each API process. Five consecutive
counted downstream failures open it for 30 seconds. Counted failures are
downstream HTTP 5xx responses, network errors, and timeouts. While open,
`/generate` returns HTTP 503 without calling Ollama. At cooldown expiry it
allows exactly one half-open probe; success closes the breaker and a counted
failure reopens it. Client cancellations and downstream HTTP 4xx responses do
not count as failures. Restarting the API resets this state.

The inference semaphore limits calls that reach Ollama. A caller that cannot
obtain a slot before `INFERENCE_QUEUE_TIMEOUT` receives HTTP 503; that queue
timeout does not count as a downstream breaker failure.

Prometheus scrapes `/metrics` every five seconds. The API exposes request,
latency, token, timeout, cancellation, downstream-failure, circuit-breaker,
active-inference, and inference-queue-timeout metrics. Grafana provisions the
Prometheus datasource, dashboard, and timeout-rate alert. The alert posts to
the local notifier at `host.docker.internal:8001/notify`; Grafana authenticates
with a Bearer token supplied through the ignored `observability/.env` file, and
the notifier displays firing and resolved alerts through macOS `osascript`.
Never commit that token.

## Observed validation evidence

The following runs were observed during this phase:

- Five failed downstream requests returned HTTP 502, opened the breaker, and
  produced breaker-state metric value `1`.
- After the cooldown, a failed half-open probe returned HTTP 502; the next
  request was rejected with HTTP 503 in about `0.000667s`.
- A successful inference returned HTTP 200 after an API restart. This confirms
  the success path, but **does not prove a half-open-to-closed recovery**,
  because the restart reset the in-memory breaker.
- With `MAX_CONCURRENT_INFERENCE=1` and `INFERENCE_QUEUE_TIMEOUT=2`, one
  request returned HTTP 200 in `6.195s`; four returned HTTP 503 at about
  `2.03s`. Afterwards, `llm_active_inference_requests` was `0` and
  `llm_inference_queue_timeouts_total` was `4`.

The focused automated checks currently pass: circuit-breaker state transitions,
single half-open admission, semaphore limiting, queue rejection, and cleanup
of a cancelled request's slot.

## Explicit remaining validation gaps

- **Successful half-open recovery remains unverified in a live API run.** Let
  the cooldown finish, restore Ollama without restarting FastAPI, send the
  single probe, and verify the state metric returns from `2` to `0`.
- **Cancellation under concurrent live load remains unverified.** Test a
  disconnect while another request is queued or running, then confirm both the
  active gauge and semaphore capacity recover without an unintended breaker
  failure.

## Next learning phase

Build forward from this stable service foundation:

1. Agent harness fundamentals: goals, context, model calls, tool selection,
   execution loops, and guardrails.
2. Local AI coding-agent environments: instructions, skills, MCP servers and
   clients, tools, permissions, and workspace boundaries.
3. Asynchronous agent jobs: durable job state, retries, handoff, status, and
   cancellation.
4. Kubernetes deployment of agent services and their dependencies.
5. Production agent observability and security: tracing, audit events,
   authorization, secret handling, and tool-risk controls.
6. An end-to-end Kubernetes troubleshooting agent that uses safe, scoped tools
   and produces observable operational outcomes.

Do not schedule more inference tuning unless a concrete product or operational
requirement makes it necessary.
