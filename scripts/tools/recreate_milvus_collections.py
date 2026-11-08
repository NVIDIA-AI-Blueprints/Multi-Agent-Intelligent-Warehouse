#!/usr/bin/env python3
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
# See the License for the specific language governing permissions and limitations under the License.

"""
Drop and recreate Milvus vector collections for embedding dimension migration.

Use this after switching the embedding model (e.g. from 1024-d to 2048-d).
Drops: warehouse_documents, warehouse_docs, warehouse_docs_gpu.
Collections are recreated automatically on next backend start or first use.
Re-index by re-uploading or re-processing documents through the document pipeline.

Usage (from project root):
  python scripts/tools/recreate_milvus_collections.py
  # or with venv:
  . env/bin/activate && python scripts/tools/recreate_milvus_collections.py
"""

import os
import sys
from pathlib import Path

# Project root
project_root = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(project_root))

# Load env before importing pymilvus
from dotenv import load_dotenv
load_dotenv(project_root / ".env")

# Collections used by document pipeline and retrievers
COLLECTIONS = (
    "warehouse_documents",  # legacy document-embedding collection (indexer removed, #270)
    "warehouse_docs",       # MilvusRetriever
    "warehouse_docs_gpu",   # GPUMilvusRetriever
)


def main() -> int:
    """Drop existing Milvus collections. They will be recreated with 2048-dim on next use."""
    host = os.getenv("MILVUS_HOST", "localhost")
    port = os.getenv("MILVUS_PORT", "19530")

    try:
        from pymilvus import connections, utility
    except ImportError as e:
        print("Error: pymilvus is required. Install with: pip install pymilvus", file=sys.stderr)
        return 1

    print("Recreate Milvus collections (drop existing for 2048-dim migration)")
    print("=" * 60)
    print(f"Milvus: {host}:{port}")
    print()

    try:
        connections.connect(
            alias="default",
            host=host,
            port=str(port),
        )
        print("Connected to Milvus.")
    except Exception as e:
        print(f"Failed to connect to Milvus: {e}", file=sys.stderr)
        return 1

    dropped = []
    for name in COLLECTIONS:
        if utility.has_collection(name):
            try:
                utility.drop_collection(name)
                print(f"  Dropped: {name}")
                dropped.append(name)
            except Exception as e:
                print(f"  Failed to drop {name}: {e}", file=sys.stderr)
        else:
            print(f"  (skip, not present): {name}")

    try:
        connections.disconnect("default")
    except Exception:
        pass

    print()
    if dropped:
        print("Next steps:")
        print("  1. Restart the backend so it recreates collections with EMBEDDING_DIMENSION=2048.")
        print("  2. Re-index documents by re-uploading them via the Document Extraction UI/API,")
        print("     or by re-processing existing documents through the pipeline.")
    else:
        print("No collections were dropped. They will be created with 2048-dim on first use.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(main())
