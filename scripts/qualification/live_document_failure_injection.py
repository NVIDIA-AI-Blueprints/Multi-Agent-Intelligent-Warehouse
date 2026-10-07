# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
v2.0.1 live document-path failure injection (audit P1-05, spec §49).

Each case runs in a fresh interpreter (NIMConfig reads its environment at
import time) that starts maiw_api.app:app's real lifespan and calls the
shipped document stages, which reach models only via ModelGateway:

    judge_real_provider   LargeLLMJudge with the configured provider
    judge_bad_key         same, NVIDIA_API_KEY replaced by an invalid value
    judge_no_key          same, NVIDIA_API_KEY empty
    judge_provider_down   same, provider URL pointed at a closed local port
    ocr_vision            NeMoOCRService on an image (Modality.IMAGE)

Prints one JSON object. Secrets are never printed. Expected: only
judge_real_provider yields a classification (from an approved Nemotron
model); every other case is a typed DocumentInferenceUnavailable and nothing
ever returns a synthetic APPROVE.
"""

from __future__ import annotations

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]

_CASE = r"""
import asyncio, json, sys
sys.path.insert(0, sys.argv[2])
async def main(case):
    from maiw_api.app import app
    from src.api.agents.document.model_gateway_adapter import DocumentInferenceUnavailable
    out = {"case": case}
    async with app.router.lifespan_context(app):
        gw = app.state.runtime.model_gateway
        try:
            if case == "ocr_vision":
                from PIL import Image
                from src.api.agents.document.ocr.nemo_ocr import NeMoOCRService
                await NeMoOCRService().extract_text([Image.new("RGB", (64, 32), "white")], {})
                out["result"] = "unexpected success"
            else:
                from src.api.agents.document.validation.large_llm_judge import LargeLLMJudge
                r = await LargeLLMJudge().evaluate_document(
                    {"extracted_fields": {"invoice_number": {"value": "INV-7781"},
                                          "total": {"value": 1250.00}}},
                    {}, "invoice")
                cap = gw.registry.get_by_id(r.judge_model)
                out.update({"result": "classification", "decision": r.decision,
                            "decision_kind": r.decision_kind, "judge_model": r.judge_model,
                            "generation": cap.generation if cap else None})
        except DocumentInferenceUnavailable as e:
            out.update({"result": "typed_failure", "code": e.code, "stage": e.stage})
        except Exception as e:
            out.update({"result": "untyped_error", "error": type(e).__name__})
    print(json.dumps(out))
asyncio.run(main(sys.argv[1]))
"""


def _run(case: str, env_overrides: dict[str, str]) -> dict:
    env = {**os.environ, **env_overrides}
    proc = subprocess.run(
        [sys.executable, "-c", _CASE, case, str(REPO_ROOT)],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=400,
    )
    lines = [ln for ln in proc.stdout.splitlines() if ln.startswith("{")]
    if not lines:
        return {"case": case, "result": "harness_error", "rc": proc.returncode}
    return json.loads(lines[-1])


def main() -> None:
    results = [
        _run("judge_real_provider", {}),
        _run("judge_bad_key", {"NVIDIA_API_KEY": "invalid-key-v201-injection"}),
        _run("judge_no_key", {"NVIDIA_API_KEY": ""}),
        _run(
            "judge_provider_down",
            {"LLM_NIM_URL": "http://127.0.0.1:9/v1", "MAIW_NIM_BASE_URL": "http://127.0.0.1:9/v1"},
        ),
        _run("ocr_vision", {}),
    ]
    synthetic_approve = any(
        r.get("decision") == "APPROVE" and r["case"] != "judge_real_provider"
        for r in results
    )
    print(json.dumps({"results": results, "synthetic_approve_on_failure": synthetic_approve}))


if __name__ == "__main__":
    main()
