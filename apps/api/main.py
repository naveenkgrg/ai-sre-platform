import asyncio
from contextlib import suppress
import json
import logging
import os
from time import perf_counter
from typing import Callable

import httpx
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel
from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest

# Create the FastAPI application.
# This is the service our client will call.
app = FastAPI()
logger = logging.getLogger(__name__)
MODEL_NAME = "qwen3:0.6b"
# Override this when Ollama runs on another host or behind a proxy.
OLLAMA_GENERATE_URL = os.getenv(
    "OLLAMA_GENERATE_URL", "http://localhost:11434/api/generate"
)


def positive_timeout_from_env(name: str, default: float) -> float:
    """Read a positive timeout value in seconds from the environment."""
    try:
        value = float(os.getenv(name, str(default)))
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a number of seconds") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be greater than zero")
    return value


def positive_integer_from_env(name: str, default: int) -> int:
    """Read a positive integer limit from the environment."""
    try:
        value = int(os.getenv(name, str(default)))
    except ValueError as exc:
        raise RuntimeError(f"{name} must be a positive integer") from exc
    if value <= 0:
        raise RuntimeError(f"{name} must be greater than zero")
    return value


MAX_CONCURRENT_INFERENCE = positive_integer_from_env(
    "MAX_CONCURRENT_INFERENCE", 3
)
INFERENCE_QUEUE_TIMEOUT_SECONDS = positive_timeout_from_env(
    "INFERENCE_QUEUE_TIMEOUT", 5
)
OLLAMA_CONNECT_TIMEOUT_SECONDS = positive_timeout_from_env(
    "OLLAMA_CONNECT_TIMEOUT_SECONDS", 2
)
OLLAMA_WRITE_TIMEOUT_SECONDS = positive_timeout_from_env(
    "OLLAMA_WRITE_TIMEOUT_SECONDS", 10
)
OLLAMA_READ_TIMEOUT_SECONDS = positive_timeout_from_env(
    "OLLAMA_READ_TIMEOUT_SECONDS", 60
)
OLLAMA_POOL_TIMEOUT_SECONDS = positive_timeout_from_env(
    "OLLAMA_POOL_TIMEOUT_SECONDS", 5
)
OLLAMA_REQUEST_TIMEOUT_SECONDS = positive_timeout_from_env(
    "OLLAMA_REQUEST_TIMEOUT_SECONDS", 90
)
# HTTPX enforces these limits independently. The endpoint also enforces the
# separate overall request deadline above while it polls for disconnects.
OLLAMA_HTTP_TIMEOUT = httpx.Timeout(
    connect=OLLAMA_CONNECT_TIMEOUT_SECONDS,
    read=OLLAMA_READ_TIMEOUT_SECONDS,
    write=OLLAMA_WRITE_TIMEOUT_SECONDS,
    pool=OLLAMA_POOL_TIMEOUT_SECONDS,
)


