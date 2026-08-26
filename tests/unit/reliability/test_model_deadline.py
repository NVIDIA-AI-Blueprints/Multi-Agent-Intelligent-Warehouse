# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
Deterministic tests for RequestDeadline propagation through the canonical model path:

    ModelRequest.deadline → ModelGateway → NIMProvider → NIMClient

No real sleeps.  All time is controlled via FakeClock.
asyncio.sleep is monkeypatched to a no-op in retry tests.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from maiw_mcp.deadline import RequestDeadline, RequestDeadlineExceeded
from maiw_models.errors import ModelTimeout, ModelUnavailable, ModelResponseError
from maiw_models.models import ModelRequest, ReasoningLevel, RiskLevel
from maiw_models.providers.nim_client import NIMClient, NIMConfig, LLMResponse


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------


class FakeClock:
    def __init__(self, start: float = 0.0) -> None:
        self._t = start

    def __call__(self) -> float:
        return self._t

    def advance(self, seconds: float) -> None:
        self._t += seconds


def _make_config(timeout: int = 30) -> NIMConfig:
    return NIMConfig(
        llm_api_key="test-key",
        llm_model="test/model",
        timeout=timeout,
    )


def _make_client(config: NIMConfig | None = None) -> NIMClient:
    return NIMClient(config=config or _make_config(), enable_cache=False)


