from __future__ import annotations

import asyncio
import unittest
from types import SimpleNamespace

from plugin import TarotRuntime, TarotsPlugin


class StreamSerializationTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self) -> None:
        self.plugin = object.__new__(TarotsPlugin)
        self.plugin._stream_execution_locks = {}
        self.runtime = TarotRuntime(self.plugin)

    async def test_same_stream_executions_do_not_overlap(self) -> None:
        active = 0
        max_active = 0
        order: list[str] = []

        async def fake_execute(
            stream_id: str,
            card_type: str,
            formation: str,
            target_user: str,
            user_request: str,
        ) -> tuple[bool, str]:
            nonlocal active, max_active
            del stream_id, card_type, formation, target_user
            active += 1
            max_active = max(max_active, active)
            order.append(f"start:{user_request}")
            await asyncio.sleep(0.01)
            order.append(f"end:{user_request}")
            active -= 1
            return True, user_request

        self.runtime._execute_unlocked = fake_execute
        results = await asyncio.gather(
            self.runtime.execute("group-1", user_request="first"),
            self.runtime.execute("group-1", user_request="second"),
        )

        self.assertEqual(max_active, 1)
        self.assertEqual(order, ["start:first", "end:first", "start:second", "end:second"])
        self.assertEqual(results, [(True, "first"), (True, "second")])
        self.assertEqual(self.plugin._stream_execution_locks, {})

    async def test_different_streams_can_execute_concurrently(self) -> None:
        both_started = asyncio.Event()
        active = 0
        max_active = 0

        async def fake_execute(
            stream_id: str,
            card_type: str,
            formation: str,
            target_user: str,
            user_request: str,
        ) -> tuple[bool, str]:
            nonlocal active, max_active
            del card_type, formation, target_user, user_request
            active += 1
            max_active = max(max_active, active)
            if active == 2:
                both_started.set()
            await asyncio.wait_for(both_started.wait(), timeout=0.2)
            active -= 1
            return True, stream_id

        self.runtime._execute_unlocked = fake_execute
        results = await asyncio.gather(
            self.runtime.execute("group-1"),
            self.runtime.execute("group-2"),
        )

        self.assertEqual(max_active, 2)
        self.assertEqual(results, [(True, "group-1"), (True, "group-2")])
        self.assertEqual(self.plugin._stream_execution_locks, {})

    async def test_stream_lock_is_released_after_execution_error(self) -> None:
        calls = 0

        async def fake_execute(*args: object, **kwargs: object) -> tuple[bool, str]:
            nonlocal calls
            del args, kwargs
            calls += 1
            if calls == 1:
                raise RuntimeError("boom")
            return True, "ok"

        self.runtime._execute_unlocked = fake_execute

        with self.assertRaises(RuntimeError):
            await self.runtime.execute("group-1")
        result = await self.runtime.execute("group-1")

        self.assertEqual(result, (True, "ok"))
        self.assertEqual(self.plugin._stream_execution_locks, {})


if __name__ == "__main__":
    unittest.main()