class CircuitBreaker:
    """Allow requests until repeated downstream failures require a cool-down."""

    # Numeric values match the Prometheus gauge exposed by this service.
    CLOSED = 0
    OPEN = 1
    HALF_OPEN = 2

    def __init__(
        self,
        failure_threshold: int = 5,
        recovery_timeout_seconds: float = 30,
        clock: Callable[[], float] = perf_counter,
        on_state_change: Callable[[int], None] | None = None,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout_seconds = recovery_timeout_seconds
        self.clock = clock
        self.on_state_change = on_state_change
        self.failure_count = 0
        self.opened_at: float | None = None
        self.state = self.CLOSED
        # A half-open breaker permits exactly one recovery probe at a time.
        self.half_open_request_in_flight = False
        # Requests complete concurrently, so every state transition is locked.
        self._lock = asyncio.Lock()

    def _set_state(self, state: int) -> None:
        self.state = state
        if self.on_state_change:
            self.on_state_change(state)

    async def allow_request(self) -> bool:
        """Return whether a request may reach Ollama."""
        async with self._lock:
            if self.state == self.OPEN:
                assert self.opened_at is not None
                # Reject requests during the cool-down period. Once it ends,
                # atomically move to half-open so only one caller can probe.
                if self.clock() - self.opened_at < self.recovery_timeout_seconds:
                    return False
                self._set_state(self.HALF_OPEN)

            if self.state == self.HALF_OPEN:
                if self.half_open_request_in_flight:
                    return False
                self.half_open_request_in_flight = True

            return True

    async def record_success(self) -> None:
        """Close the breaker after a successful recovery request."""
        async with self._lock:
            if self.state == self.HALF_OPEN:
                self.failure_count = 0
                self.opened_at = None
                self.half_open_request_in_flight = False
                self._set_state(self.CLOSED)
            elif self.state == self.CLOSED:
                self.failure_count = 0

    async def record_failure(self) -> None:
        """Open or reopen the breaker after a counted downstream failure."""
        async with self._lock:
            if self.state == self.HALF_OPEN:
                self.half_open_request_in_flight = False
                self.opened_at = self.clock()
                self._set_state(self.OPEN)
                return

            if self.state == self.CLOSED:
                self.failure_count += 1
                # Only failures received consecutively while closed open it.
                if self.failure_count >= self.failure_threshold:
                    self.opened_at = self.clock()
                    self._set_state(self.OPEN)

    async def release_half_open_request(self) -> None:
        """Release the probe slot without treating a cancelled request as failure."""
        async with self._lock:
            if self.state == self.HALF_OPEN:
                self.half_open_request_in_flight = False


LLM_REQUESTS = Counter(
    "llm_requests_total",
    "Total number of LLM generation requests.",
    ["model", "http_status"],
)
LLM_REQUEST_DURATION = Histogram(
    "llm_request_duration_seconds",
    "End-to-end duration of LLM generation requests.",
    ["model", "http_status"],
)
LLM_INPUT_TOKENS = Counter(
    "llm_input_tokens_total", "Total input tokens sent to the LLM.", ["model"]
)
LLM_OUTPUT_TOKENS = Counter(
    "llm_output_tokens_total", "Total tokens generated by the LLM.", ["model"]
)
LLM_TIMEOUTS = Counter("llm_timeouts_total", "Total LLM request timeouts.", ["model"])
LLM_CANCELLATIONS = Counter(
    "llm_cancellations_total", "Total LLM requests cancelled by clients.", ["model"]
)
LLM_DOWNSTREAM_FAILURES = Counter(
    "llm_downstream_failures_total",
    "Total downstream LLM failures counted by the circuit breaker.",
    ["model", "reason"],
)
LLM_CIRCUIT_BREAKER_STATE = Gauge(
    "llm_circuit_breaker_state",
    "Current LLM circuit breaker state: 0=closed, 1=open, 2=half-open.",
    ["model"],
)
LLM_ACTIVE_INFERENCE_REQUESTS = Gauge(
    "llm_active_inference_requests",
    "Number of Ollama inference requests currently holding a concurrency slot.",
    ["model"],
)
LLM_INFERENCE_QUEUE_TIMEOUTS = Counter(
    "llm_inference_queue_timeouts_total",
    "Total requests that timed out waiting for an inference slot.",
    ["model"],
)
# Publish the initial state, then update the gauge at each state transition.
LLM_CIRCUIT_BREAKER_STATE.labels(MODEL_NAME).set(CircuitBreaker.CLOSED)
LLM_ACTIVE_INFERENCE_REQUESTS.labels(MODEL_NAME).set(0)
circuit_breaker = CircuitBreaker(
    on_state_change=lambda state: LLM_CIRCUIT_BREAKER_STATE.labels(MODEL_NAME).set(
        state
    )
)
# A process-local backpressure limit for calls sent to Ollama. It is deliberately
# separate from HTTPX's connection-pool limit, which controls socket reuse.
inference_semaphore = asyncio.Semaphore(MAX_CONCURRENT_INFERENCE)


async def record_downstream_failure(reason: str) -> None:
    # The reason label is deliberately a fixed, low-cardinality set.
    LLM_DOWNSTREAM_FAILURES.labels(MODEL_NAME, reason).inc()
    await circuit_breaker.record_failure()


def log_generate_request(
    started_at: float,
    status_code: int,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
) -> None:
    duration_ms = round((perf_counter() - started_at) * 1000, 2)
    output_tokens_per_second = (
        round(output_tokens / (duration_ms / 1000), 2)
        if output_tokens is not None and duration_ms > 0
        else None
    )
    status_label = str(status_code)
    LLM_REQUESTS.labels(MODEL_NAME, status_label).inc()
    LLM_REQUEST_DURATION.labels(MODEL_NAME, status_label).observe(duration_ms / 1000)
    if input_tokens is not None:
        LLM_INPUT_TOKENS.labels(MODEL_NAME).inc(input_tokens)
    if output_tokens is not None:
        LLM_OUTPUT_TOKENS.labels(MODEL_NAME).inc(output_tokens)
    if status_code == 504:
        LLM_TIMEOUTS.labels(MODEL_NAME).inc()
    elif status_code == 499:
        LLM_CANCELLATIONS.labels(MODEL_NAME).inc()
    logger.info(
        json.dumps(
            {
                "event": "generate_request",
                "model": MODEL_NAME,
                "http_status": status_code,
                "duration_ms": duration_ms,
                "input_tokens": input_tokens,
                "output_tokens": output_tokens,
                "output_tokens_per_second": output_tokens_per_second,
            }
        )
    )


# Define the JSON request format.
# Example:
# {
#   "prompt": "Explain Kubernetes"
# }
class PromptRequest(BaseModel):
    prompt: str


# Create a POST API endpoint.
# Client will call:
# POST http://localhost:8000/generate
@app.post("/generate")
async def generate(req: PromptRequest, request: Request):
    started_at = perf_counter()
    # This is a strict wall-clock deadline, unlike HTTPX's phase timeouts.
    deadline = started_at + OLLAMA_REQUEST_TIMEOUT_SECONDS

    # Do not start an upstream request while the breaker is still open.
    if not await circuit_breaker.allow_request():
        log_generate_request(started_at, status_code=503)
        raise HTTPException(
            status_code=503,
            detail="LLM circuit breaker is open",
        )

    inference_slot_acquired = False
    ollama_request: asyncio.Task[httpx.Response] | None = None
    try:
        try:
            await asyncio.wait_for(
                inference_semaphore.acquire(), timeout=INFERENCE_QUEUE_TIMEOUT_SECONDS
            )
        except TimeoutError:
            # A full local queue is not an Ollama failure, but a half-open
            # breaker probe still needs to be released before we reject it.
            LLM_INFERENCE_QUEUE_TIMEOUTS.labels(MODEL_NAME).inc()
            await circuit_breaker.release_half_open_request()
            log_generate_request(started_at, status_code=503)
            raise HTTPException(
                status_code=503,
                detail="LLM inference queue is full",
            )

        inference_slot_acquired = True
        LLM_ACTIVE_INFERENCE_REQUESTS.labels(MODEL_NAME).inc()

        # Call the Ollama API running locally on port 11434.
        # FastAPI acts as a wrapper/service layer around the LLM.
        async with httpx.AsyncClient(timeout=OLLAMA_HTTP_TIMEOUT) as client:
            ollama_request = asyncio.create_task(
                client.post(
                    OLLAMA_GENERATE_URL,
                    json={
                        # Local model we downloaded earlier.
                        "model": MODEL_NAME,

                        # Send the user prompt to the model.
                        "prompt": req.prompt,

                        # Return the full response in one result.
                        # Later we will change this to streaming.
                        "stream": False,

                        # Disable extra reasoning output for this experiment.
                        "think": False,
                    },
                )
            )

            while not ollama_request.done():
                remaining = deadline - perf_counter()
                if remaining <= 0:
                    # Cancel first so leaving the handler also closes the
                    # in-flight connection to Ollama.
                    ollama_request.cancel()
                    with suppress(asyncio.CancelledError):
                        await ollama_request
                    raise TimeoutError("LLM request exceeded its overall timeout")

                await asyncio.wait({ollama_request}, timeout=min(0.1, remaining))
                if await request.is_disconnected():
                    # A frontend cancellation is not an Ollama failure, so
                    # release a possible half-open probe without counting it.
                    ollama_request.cancel()
                    with suppress(asyncio.CancelledError):
                        await ollama_request
                    await circuit_breaker.release_half_open_request()
                    log_generate_request(started_at, status_code=499)
                    raise HTTPException(
                        status_code=499,
                        detail="Client disconnected before LLM inference completed",
                    )

            ollama_response = await ollama_request
    except asyncio.CancelledError:
        # The ASGI server may cancel this handler while it is queued or while
        # Ollama is running. In either case, release all local and breaker
        # state without counting the cancellation as a downstream failure.
        if ollama_request is not None:
            ollama_request.cancel()
            with suppress(asyncio.CancelledError):
                await ollama_request
        await circuit_breaker.release_half_open_request()
        log_generate_request(started_at, status_code=499)
        raise
    except (httpx.TimeoutException, TimeoutError):
        # HTTPX phase timeouts and the overall deadline both affect dependency
        # availability and therefore count toward opening the breaker.
        await record_downstream_failure("timeout")
        log_generate_request(started_at, status_code=504)
        raise HTTPException(
            status_code=504,
            detail="LLM inference timed out",
        )
    except httpx.NetworkError:
        # Connection and transport failures are also counted downstream errors.
        await record_downstream_failure("connection_error")
        log_generate_request(started_at, status_code=502)
        raise HTTPException(
            status_code=502,
            detail="Unable to reach LLM service",
        )
    except HTTPException:
        raise
    except Exception:
        await circuit_breaker.release_half_open_request()
        log_generate_request(started_at, status_code=500)
        raise
    finally:
        if inference_slot_acquired:
            inference_semaphore.release()
            LLM_ACTIVE_INFERENCE_REQUESTS.labels(MODEL_NAME).dec()

    if 500 <= ollama_response.status_code < 600:
        # Ollama reached us but failed server-side, so count it as unhealthy.
        await record_downstream_failure("http_5xx")
        log_generate_request(started_at, status_code=502)
        raise HTTPException(
            status_code=502,
            detail="LLM service returned an error",
        )

    # Any non-5xx response proves Ollama is reachable. In particular, a 4xx
    # must not count as a breaker failure and can close a half-open probe.
    await circuit_breaker.record_success()

    try:
        # Convert Ollama's JSON response into a Python dictionary.
        data = ollama_response.json()

        # Return only the fields we care about.
        # FastAPI automatically converts this dictionary back to JSON.
        response = {
            "response": data["response"],
            "input_tokens": data["prompt_eval_count"],
            "output_tokens": data["eval_count"],
            "total_duration": data["total_duration"],
        }
    except Exception:
        await circuit_breaker.release_half_open_request()
        log_generate_request(started_at, status_code=500)
        raise
    log_generate_request(
        started_at,
        status_code=200,
        input_tokens=response["input_tokens"],
        output_tokens=response["output_tokens"],
    )
    return response


@app.get("/metrics", include_in_schema=False)
def metrics():
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/health")
def health():
    return {"status": "ok"}
