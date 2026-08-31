#!/usr/bin/env bash
# SPDX-FileCopyrightText: Copyright (c) 2025 NVIDIA CORPORATION & AFFILIATES. All rights reserved.
# SPDX-License-Identifier: Apache-2.0
#
# MAIW v2 Demo World Setup
# Generates the canonical DC-47 Warehouse World DataPack (or validates the existing one).
#
# Usage:
#   ./scripts/setup_demo_world.sh
#
# Environment overrides:
#   MAIW_WORLD_CONFIG   path to world config YAML  (default: data/world-configs/dc47-demo.yaml)
#   MAIW_WORLD_OUTPUT   path to DataPack output dir (default: data/worlds/dc47-demo-v1)

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CONFIG="${MAIW_WORLD_CONFIG:-data/world-configs/dc47-demo.yaml}"
OUTPUT="${MAIW_WORLD_OUTPUT:-data/worlds/dc47-demo-v1}"

echo ""
echo "MAIW v2 Demo World Setup"
echo "========================"
echo ""

# ── Environment check ─────────────────────────────────────────────────────────

if ! command -v python3 &>/dev/null; then
  echo "ERROR: python3 not found"
  exit 1
fi

if ! python3 -c "import maiw_world" &>/dev/null; then
  echo "ERROR: maiw_world package not importable."
  echo "       Run: pip install -e packages/maiw-world"
  exit 1
fi

if [[ -z "${NVIDIA_API_KEY:-}" ]]; then
  echo "WARNING: NVIDIA_API_KEY is not set."
  echo "         Set it before launching Demo Mode:"
  echo "           export NVIDIA_API_KEY=nvapi-..."
  echo ""
fi

cd "$REPO_ROOT"

# ── DataPack setup ────────────────────────────────────────────────────────────

if [[ -d "$OUTPUT" && -f "$OUTPUT/manifest.json" ]]; then
  echo "DataPack already exists: $OUTPUT"
  echo "Running validation..."
  echo ""
  python3 -m maiw_world validate "$OUTPUT"
  echo ""
  echo "To regenerate: python3 -m maiw_world generate --config $CONFIG --output $OUTPUT --overwrite"
else
  echo "Generating Warehouse World..."
  echo "Config: $CONFIG"
  echo "Output: $OUTPUT"
  echo ""
  python3 -m maiw_world generate --config "$CONFIG" --output "$OUTPUT"
fi

echo ""
echo "Next steps:"
echo "  Start Demo Mode:  ./scripts/start_demo_mode.sh"
echo "  Open Demo UI:     http://localhost:3001/demo"
echo ""
echo "Done."
