"""
MCP domain image and deployment probe guards.

Dockerfile.mcp builds the four ``wosa-mcp-*`` Compose services.  After #94
moved code into maiw-contracts / maiw-decision the image stopped installing
them and every server crash-looped on ModuleNotFoundError while the
deployment workflow stayed green.  These checks keep the image's installed
packages in step with the servers' startup imports, and keep the workflow
probing the running containers.
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
DOMAINS = ("inventory", "equipment", "labor", "wave")


def _startup_maiw_packages(path: Path) -> set[str]:
    """Top-level ``maiw_*`` imports of a module (imported at startup)."""
    found = set()
    for node in ast.parse(path.read_text()).body:
        if isinstance(node, ast.ImportFrom) and node.module:
            names = [node.module]
        elif isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        else:
            continue
        found |= {n.split(".")[0] for n in names if n.startswith("maiw_")}
    return found


def _installed_packages(dockerfile: str) -> set[str]:
    install = dockerfile.split("RUN pip install --no-cache-dir", 1)[1].split("\n\n")[0]
    return {
        tok.split("/")[1].replace("-", "_")
        for tok in install.split()
        if tok.startswith("packages/")
    }


def test_mcp_image_installs_every_maiw_package_servers_import_at_startup():
    dockerfile = (REPO_ROOT / "Dockerfile.mcp").read_text()
    installed = _installed_packages(dockerfile)
    for domain in DOMAINS:
        for module in ("server.py", "provider.py"):
            needed = _startup_maiw_packages(REPO_ROOT / "mcp_servers" / domain / module)
            missing = needed - installed
            assert not missing, f"{domain}/{module} imports {missing}, not installed"
    for package in installed:
        dirname = package.replace("_", "-")
        assert f"COPY packages/{dirname} ./packages/{dirname}" in dockerfile


def _module_file(module: str) -> Path | None:
    base = REPO_ROOT.joinpath(*module.split("."))
    for candidate in (base.with_suffix(".py"), base / "__init__.py"):
        if candidate.is_file():
            return candidate
    return None


def _repo_imports(path: Path) -> set[str]:
    """Every ``src.*`` / ``mcp_servers.*`` module a file imports, at any depth."""
    package = path.relative_to(REPO_ROOT).parts[:-1]
    found = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            names = [a.name for a in node.names]
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = list(package[: len(package) - node.level + 1])
                prefix = ".".join(base + ([node.module] if node.module else []))
            else:
                prefix = node.module or ""
            names = [prefix] + [f"{prefix}.{a.name}" for a in node.names]
        else:
            continue
        for name in names:
            if name.split(".")[0] in ("src", "mcp_servers"):
                parts = name.split(".")
                found |= {".".join(parts[:i]) for i in range(2, len(parts) + 1)}
    return found


def test_mcp_image_copies_all_repo_code_the_servers_reach():
    # The adapters import repo code lazily on first use (and equipment builds
    # its provider at startup), so follow every src.* import transitively.
    dockerfile = (REPO_ROOT / "Dockerfile.mcp").read_text()
    copied = [
        m.group(1).replace("${MCP_DOMAIN}", "{domain}")
        for m in re.finditer(r"^COPY (src/\S+|mcp_servers/\S+) ", dockerfile, re.M)
    ]
    for domain in DOMAINS:
        roots = [c.format(domain=domain) for c in copied]
        seen: set[Path] = set()
        queue = sorted((REPO_ROOT / "mcp_servers" / domain).rglob("*.py"))
        while queue:
            path = queue.pop()
            if path in seen:
                continue
            seen.add(path)
            rel = path.relative_to(REPO_ROOT).as_posix()
            assert any(
                rel == r or rel.startswith(r.rstrip("/") + "/") for r in roots
            ), f"{domain}: {rel} is imported but not copied into the image"
            for module in _repo_imports(path):
                target = _module_file(module)
                if target is not None:
                    queue.append(target)


def test_every_mcp_server_has_a_launch_entry_point():
    # Dockerfile.mcp runs ``python -m mcp_servers.<domain>.server``; a module
    # without a __main__ block imports, exits 0 and restart-loops.
    compose = (REPO_ROOT / "deploy/compose/docker-compose.dev.yaml").read_text()
    for domain in DOMAINS:
        source = (REPO_ROOT / "mcp_servers" / domain / "server.py").read_text()
        mains = [
            node
            for node in ast.parse(source).body
            if isinstance(node, ast.If)
            and "__main__" in ast.unparse(node.test)
            and "__name__" in ast.unparse(node.test)
        ]
        assert len(mains) == 1, f"{domain}/server.py has no __main__ entry point"
        block = ast.unparse(mains[0])
        assert "mcp_server.run('streamable-http'" in block
        env = f"MAIW_MCP_{domain.upper()}_PORT"
        default = re.search(rf"{env}', '(\d+)'", block)
        assert default, f"{domain}: entry point does not read {env}"
        assert f"{env}={default.group(1)}" in compose


def test_deploy_workflow_probes_all_mcp_containers():
    jobs = yaml.safe_load((REPO_ROOT / ".github/workflows/main.yml").read_text())[
        "jobs"
    ]
    steps = {s.get("name", ""): s for job in jobs.values() for s in job["steps"]}
    run = steps["Verify: MCP domain servers"]["run"]
    assert "continue-on-error" not in steps["Verify: MCP domain servers"]
    for domain in DOMAINS:
        assert f"wosa-mcp-{domain}" in run
    assert "python3 scripts/testing/probe_mcp_servers.py" in run


def _probe_module():
    spec = importlib.util.spec_from_file_location(
        "probe_mcp_servers", REPO_ROOT / "scripts/testing/probe_mcp_servers.py"
    )
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_probe_defaults_match_compose_ports():
    compose = (REPO_ROOT / "deploy/compose/docker-compose.dev.yaml").read_text()
    for domain, port in _probe_module().DEFAULT_DOMAINS.items():
        assert f"MAIW_MCP_{domain.upper()}_PORT={port}" in compose


def test_probe_parses_event_stream_and_json_replies():
    probe = _probe_module()
    message = {"jsonrpc": "2.0", "id": 1, "result": {"serverInfo": {"name": "x"}}}
    sse = f"event: message\ndata: {json.dumps(message)}\n\n"
    assert probe.parse_jsonrpc("text/event-stream", sse, 1) == message
    assert probe.parse_jsonrpc("application/json", json.dumps(message), 1) == message


def test_probe_rejects_errors_and_missing_responses():
    probe = _probe_module()
    error = {"jsonrpc": "2.0", "id": 2, "error": {"code": -32601, "message": "nope"}}
    with pytest.raises(probe.ProbeError, match="JSON-RPC error"):
        probe.parse_jsonrpc("application/json", json.dumps(error), 2)
    with pytest.raises(probe.ProbeError, match="no JSON-RPC response"):
        probe.parse_jsonrpc("application/json", json.dumps({"id": 9}), 2)
