# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
"""
scripts/data/generate_all_sku_forecasts.py builds every forecasting estimator.

The S6709 (fixed seed) fix passed ``random_state`` to ``SVR``, which has no
such parameter, so constructing the engine raised ``TypeError`` and the data
generation script never ran.  Building the engine here makes a bad estimator
keyword fail in CORE CI, and pins a fixed seed on every estimator that takes one.
"""

from __future__ import annotations

import importlib.util
import warnings
from pathlib import Path

import pytest

pytest.importorskip("sklearn")
pytest.importorskip("pandas")
pytest.importorskip("asyncpg")

from sklearn.base import clone

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "scripts"
    / "data"
    / "generate_all_sku_forecasts.py"
)


def _load():
    spec = importlib.util.spec_from_file_location("generate_all_sku_forecasts", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    # The script silences all warnings at import; keep that out of the test session.
    with warnings.catch_warnings():
        spec.loader.exec_module(mod)
    return mod


def test_engine_builds_every_estimator():
    engine = _load().AllSKUForecastingEngine()

    expected = {
        "Random Forest",
        "Gradient Boosting",
        "Linear Regression",
        "Ridge Regression",
        "Support Vector Regression",
    }
    assert expected <= set(engine.models)
    for name, model in engine.models.items():
        assert model is not None, name
        # clone() round-trips get_params() through the constructor.
        clone(model)


def test_seeded_estimators_use_fixed_random_state():
    engine = _load().AllSKUForecastingEngine()

    for name, model in engine.models.items():
        params = model.get_params()
        if "random_state" in params:
            assert params["random_state"] == 42, name
