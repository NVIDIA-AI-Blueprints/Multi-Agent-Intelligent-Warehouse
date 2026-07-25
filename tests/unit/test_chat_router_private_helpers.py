# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
# http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Regression tests for chat router private helper wiring."""

import ast
import unittest
from pathlib import Path


CHAT_ROUTER_PATH = Path(__file__).resolve().parents[2] / "src" / "api" / "routers" / "chat.py"


class ChatRouterPrivateHelperTests(unittest.TestCase):
    def test_called_create_helpers_are_defined(self) -> None:
        """Ensure refactors do not leave runtime-only missing helper errors behind."""
        tree = ast.parse(CHAT_ROUTER_PATH.read_text())
        defined_helpers = set()
        called_helpers = set()

        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("_create_"):
                defined_helpers.add(node.name)
            elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) and node.func.id.startswith("_create_"):
                called_helpers.add(node.func.id)

        self.assertLessEqual(called_helpers, defined_helpers)


if __name__ == "__main__":
    unittest.main()
