# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""Unit tests for ScenarioEventBus and ScenarioEvent."""

import asyncio
import pytest

from maiw_api.demo.events import ScenarioEvent, ScenarioEventBus


class TestScenarioEvent:
    def test_to_sse_dict_has_required_keys(self):
        ev = ScenarioEvent(category="STATE", message="test", detail="d")
        d = ev.to_sse_dict()
        assert d["category"] == "STATE"
        assert d["message"] == "test"
        assert "ts" in d
        assert "id" in d

    def test_to_sse_dict_empty_detail_is_none(self):
        ev = ScenarioEvent(category="TICK", message="tick", detail="")
        d = ev.to_sse_dict()
        assert d["detail"] is None

    def test_to_sse_dict_non_empty_detail(self):
        ev = ScenarioEvent(category="INJECT", message="inject", detail="some detail")
        d = ev.to_sse_dict()
        assert d["detail"] == "some detail"


class TestScenarioEventBus:
    def _run(self, coro):
        return asyncio.get_event_loop().run_until_complete(coro)

    def test_subscribe_returns_queue(self):
        bus = ScenarioEventBus()
        q = bus.subscribe()
        assert q is not None
        assert len(bus._subscribers) == 1

    def test_unsubscribe_removes_queue(self):
        bus = ScenarioEventBus()
        q = bus.subscribe()
        bus.unsubscribe(q)
        assert len(bus._subscribers) == 0

    def test_unsubscribe_nonexistent_is_safe(self):
        bus = ScenarioEventBus()
        import asyncio as _asyncio

        fake_q = _asyncio.Queue()
        bus.unsubscribe(fake_q)  # should not raise

    def test_publish_delivers_to_subscriber(self):
        bus = ScenarioEventBus()
        q = bus.subscribe()
        ev = ScenarioEvent(category="STATE", message="hello")
        self._run(bus.publish(ev))
        assert not q.empty()
        received = q.get_nowait()
        assert received.message == "hello"

    def test_publish_delivers_to_multiple_subscribers(self):
        bus = ScenarioEventBus()
        q1 = bus.subscribe()
        q2 = bus.subscribe()
        ev = ScenarioEvent(category="TICK", message="tick")
        self._run(bus.publish(ev))
        assert not q1.empty()
        assert not q2.empty()

    def test_publish_scenario_sets_state_category(self):
        bus = ScenarioEventBus()
        q = bus.subscribe()
        self._run(bus.publish_scenario(message="scenario:start"))
        ev = q.get_nowait()
        assert ev.category == "STATE"
        assert ev.message == "scenario:start"

    def test_publish_inject_sets_inject_category(self):
        bus = ScenarioEventBus()
        q = bus.subscribe()
        self._run(bus.publish_inject(event_type="equipment_fault", asset_id="AGV-01"))
        ev = q.get_nowait()
        assert ev.category == "INJECT"
        assert ev.asset_id == "AGV-01"

    def test_publish_tick_sets_tick_category(self):
        bus = ScenarioEventBus()
        q = bus.subscribe()
        self._run(
            bus.publish_tick(elapsed_seconds=60, clock_iso="2026-08-23T08:01:00+00:00")
        )
        ev = q.get_nowait()
        assert ev.category == "TICK"

    def test_publish_equipment_write_sets_execute_category(self):
        bus = ScenarioEventBus()
        q = bus.subscribe()
        self._run(bus.publish_equipment_write(action="assign", asset_id="AGV-01"))
        ev = q.get_nowait()
        assert ev.category == "EXECUTE"
        assert ev.asset_id == "AGV-01"

    def test_max_subscribers_evicts_oldest(self):
        bus = ScenarioEventBus()
        queues = [bus.subscribe() for _ in range(bus._MAX_SUBSCRIBERS)]
        # One more pushes out the oldest
        new_q = bus.subscribe()
        assert len(bus._subscribers) == bus._MAX_SUBSCRIBERS
        assert new_q in bus._subscribers
        # Oldest gets sentinel None
        sentinel = queues[0].get_nowait()
        assert sentinel is None
