"""Redis failure deadlines without touching shared Redis or MongoDB."""

import asyncio
import time
import unittest
from unittest.mock import AsyncMock, patch

import cache
from settings import CacheSettings


class CacheTimeoutTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.settings = CacheSettings(cache_enabled=True, redis_timeout_seconds=0.05)
        self.config = patch.object(cache, "_cache_settings", return_value=self.settings)
        self.config.start()
        cache.redis_client = None
        cache._last_connect_attempt_ts = 0

    async def asyncTearDown(self):
        await cache.close_cache()
        self.config.stop()

    async def stall(self, *args):
        await asyncio.sleep(10)

    async def test_startup_with_silent_tcp_server_returns_promptly(self):
        writers = []

        async def silent(reader, writer):
            writers.append(writer)
            try:
                await reader.read()
            finally:
                writer.close()

        server = await asyncio.start_server(silent, "127.0.0.1", 0)
        port = server.sockets[0].getsockname()[1]
        self.settings.redis_url = f"redis://127.0.0.1:{port}/0"
        try:
            started = time.monotonic()
            await asyncio.wait_for(cache.init_cache(), timeout=1)
            self.assertLess(time.monotonic() - started, 0.5)
            self.assertIsNone(cache.redis_client)
        finally:
            server.close()
            for writer in writers:
                writer.close()
                await writer.wait_closed()
            await server.wait_closed()

    async def test_get_timeout_falls_back_without_immediate_reconnect(self):
        client = AsyncMock()
        client.get.side_effect = self.stall
        cache.redis_client = client
        with patch.object(cache.redis.Redis, "from_url") as connect:
            self.assertIsNone(await asyncio.wait_for(cache.cache_get("test"), 1))
            self.assertIsNone(await cache.cache_get("test"))
            await cache.cache_set("test", {"value": 1})
            connect.assert_not_called()
        client.aclose.assert_awaited_once()

    async def test_set_timeout_is_bounded(self):
        client = AsyncMock()
        client.setex.side_effect = self.stall
        cache.redis_client = client
        await asyncio.wait_for(cache.cache_set("test", {"value": 1}), 1)
        self.assertIsNone(cache.redis_client)
        client.aclose.assert_awaited_once()

    async def test_failed_ping_closes_candidate(self):
        candidate = AsyncMock()
        candidate.ping.side_effect = self.stall
        with patch.object(cache.redis.Redis, "from_url", return_value=candidate):
            await asyncio.wait_for(cache.init_cache(), 1)
        candidate.aclose.assert_awaited_once()
        self.assertIsNone(cache.redis_client)

    async def test_client_recovers_after_backoff(self):
        candidate = AsyncMock()
        candidate.get.return_value = '{"value": 1}'
        cache._last_connect_attempt_ts = time.monotonic() - 6
        with patch.object(cache.redis.Redis, "from_url", return_value=candidate):
            self.assertEqual(await cache.cache_get("test"), {"value": 1})
        self.assertIs(cache.redis_client, candidate)

    async def test_slow_cleanup_is_bounded(self):
        client = AsyncMock()
        client.aclose.side_effect = self.stall
        cache.redis_client = client
        await asyncio.wait_for(cache.close_cache(), 1)
        self.assertIsNone(cache.redis_client)

    async def test_old_failure_does_not_disconnect_replacement(self):
        old, new = AsyncMock(), AsyncMock()
        cache.redis_client = new
        await cache._discard_failed_client(old)
        self.assertIs(cache.redis_client, new)
        new.aclose.assert_not_awaited()

    def test_invalid_deadlines_rejected(self):
        for value in [0, -1, 6]:
            with self.subTest(value=value), self.assertRaises(ValueError):
                CacheSettings(redis_timeout_seconds=value)
