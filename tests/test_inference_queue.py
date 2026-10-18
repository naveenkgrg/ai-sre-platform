import asyncio
import unittest

from fastapi import HTTPException

from apps.api import main


class ConnectedRequest:
    async def is_disconnected(self) -> bool:
        return False


class FakeResponse:
    status_code = 200

    def json(self):
        return {
            "response": "ok",
            "prompt_eval_count": 1,
            "eval_count": 1,
            "total_duration": 1,
        }


class BlockingOllamaClient:
    def __init__(self, started, release, state):
        self.started = started
        self.release = release
        self.state = state

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc, traceback):
        return False

    async def post(self, *args, **kwargs):
        self.state["active"] += 1
        self.state["max_active"] = max(
            self.state["max_active"], self.state["active"]
        )
        self.started.set()
        try:
            await self.release.wait()
        finally:
            self.state["active"] -= 1
        return FakeResponse()


class InferenceQueueTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.original_client = main.httpx.AsyncClient
        self.original_breaker = main.circuit_breaker
        self.original_semaphore = main.inference_semaphore
        self.original_queue_timeout = main.INFERENCE_QUEUE_TIMEOUT_SECONDS
        main.circuit_breaker = main.CircuitBreaker()
        main.inference_semaphore = asyncio.Semaphore(1)

        self.started = asyncio.Event()
        self.release = asyncio.Event()
        self.state = {"active": 0, "max_active": 0}
        main.httpx.AsyncClient = lambda **kwargs: BlockingOllamaClient(
            self.started, self.release, self.state
        )

    async def asyncTearDown(self):
        main.httpx.AsyncClient = self.original_client
        main.circuit_breaker = self.original_breaker
        main.inference_semaphore = self.original_semaphore
        main.INFERENCE_QUEUE_TIMEOUT_SECONDS = self.original_queue_timeout

    async def test_concurrent_requests_are_limited_by_the_semaphore(self):
        main.INFERENCE_QUEUE_TIMEOUT_SECONDS = 1
        first = asyncio.create_task(
            main.generate(main.PromptRequest(prompt="first"), ConnectedRequest())
        )
        await asyncio.wait_for(self.started.wait(), timeout=0.5)

        second = asyncio.create_task(
            main.generate(main.PromptRequest(prompt="second"), ConnectedRequest())
        )
        await asyncio.sleep(0.02)
        self.assertEqual(self.state["max_active"], 1)

        self.release.set()
        responses = await asyncio.gather(first, second)
        self.assertEqual([response["response"] for response in responses], ["ok", "ok"])
        self.assertEqual(self.state["max_active"], 1)
        self.assertEqual(main.inference_semaphore._value, 1)

    async def test_full_queue_returns_503_and_records_timeout(self):
        main.INFERENCE_QUEUE_TIMEOUT_SECONDS = 0.02
        timeout_metric = main.LLM_INFERENCE_QUEUE_TIMEOUTS.labels(main.MODEL_NAME)
        timeouts_before = timeout_metric._value.get()
        first = asyncio.create_task(
            main.generate(main.PromptRequest(prompt="first"), ConnectedRequest())
        )
        await asyncio.wait_for(self.started.wait(), timeout=0.5)

        with self.assertRaises(HTTPException) as error:
            await main.generate(main.PromptRequest(prompt="second"), ConnectedRequest())

        self.assertEqual(error.exception.status_code, 503)
        self.assertEqual(error.exception.detail, "LLM inference queue is full")
        self.assertEqual(timeout_metric._value.get(), timeouts_before + 1)

        self.release.set()
        await first
        self.assertEqual(main.inference_semaphore._value, 1)

    async def test_cancellation_releases_the_inference_slot(self):
        request = asyncio.create_task(
            main.generate(main.PromptRequest(prompt="cancel"), ConnectedRequest())
        )
        await asyncio.wait_for(self.started.wait(), timeout=0.5)

        request.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await request

        self.assertEqual(self.state["active"], 0)
        self.assertEqual(main.inference_semaphore._value, 1)
        active_metric = main.LLM_ACTIVE_INFERENCE_REQUESTS.labels(main.MODEL_NAME)
        self.assertEqual(active_metric._value.get(), 0)
