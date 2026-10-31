# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
v2.1.0 — default network exposure and the documented first run.

Docker publishes a port on every host interface unless the mapping names a
host IP, and the MCP write tools trust the decision IDs their caller sends.
So every Compose port binds 127.0.0.1; only the operator-facing entry points
(nginx, frontend, API) may be widened, deliberately, via MAIW_PUBLISH_ADDRESS.
The README quickstart and the notebook must name commands and ports that exist.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILES = sorted((REPO_ROOT / "deploy/compose").glob("docker-compose*.y*ml"))
LOOPBACK = "127.0.0.1:"
WIDENABLE = "${MAIW_PUBLISH_ADDRESS:-127.0.0.1}:"
OPERATOR_ENTRY_POINTS = {"backend", "frontend", "nginx"}
WEB = REPO_ROOT / "src/ui/web"


def _published_ports(path: Path):
    services = yaml.safe_load(path.read_text()).get("services") or {}
    for name, service in services.items():
        for mapping in (service or {}).get("ports") or []:
            yield name, str(mapping)


@pytest.mark.parametrize("path", COMPOSE_FILES, ids=lambda p: p.name)
def test_every_published_port_names_a_loopback_host_ip(path):
    offenders = []
    for service, mapping in _published_ports(path):
        if mapping.startswith(LOOPBACK):
            continue
        if (
            path.name == "docker-compose.dev.yaml"
            and service in OPERATOR_ENTRY_POINTS
            and mapping.startswith(WIDENABLE)
        ):
            continue
        offenders.append(f"{service}: {mapping}")
    assert offenders == []


def test_datastores_and_mcp_servers_cannot_be_widened():
    path = REPO_ROOT / "deploy/compose/docker-compose.dev.yaml"
    ports = list(_published_ports(path))
    services = {service for service, _ in ports}
    assert {"timescaledb", "redis", "minio", "mcp-equipment", "backend"} <= services
    for service, mapping in ports:
        if service not in OPERATOR_ENTRY_POINTS:
            assert mapping.startswith(LOOPBACK), f"{service}: {mapping}"
            assert "MAIW_PUBLISH_ADDRESS" not in mapping


def _start_script() -> str:
    return json.loads((WEB / "package.json").read_text())["scripts"]["start"]


def _proxy_default_port() -> int:
    proxy = (WEB / "src/setupProxy.js").read_text()
    match = re.search(r"MAIW_API_PROXY_TARGET \|\| 'http://localhost:(\d+)'", proxy)
    assert match, "setupProxy.js must default the API target to localhost"
    return int(match.group(1))


def test_ui_dev_server_binds_loopback_by_default():
    start = _start_script()
    assert "HOST=${HOST:-127.0.0.1}" in start
    assert "PORT=${PORT:-3001}" in start
    assert "0.0.0.0" not in start


def _quickstart() -> str:
    readme = (REPO_ROOT / "README.md").read_text()
    section = readme.split("## Quickstart", 1)[1].split("\n## ", 1)[0]
    return section


def test_readme_quickstart_commands_and_ports_match_the_code():
    quickstart = _quickstart()
    scripts = json.loads((WEB / "package.json").read_text())["scripts"]
    for script in re.findall(r"npm (?:run )?(\w[\w:-]*)", quickstart):
        if script not in {"install", "ci"}:
            assert script in scripts, f"README runs `npm {script}`, not in package.json"
    api_ports = {int(p) for p in re.findall(r"uvicorn maiw_api\.app:app[^\n]*--port (\d+)", quickstart)}
    assert api_ports == {_proxy_default_port()}
    ui_ports = {int(p) for p in re.findall(r"http://localhost:(\d+)", quickstart)}
    assert ui_ports == {3001}
    for command in re.findall(r"python -m maiw_world (\w+)", quickstart):
        main = (REPO_ROOT / "packages/maiw-world/maiw_world/__main__.py").read_text()
        assert f'add_parser("{command}"' in main
    assert (REPO_ROOT / "data/worlds/dc47-demo-v1/manifest.json").is_file()


def test_notebook_targets_the_documented_ports():
    nb = json.loads((REPO_ROOT / "notebooks/MAIW_v2_Getting_Started.ipynb").read_text())
    text = "".join("".join(cell.get("source", [])) for cell in nb["cells"])
    assert "npm run dev" not in text
    api = _proxy_default_port()
    assert set(map(int, re.findall(r"--port (\d+)", text))) == {api}
    assert set(map(int, re.findall(r'API_BASE = "http://localhost:(\d+)"', text))) == {api}
    assert set(map(int, re.findall(r"http://localhost:(\d+)/?(?!api)", text))) <= {3001, api}


def test_readme_quickstart_installs_requirements_before_packages():
    quickstart = _quickstart()
    requirements = quickstart.index("pip install -r requirements.txt")
    assert requirements < quickstart.index("pip install -e packages/")


def test_dev_server_proxy_is_setup_proxy_on_the_v3_api():
    # craco removes the CRA hook that loads src/setupProxy.js, so craco must
    # register it; otherwise the operator-header handling never runs.
    craco = (WEB / "craco.config.js").read_text()
    assert "require('./src/setupProxy')" in craco
    assert "createProxyMiddleware" not in craco
    proxy = (WEB / "src/setupProxy.js").read_text()
    package = json.loads((WEB / "package.json").read_text())
    deps = {**package.get("dependencies", {}), **package.get("devDependencies", {})}
    assert deps["http-proxy-middleware"].lstrip("^~").startswith("3.")
    # 3.x ignores the 2.x onProxyReq/onError/onProxyRes options.
    assert re.search(r"^\s+on: \{", proxy, re.M)
    for legacy in ("onProxyReq:", "onError:", "onProxyRes:"):
        assert legacy not in proxy
