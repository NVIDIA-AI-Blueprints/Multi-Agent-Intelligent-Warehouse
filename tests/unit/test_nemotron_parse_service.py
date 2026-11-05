"""Nemotron Parse runs only against a configured NIM and never invents text.

The hosted nvidia/nemotron-parse endpoint is retired on 2026-11-16 (DTAI-1312).
The service used it by default, and with no API key, or when a call failed, it
returned a hard-coded sample invoice ("INVOICE #INV-2024-001 ... Total:
$1,763.13") at 0.91 confidence. Its only caller is the legacy
DocumentExtractionAgent, which asks it whenever primary OCR is below 0.8
confidence and keeps the higher score. The shipped upload route does not use
that agent, but anything that did would have got the sample invoice back.
"""

import json

import httpx
import pytest
from PIL import Image

from src.api.agents.document.ocr import nemotron_parse
from src.api.agents.document.ocr.nemotron_parse import NemotronParseService

LAYOUT = {"layout_detection": []}


@pytest.fixture
def no_parse_env(monkeypatch):
    monkeypatch.delenv("NEMO_PARSE_URL", raising=False)
    monkeypatch.delenv("NEMO_PARSE_API_KEY", raising=False)


def _route_http(monkeypatch, handler):
    """Send the service's httpx calls to ``handler``; return the request log."""
    requests = []
    real_client = httpx.AsyncClient

    def record(request):
        requests.append(request)
        return handler(request)

    def client(**kwargs):
        return real_client(transport=httpx.MockTransport(record), **kwargs)

    monkeypatch.setattr(nemotron_parse.httpx, "AsyncClient", client)
    return requests


def _page():
    return Image.new("RGB", (32, 32), "white")


def _refuse(request):
    raise httpx.ConnectError("connection refused", request=request)


async def test_disabled_without_url_even_with_a_key(no_parse_env, monkeypatch):
    monkeypatch.setenv("NEMO_PARSE_API_KEY", "nvapi-test")
    requests = _route_http(monkeypatch, lambda r: httpx.Response(200, json={}))
    service = NemotronParseService()

    assert not service.enabled
    await service.initialize()
    result = await service.parse_document([_page()], LAYOUT)

    assert requests == []
    assert result["available"] is False
    assert result["confidence"] == 0.0
    assert result["text"] == ""


@pytest.mark.parametrize(
    "handler",
    [
        lambda r: httpx.Response(404, json={"detail": "Function not found"}),
        lambda r: httpx.Response(500),
        _refuse,
    ],
    ids=["retired-404", "server-error", "unreachable"],
)
async def test_failed_call_is_unavailable_not_sample_text(
    no_parse_env, monkeypatch, handler
):
    monkeypatch.setenv("NEMO_PARSE_URL", "http://nim.local:8004/v1")
    _route_http(monkeypatch, handler)
    service = NemotronParseService()

    result = await service.parse_document([_page(), _page()], LAYOUT)

    assert result["available"] is False
    assert result["confidence"] == 0.0
    assert result["text"] == ""
    assert "INVOICE" not in json.dumps(result)


async def test_configured_nim_is_called_and_parsed(no_parse_env, monkeypatch):
    monkeypatch.setenv("NEMO_PARSE_URL", "http://nim.local:8004/v1/")
    body = {
        "outputs": [
            {"name": "text", "data": ["Bill of lading 7731"]},
            {
                "name": "elements",
                "data": [
                    {"text": "Bill of lading", "type": "title", "confidence": 0.9},
                    {"text": "7731", "type": "text", "confidence": 0.7},
                ],
            },
        ]
    }
    requests = _route_http(monkeypatch, lambda r: httpx.Response(200, json=body))
    service = NemotronParseService()

    result = await service.parse_document([_page()], LAYOUT)

    assert [str(r.url) for r in requests] == [
        "http://nim.local:8004/v1/models/nemotron-parse/infer"
    ]
    assert "authorization" not in requests[0].headers
    assert result["available"] is True
    assert result["text"] == "Bill of lading 7731"
    assert result["confidence"] == pytest.approx(0.8)


async def test_api_key_is_sent_when_set(no_parse_env, monkeypatch):
    monkeypatch.setenv("NEMO_PARSE_URL", "http://nim.local:8004/v1")
    monkeypatch.setenv("NEMO_PARSE_API_KEY", "nvapi-test")
    requests = _route_http(
        monkeypatch, lambda r: httpx.Response(200, json={"outputs": []})
    )

    await NemotronParseService().parse_document([_page()], LAYOUT)

    assert requests[0].headers["authorization"] == "Bearer nvapi-test"