def _ok_post_mock(content: str = "ok") -> AsyncMock:
    """Returns an httpx-like successful response."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15},
        "model": "test/model",
    }
    return AsyncMock(return_value=resp)


def _http_status_post_mock(status_code: int) -> AsyncMock:
    """Returns a mock that raises HTTPStatusError with the given status."""
    def _raise(*args, **kwargs):
        resp = MagicMock()
        resp.status_code = status_code
        raise httpx.HTTPStatusError(
            f"HTTP {status_code}", request=MagicMock(), response=resp
        )
    return AsyncMock(side_effect=_raise)


def _timeout_post_mock() -> AsyncMock:
    return AsyncMock(side_effect=httpx.TimeoutException("timed out"))


def _run(coro):
    return asyncio.new_event_loop().run_until_complete(coro)


# ---------------------------------------------------------------------------
# 15a — ModelRequest accepts deadline field
# ---------------------------------------------------------------------------


class TestModelRequestDeadlineField:
    def test_deadline_defaults_to_none(self):
        req = ModelRequest(task="t", messages=[])
        assert req.deadline is None

    def test_deadline_accepts_request_deadline(self):
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.from_timeout(30.0, clock=clock)
        req = ModelRequest(task="t", messages=[], deadline=dl)
        assert req.deadline is dl

    def test_deadline_accepts_unlimited(self):
        dl = RequestDeadline.unlimited()
        req = ModelRequest(task="t", messages=[], deadline=dl)
        assert req.deadline is dl

    def test_deadline_accepts_none_explicitly(self):
        req = ModelRequest(task="t", messages=[], deadline=None)
        assert req.deadline is None

    def test_existing_fields_unaffected(self):
        req = ModelRequest(
            task="warehouse.test",
            messages=[{"role": "user", "content": "hi"}],
            reasoning=ReasoningLevel.HIGH,
            risk_level=RiskLevel.CRITICAL,
        )
        assert req.task == "warehouse.test"
        assert req.reasoning == ReasoningLevel.HIGH


# ---------------------------------------------------------------------------
# 15b — ModelGateway: expired deadline → 0 provider calls
# ---------------------------------------------------------------------------


class TestModelGatewayDeadlineGuard:
    def _make_gateway(self):
        from maiw_models.gateway import ModelGateway
        from maiw_models.registry import ModelRegistry
        from maiw_models.router import ModelRouter
        from maiw_models.telemetry import GatewayTelemetry
        import os
        from unittest.mock import patch as _patch

        env = {
            "NEMOTRON_SUPER_ENABLED": "true",
            "NEMOTRON_SUPER_MODEL": "test/super-model",
        }
        with _patch.dict(os.environ, env):
            registry = ModelRegistry()

        mock_provider = MagicMock()
        mock_provider.call = AsyncMock(
            return_value=MagicMock(
                content="ok",
                usage={},
                model="test/super-model",
                finish_reason="stop",
            )
        )
        gateway = ModelGateway(
            provider=mock_provider,
            registry=registry,
            router=ModelRouter(registry),
            telemetry=GatewayTelemetry(),
        )
        return gateway, mock_provider

    def test_expired_deadline_raises_before_provider(self):
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.from_timeout(5.0, clock=clock)
        clock.advance(10.0)  # expired by 5s

        gateway, mock_provider = self._make_gateway()
        req = ModelRequest(task="t", messages=[], deadline=dl)

        with pytest.raises(RequestDeadlineExceeded):
            _run(gateway.generate(req))

        mock_provider.call.assert_not_called()

    def test_expired_deadline_exceeded_by_correct_amount(self):
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.from_timeout(10.0, clock=clock)
        clock.advance(13.0)  # expired by 3s

        gateway, _ = self._make_gateway()
        req = ModelRequest(task="t", messages=[], deadline=dl)

        with pytest.raises(RequestDeadlineExceeded) as exc_info:
            _run(gateway.generate(req))

        assert exc_info.value.expired_by_ms == pytest.approx(3000.0, abs=1.0)

    def test_fresh_deadline_calls_provider(self):
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.from_timeout(30.0, clock=clock)

        gateway, mock_provider = self._make_gateway()
        req = ModelRequest(task="t", messages=[], deadline=dl)

        response = _run(gateway.generate(req))
        assert response.content == "ok"
        mock_provider.call.assert_called_once()

    def test_no_deadline_calls_provider_normally(self):
        gateway, mock_provider = self._make_gateway()
        req = ModelRequest(task="t", messages=[])

        response = _run(gateway.generate(req))
        assert response.content == "ok"
        mock_provider.call.assert_called_once()

    def test_unlimited_deadline_calls_provider(self):
        dl = RequestDeadline.unlimited()
        gateway, mock_provider = self._make_gateway()
        req = ModelRequest(task="t", messages=[], deadline=dl)

        response = _run(gateway.generate(req))
        assert response.content == "ok"
        mock_provider.call.assert_called_once()

    def test_request_deadline_exceeded_not_wrapped_as_model_timeout(self):
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.from_timeout(5.0, clock=clock)
        clock.advance(10.0)

        gateway, _ = self._make_gateway()
        req = ModelRequest(task="t", messages=[], deadline=dl)

        with pytest.raises(RequestDeadlineExceeded):
            _run(gateway.generate(req))

        # Confirm it is NOT ModelTimeout
        try:
            _run(gateway.generate(req))
        except RequestDeadlineExceeded:
            pass  # correct
        except ModelTimeout:
            pytest.fail("Deadline exhaustion must not be wrapped as ModelTimeout")


# ---------------------------------------------------------------------------
# 15c — NIMClient: effective timeout shrinks with remaining budget
# ---------------------------------------------------------------------------


class TestNIMClientTimeoutPropagation:
    def test_no_deadline_uses_config_timeout(self):
        client = _make_client(_make_config(timeout=30))
        captured_timeout = []

        async def fake_post(path, **kwargs):
            captured_timeout.append(kwargs.get("timeout", "DEFAULT"))
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                "usage": {}, "model": "test/model",
            }
            return resp

        client.llm_client.post = fake_post
        result = _run(client.generate_response(messages=[{"role": "user", "content": "hi"}]))
        assert result.content == "ok"
        # No deadline → no per-request timeout kwarg (uses client-level default)
        assert captured_timeout[0] == "DEFAULT"

    def test_deadline_with_abundant_budget_uses_config_timeout(self):
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.from_timeout(3600.0, clock=clock)
        client = _make_client(_make_config(timeout=30))
        captured_timeout = []

        async def fake_post(path, **kwargs):
            captured_timeout.append(kwargs.get("timeout"))
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                "usage": {}, "model": "test/model",
            }
            return resp

        client.llm_client.post = fake_post
        _run(client.generate_response(
            messages=[{"role": "user", "content": "hi"}], deadline=dl
        ))
        # config.timeout=30, remaining=3600 → effective = min(30, 3600) = 30
        assert captured_timeout[0] == pytest.approx(30.0)

    def test_deadline_with_tight_budget_reduces_timeout(self):
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.from_timeout(10.0, clock=clock)
        clock.advance(8.0)  # 2s remaining
        client = _make_client(_make_config(timeout=30))
        captured_timeout = []

        async def fake_post(path, **kwargs):
            captured_timeout.append(kwargs.get("timeout"))
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                "usage": {}, "model": "test/model",
            }
            return resp

        client.llm_client.post = fake_post
        _run(client.generate_response(
            messages=[{"role": "user", "content": "hi"}], deadline=dl
        ))
        # config.timeout=30, remaining≈2s → effective = min(30, 2) = 2
        assert captured_timeout[0] == pytest.approx(2.0, abs=0.1)

    def test_expired_deadline_raises_before_httpx_call(self):
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.from_timeout(5.0, clock=clock)
        clock.advance(10.0)

        client = _make_client()
        client.llm_client.post = AsyncMock()  # should never be called

        with pytest.raises(RequestDeadlineExceeded):
            _run(client.generate_response(
                messages=[{"role": "user", "content": "hi"}], deadline=dl
            ))

        client.llm_client.post.assert_not_called()


# ---------------------------------------------------------------------------
# 15d — Retry behavior with deadline (mocked asyncio.sleep)
# ---------------------------------------------------------------------------


class TestNIMClientRetryWithDeadline:
    def _client_with_response_sequence(self, responses, timeout: int = 30) -> NIMClient:
        client = _make_client(_make_config(timeout=timeout))
        call_iter = iter(responses)

        async def fake_post(path, **kwargs):
            resp_or_exc = next(call_iter)
            if isinstance(resp_or_exc, Exception):
                raise resp_or_exc
            return resp_or_exc

        client.llm_client.post = fake_post
        return client

    def _ok_response(self):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {
            "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
            "usage": {}, "model": "test/model",
        }
        return resp

    def _http_error(self, code: int):
        resp = MagicMock()
        resp.status_code = code
        return httpx.HTTPStatusError(f"HTTP {code}", request=MagicMock(), response=resp)

    # ── Retry success cases ───────────────────────────────────────────────

    def test_timeout_retry_succeeds_within_budget(self):
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.from_timeout(120.0, clock=clock)
        responses = [
            httpx.TimeoutException("timed out"),
            self._ok_response(),
        ]
        client = self._client_with_response_sequence(responses, timeout=30)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = _run(client.generate_response(
                messages=[{"role": "user", "content": "hi"}], deadline=dl
            ))
        assert result.content == "ok"

    def test_429_retry_succeeds_within_budget(self):
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.from_timeout(120.0, clock=clock)
        responses = [self._http_error(429), self._ok_response()]
        client = self._client_with_response_sequence(responses)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = _run(client.generate_response(
                messages=[{"role": "user", "content": "hi"}], deadline=dl
            ))
        assert result.content == "ok"

    def test_500_retry_succeeds_within_budget(self):
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.from_timeout(120.0, clock=clock)
        responses = [self._http_error(500), self._ok_response()]
        client = self._client_with_response_sequence(responses)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = _run(client.generate_response(
                messages=[{"role": "user", "content": "hi"}], deadline=dl
            ))
        assert result.content == "ok"

    # ── No-retry on 4xx ───────────────────────────────────────────────────

    def test_400_does_not_retry(self):
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.from_timeout(120.0, clock=clock)
        responses = [self._http_error(400)]
        client = self._client_with_response_sequence(responses)
        call_count = [0]
        original_post = client.llm_client.post

        async def counting_post(path, **kwargs):
            call_count[0] += 1
            return await original_post(path, **kwargs)

        client.llm_client.post = counting_post

        with pytest.raises(ConnectionError):
            _run(client.generate_response(
                messages=[{"role": "user", "content": "hi"}], deadline=dl
            ))
        # 400 = no retry → exactly 1 call
        assert call_count[0] == 1

    def test_401_does_not_retry(self):
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.from_timeout(120.0, clock=clock)
        responses = [self._http_error(401)]
        client = self._client_with_response_sequence(responses)

        with pytest.raises(ConnectionError):
            with patch("asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
                _run(client.generate_response(
                    messages=[{"role": "user", "content": "hi"}], deadline=dl
                ))
        mock_sleep.assert_not_called()

    # ── Deadline suppresses retry ─────────────────────────────────────────

    def test_deadline_expired_before_first_attempt_raises(self):
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.from_timeout(5.0, clock=clock)
        clock.advance(6.0)  # expired

        client = _make_client()
        client.llm_client.post = AsyncMock()

        with pytest.raises(RequestDeadlineExceeded):
            _run(client.generate_response(
                messages=[{"role": "user", "content": "hi"}], deadline=dl
            ))
        client.llm_client.post.assert_not_called()

    def test_deadline_exhausted_after_first_timeout_suppresses_retry(self):
        """After first attempt times out, remaining budget < backoff → no second attempt."""
        clock = FakeClock(start=0.0)
        # budget=3s; backoff after attempt 0 = 2^0 = 1s; but we'll drain to 0.5s
        dl = RequestDeadline.from_timeout(3.0, clock=clock)

        client = _make_client(_make_config(timeout=30))
        call_count = [0]

        async def fake_post(path, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                clock.advance(2.6)  # drain to 0.4s remaining
                raise httpx.TimeoutException("timed out")
            return self._ok_response()

        client.llm_client.post = fake_post

        # remaining (0.4s) < backoff (1s) → retry suppressed
        with pytest.raises(httpx.TimeoutException):
            _run(client.generate_response(
                messages=[{"role": "user", "content": "hi"}], deadline=dl
            ))
        assert call_count[0] == 1

    def test_deadline_insufficient_for_backoff_suppresses_retry(self):
        """Explicitly test backoff suppression: remaining <= wait_time."""
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.from_timeout(10.0, clock=clock)

        client = _make_client(_make_config(timeout=30))
        call_count = [0]

        async def fake_post(path, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                clock.advance(9.5)  # 0.5s remaining; backoff = 2^0 = 1s
                raise httpx.TimeoutException("timed out")
            return self._ok_response()

        client.llm_client.post = fake_post

        # 0.5s remaining < 1s backoff → no second attempt
        with pytest.raises(httpx.TimeoutException):
            _run(client.generate_response(
                messages=[{"role": "user", "content": "hi"}], deadline=dl
            ))
        assert call_count[0] == 1

    def test_deadline_expired_before_second_attempt(self):
        """Deadline expires during backoff sleep → second attempt check raises."""
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.from_timeout(10.0, clock=clock)

        client = _make_client(_make_config(timeout=30))
        call_count = [0]

        async def fake_post(path, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                raise httpx.TimeoutException("timed out")
            return self._ok_response()

        client.llm_client.post = fake_post

        async def draining_sleep(seconds):
            clock.advance(seconds + 20.0)  # drain clock far past deadline

        async def run():
            with patch("maiw_models.providers.nim_client.asyncio.sleep", side_effect=draining_sleep):
                return await client.generate_response(
                    messages=[{"role": "user", "content": "hi"}], deadline=dl
                )

        with pytest.raises(RequestDeadlineExceeded):
            _run(run())

    def test_no_deadline_retries_without_budget_check(self):
        """Legacy path (no deadline) retries normally using config timeout."""
        responses = [
            httpx.TimeoutException("timed out"),
            self._ok_response(),
        ]
        client = self._client_with_response_sequence(responses)

        with patch("asyncio.sleep", new_callable=AsyncMock):
            result = _run(client.generate_response(
                messages=[{"role": "user", "content": "hi"}],
                # no deadline
            ))
        assert result.content == "ok"


# ---------------------------------------------------------------------------
# 15e — NIMProvider propagates deadline (integration with NIMClient mock)
# ---------------------------------------------------------------------------


class TestNIMProviderDeadlinePropagation:
    def _make_provider(self) -> tuple:
        from maiw_models.providers.nim import NIMProvider
        from maiw_models.models import ModelCapability

        mock_client = MagicMock(spec=NIMClient)
        mock_client.config = _make_config()
        provider = NIMProvider(nim_client=mock_client)
        capability = ModelCapability(
            model_id="test/model",
            role="super",
        )
        return provider, mock_client, capability

    def test_deadline_passed_to_nim_client(self):
        provider, mock_client, capability = self._make_provider()
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.from_timeout(30.0, clock=clock)

        mock_client.generate_response = AsyncMock(return_value=LLMResponse(
            content="ok", usage={}, model="test/model", finish_reason="stop"
        ))

        req = ModelRequest(task="t", messages=[], deadline=dl)
        _run(provider.call(model_id="test/model", request=req, capability=capability))

        call_kwargs = mock_client.generate_response.call_args.kwargs
        assert call_kwargs.get("deadline") is dl

    def test_none_deadline_passed_to_nim_client(self):
        provider, mock_client, capability = self._make_provider()

        mock_client.generate_response = AsyncMock(return_value=LLMResponse(
            content="ok", usage={}, model="test/model", finish_reason="stop"
        ))

        req = ModelRequest(task="t", messages=[])
        _run(provider.call(model_id="test/model", request=req, capability=capability))

        call_kwargs = mock_client.generate_response.call_args.kwargs
        assert call_kwargs.get("deadline") is None

    def test_request_deadline_exceeded_not_wrapped_as_model_response_error(self):
        provider, mock_client, capability = self._make_provider()

        mock_client.generate_response = AsyncMock(
            side_effect=RequestDeadlineExceeded(expired_by_ms=500.0)
        )

        req = ModelRequest(task="t", messages=[])
        with pytest.raises(RequestDeadlineExceeded):
            _run(provider.call(model_id="test/model", request=req, capability=capability))

    def test_timeout_still_becomes_model_timeout(self):
        provider, mock_client, capability = self._make_provider()

        mock_client.generate_response = AsyncMock(
            side_effect=httpx.TimeoutException("timed out")
        )

        req = ModelRequest(task="t", messages=[])
        with pytest.raises(ModelTimeout):
            _run(provider.call(model_id="test/model", request=req, capability=capability))


# ---------------------------------------------------------------------------
# 15f — Worst-case bound verification
# ---------------------------------------------------------------------------


class TestWorstCaseBound:
    def test_30s_budget_cannot_exceed_30s(self):
        """Any request with a 30s deadline can never consume more than 30s."""
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.from_timeout(30.0, clock=clock)

        # Simulate 30 failed attempts — deadline check stops them all
        client = _make_client(_make_config(timeout=240))
        call_count = [0]

        async def fake_post(path, **kwargs):
            call_count[0] += 1
            clock.advance(5.0)  # each attempt consumes 5s
            if not dl.expired:
                raise httpx.TimeoutException("timed out")
            # Should never reach here — deadline check fires first
            pytest.fail("Provider called after deadline expired")

        client.llm_client.post = fake_post

        with patch("asyncio.sleep", new_callable=AsyncMock):
            # Will eventually exhaust budget
            try:
                _run(client.generate_response(
                    messages=[{"role": "user", "content": "hi"}],
                    deadline=dl,
                ))
            except (RequestDeadlineExceeded, httpx.TimeoutException, ConnectionError):
                pass

        # Must never consume more than budget
        assert clock() <= 31.0  # allow 1s slop for test mechanics

    def test_budget_propagated_as_effective_timeout_not_config_timeout(self):
        """When 5s remain, httpx receives 5s not 240s."""
        clock = FakeClock(start=0.0)
        dl = RequestDeadline.from_timeout(30.0, clock=clock)
        clock.advance(25.0)  # 5s remaining

        client = _make_client(_make_config(timeout=240))
        captured_timeout = []

        async def fake_post(path, **kwargs):
            captured_timeout.append(kwargs.get("timeout"))
            resp = MagicMock()
            resp.raise_for_status = MagicMock()
            resp.json.return_value = {
                "choices": [{"message": {"content": "ok"}, "finish_reason": "stop"}],
                "usage": {}, "model": "test/model",
            }
            return resp

        client.llm_client.post = fake_post
        _run(client.generate_response(
            messages=[{"role": "user", "content": "hi"}], deadline=dl
        ))
        assert captured_timeout[0] == pytest.approx(5.0, abs=0.1)
        assert captured_timeout[0] < 10.0  # definitely not 240
