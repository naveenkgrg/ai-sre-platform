import asyncio
import unittest

from apps.api.main import CircuitBreaker


class CircuitBreakerTests(unittest.IsolatedAsyncioTestCase):
    async def test_opens_then_closes_after_a_successful_recovery_request(self):
        now = [0.0]
        breaker = CircuitBreaker(clock=lambda: now[0])

        for _ in range(4):
            await breaker.record_failure()
            self.assertEqual(breaker.state, CircuitBreaker.CLOSED)

        await breaker.record_failure()
        self.assertEqual(breaker.state, CircuitBreaker.OPEN)
        self.assertFalse(await breaker.allow_request())

        now[0] = 30.0
        self.assertTrue(await breaker.allow_request())
        self.assertEqual(breaker.state, CircuitBreaker.HALF_OPEN)
        await breaker.record_success()
        self.assertEqual(breaker.state, CircuitBreaker.CLOSED)
        self.assertTrue(await breaker.allow_request())

    async def test_reopens_when_the_recovery_request_fails(self):
        now = [0.0]
        breaker = CircuitBreaker(clock=lambda: now[0])

        for _ in range(5):
            await breaker.record_failure()

        now[0] = 30.0
        self.assertTrue(await breaker.allow_request())
        await breaker.record_failure()

        self.assertEqual(breaker.state, CircuitBreaker.OPEN)
        self.assertFalse(await breaker.allow_request())

    async def test_only_one_concurrent_request_enters_half_open_state(self):
        now = [0.0]
        breaker = CircuitBreaker(clock=lambda: now[0])

        for _ in range(5):
            await breaker.record_failure()

        now[0] = 30.0
        allowed = await asyncio.gather(
            *(breaker.allow_request() for _ in range(10))
        )

        self.assertEqual(sum(allowed), 1)
        self.assertEqual(breaker.state, CircuitBreaker.HALF_OPEN)
