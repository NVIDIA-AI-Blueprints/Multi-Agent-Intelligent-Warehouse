#!/usr/bin/env python3
"""
Probe the MAIW MCP domain servers over streamable HTTP.

For each domain this sends a JSON-RPC ``initialize`` and a ``tools/list`` to
``http://<host>:<port>/mcp`` and requires a ``serverInfo`` and at least one
tool.  Used by the deployment workflow against the Compose ``wosa-mcp-*``
containers; stdlib only so it runs on the bare runner.

    python3 scripts/testing/probe_mcp_servers.py
    python3 scripts/testing/probe_mcp_servers.py --domain inventory=8765

Exit status is 0 only when every domain answers both requests.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from typing import Any

DEFAULT_DOMAINS = {"inventory": 8765, "equipment": 8766, "labor": 8767, "wave": 8768}
PROTOCOL_VERSION = "2025-06-18"


class ProbeError(Exception):
    """A domain server did not answer as an MCP server."""


def parse_jsonrpc(content_type: str, body: str, request_id: int) -> dict[str, Any]:
    """
    Return the JSON-RPC response with ``request_id`` from a streamable-HTTP
    reply, which is either ``application/json`` or a ``text/event-stream``
    whose ``data:`` lines carry JSON-RPC messages.
    """
    if "text/event-stream" in content_type:
        messages = []
        data: list[str] = []
        for line in body.splitlines() + [""]:
            if line.startswith("data:"):
                data.append(line[5:].lstrip())
            elif not line.strip() and data:
                messages.append(json.loads("\n".join(data)))
                data = []
    else:
        parsed = json.loads(body)
        messages = parsed if isinstance(parsed, list) else [parsed]
    for message in messages:
        if isinstance(message, dict) and message.get("id") == request_id:
            if "error" in message:
                raise ProbeError(f"JSON-RPC error: {message['error']}")
            return message
    raise ProbeError(f"no JSON-RPC response with id={request_id} in reply")


def _post(url: str, payload: dict, headers: dict[str, str], timeout: float):
    request = urllib.request.Request(
        url,
        data=json.dumps(payload).encode(),
        method="POST",
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            **headers,
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return (
            response.headers.get("Content-Type", ""),
            dict(response.headers),
            response.read().decode(),
        )


def probe(host: str, port: int, timeout: float) -> tuple[str, list[str]]:
    """Return (server name, tool names) for one domain, or raise."""
    url = f"http://{host}:{port}/mcp"
    ctype, headers, body = _post(
        url,
        {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "initialize",
            "params": {
                "protocolVersion": PROTOCOL_VERSION,
                "capabilities": {},
                "clientInfo": {"name": "maiw-ci-probe", "version": "1"},
            },
        },
        {},
        timeout,
    )
    result = parse_jsonrpc(ctype, body, 1).get("result") or {}
    server = (result.get("serverInfo") or {}).get("name")
    if not server:
        raise ProbeError("initialize returned no serverInfo")

    follow = {"MCP-Protocol-Version": result.get("protocolVersion", PROTOCOL_VERSION)}
    session = {k.lower(): v for k, v in headers.items()}.get("mcp-session-id")
    if session:
        follow["Mcp-Session-Id"] = session
    ctype, _, body = _post(
        url,
        {"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}},
        follow,
        timeout,
    )
    tools = (parse_jsonrpc(ctype, body, 2).get("result") or {}).get("tools") or []
    names = [t.get("name", "?") for t in tools]
    if not names:
        raise ProbeError("tools/list returned no tools")
    return server, names


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--host", default="localhost")
    parser.add_argument(
        "--domain",
        action="append",
        metavar="NAME=PORT",
        help="domain to probe (repeatable; default: all four Compose domains)",
    )
    parser.add_argument("--attempts", type=int, default=15)
    parser.add_argument("--delay", type=float, default=2.0)
    parser.add_argument("--timeout", type=float, default=10.0)
    args = parser.parse_args(argv)

    domains = (
        {n: int(p) for n, p in (d.split("=", 1) for d in args.domain)}
        if args.domain
        else DEFAULT_DOMAINS
    )
    failed = []
    for name, port in domains.items():
        error: Exception | None = None
        for _ in range(args.attempts):
            try:
                server, tools = probe(args.host, port, args.timeout)
            except (ProbeError, OSError, ValueError, urllib.error.URLError) as exc:
                error = exc
                time.sleep(args.delay)
                continue
            print(
                f"✅ {name} (:{port}) {server}: {len(tools)} tools — {', '.join(tools)}"
            )
            error = None
            break
        if error is not None:
            print(f"❌ {name} (:{port}) not answering as an MCP server: {error}")
            failed.append(name)
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
