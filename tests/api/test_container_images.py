"""
Container image hardening guards (NSPECT-NJMX-9GQU).

Static checks on the Dockerfiles that produce the published images
(``bpf-maiw-backend`` <- Dockerfile.backend, ``bpf-maiw-frontend`` <-
Dockerfile.frontend) so the remediated surface does not silently regress.
"""

from __future__ import annotations

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]


def _stages(dockerfile: str) -> dict[str, str]:
    """Split a Dockerfile into {stage_name: text} on ``FROM ... AS name``."""
    stages: dict[str, str] = {}
    current = None
    for line in dockerfile.splitlines():
        m = re.match(r"^FROM\s+\S+\s+AS\s+(\S+)", line, re.IGNORECASE)
        if m:
            current = m.group(1)
            stages[current] = ""
        if current is not None:
            stages[current] += line + "\n"
    return stages


def _instructions(text: str) -> str:
    """Dockerfile text without comment lines."""
    return "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )


def test_backend_base_is_python_313_trixie_pinned_by_digest():
    text = (REPO_ROOT / "Dockerfile.backend").read_text()
    m = re.search(r"^ARG PYTHON_IMAGE=(\S+)$", text, re.MULTILINE)
    assert m, "Dockerfile.backend must pin its base via ARG PYTHON_IMAGE"
    image = m.group(1)
    assert re.match(r"python:3\.13\.\d+-slim-trixie@sha256:[0-9a-f]{64}$", image)
    assert "/usr/local/lib/python3.13/site-packages" in text


def test_backend_runtime_stage_ships_no_extra_tools():
    stages = _stages((REPO_ROOT / "Dockerfile.backend").read_text())
    final = _instructions(stages["final"])
    assert "apt-get upgrade" in final
    assert "apt-get install" not in final
    for tool in ("curl", "wget", "git ", "poppler", "gcc", "g++"):
        assert tool not in final, tool
    assert "pip uninstall -y pip" in final
    healthcheck = re.search(r"^HEALTHCHECK.*\n.*$", final, re.MULTILINE)
    assert healthcheck and "urllib.request" in healthcheck.group(0)


def test_backend_image_carries_demo_runtime_dependencies():
    text = _instructions((REPO_ROOT / "Dockerfile.backend").read_text())
    for required in (
        "packages/maiw-contracts",
        "packages/maiw-world",
        "COPY mcp_servers/",
        "COPY data/worlds/",
    ):
        assert required in text, required


def test_frontend_runtime_is_static_nginx_without_node():
    stages = _stages((REPO_ROOT / "Dockerfile.frontend").read_text())
    assert set(stages) == {"build", "runtime"}
    runtime = _instructions(stages["runtime"])
    assert "apk upgrade --no-cache" in runtime
    assert "npm" not in runtime and "node_modules" not in runtime
    assert "COPY --from=build /app/build /usr/share/nginx/html" in runtime
    text = (REPO_ROOT / "Dockerfile.frontend").read_text()
    assert re.search(
        r"^ARG NODE_IMAGE=node:22\.\d+\.\d+-alpine\S*@sha256:[0-9a-f]{64}$",
        text,
        re.MULTILINE,
    )
    assert re.search(
        r"^ARG NGINX_IMAGE=nginxinc/nginx-unprivileged:\S+-alpine\S*@sha256:[0-9a-f]{64}$",
        text,
        re.MULTILINE,
    )


def test_frontend_proxy_never_forwards_operator_credential():
    conf = (REPO_ROOT / "deploy/docker/frontend-nginx.conf.template").read_text()
    assert 'proxy_set_header X-Maiw-Operator-Token "";' in conf
    assert "try_files $uri $uri/ /index.html;" in conf
    assert "${MAIW_API_UPSTREAM}" in conf
    # The template must be in the Docker build context.
    dockerignore = (REPO_ROOT / ".dockerignore").read_text()
    assert "!deploy/docker/frontend-nginx.conf.template" in dockerignore


def test_compose_backend_healthcheck_does_not_need_curl():
    compose = (REPO_ROOT / "deploy/compose/docker-compose.dev.yaml").read_text()
    backend = compose.split("\n  backend:\n", 1)[1].split("\n  # Frontend", 1)[0]
    healthcheck = re.search(r"^\s+test: (.*)$", backend, re.MULTILINE)
    assert healthcheck and "curl" not in healthcheck.group(1)
    assert "urllib.request" in healthcheck.group(1)
    frontend = compose.split("\n  frontend:\n", 1)[1].split("\n  # Nginx", 1)[0]
    assert '"3001:8080"' in frontend


def test_backend_image_ships_demo_evaluation_artifact():
    # GET /api/v1/demo/counterfactual/result reads this committed file; without
    # it the UI's "Control vs MAIW" panel shows "No evaluation data".
    text = (REPO_ROOT / "Dockerfile.backend").read_text()
    assert "COPY artifacts/demo/ ./artifacts/demo/" in text
    assert (REPO_ROOT / "artifacts/demo/labor_wave_control_vs_maiw.json").is_file()
