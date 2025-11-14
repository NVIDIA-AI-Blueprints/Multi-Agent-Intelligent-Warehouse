#!/usr/bin/env python3
"""
Repository Structure Migration Script

This script migrates the warehouse-operational-assistant repository
to match the NVIDIA AI Blueprints structure pattern.
"""

import os
import shutil
import re
from pathlib import Path
from typing import List, Tuple

# Base directory
BASE_DIR = Path(__file__).parent.parent

# File mappings: (source, destination, is_directory)
FILE_MAPPINGS = [
    # Source code to src/
    ("chain_server", "src/api", True),
    ("inventory_retriever", "src/retrieval", True),
    ("memory_retriever", "src/memory", True),
    ("adapters", "src/adapters", True),
    ("ui", "src/ui", True),
    
    # Deployment files to deploy/
    ("helm", "deploy/helm", True),
    ("docker-compose.yaml", "deploy/compose/docker-compose.yaml", False),
    ("docker-compose.dev.yaml", "deploy/compose/docker-compose.dev.yaml", False),
    ("docker-compose.monitoring.yaml", "deploy/compose/docker-compose.monitoring.yaml", False),
    ("docker-compose.gpu.yaml", "deploy/compose/docker-compose.gpu.yaml", False),
    ("docker-compose.rapids.yml", "deploy/compose/docker-compose.rapids.yml", False),
    ("docker-compose-nim-local.yaml", "deploy/compose/docker-compose-nim-local.yaml", False),
    ("docker-compose.ci.yml", "deploy/compose/docker-compose.ci.yml", False),
    ("docker-compose.versioned.yaml", "deploy/compose/docker-compose.versioned.yaml", False),
    
    # Guardrails config
    ("guardrails", "data/config/guardrails", True),
    
    # Monitoring (keep as is, but document)
    # ("monitoring", "monitoring", True),  # Keep in root for now
]

# Scripts to reorganize
SCRIPT_MAPPINGS = [
    # Setup scripts
    ("scripts/dev_up.sh", "scripts/setup/dev_up.sh", False),
    ("scripts/create_default_users.py", "scripts/setup/create_default_users.py", False),
    ("scripts/setup_monitoring.sh", "deploy/scripts/setup_monitoring.sh", False),
    ("scripts/setup_rapids_gpu.sh", "scripts/setup/setup_rapids_gpu.sh", False),
    ("scripts/setup_rapids_phase1.sh", "scripts/setup/setup_rapids_phase1.sh", False),
    ("scripts/fix_admin_password.py", "scripts/setup/fix_admin_password.py", False),
    ("scripts/update_admin_password.py", "scripts/setup/update_admin_password.py", False),
    
    # Data generation scripts
    ("scripts/generate_historical_demand.py", "scripts/data/generate_historical_demand.py", False),
    ("scripts/generate_synthetic_data.py", "scripts/data/generate_synthetic_data.py", False),
    ("scripts/generate_all_sku_forecasts.py", "scripts/data/generate_all_sku_forecasts.py", False),
    ("scripts/quick_demo_data.py", "scripts/data/quick_demo_data.py", False),
    ("scripts/run_data_generation.sh", "scripts/data/run_data_generation.sh", False),
    ("scripts/run_quick_demo.sh", "scripts/data/run_quick_demo.sh", False),
    
    # Forecasting scripts
    ("scripts/phase1_phase2_forecasting_agent.py", "scripts/forecasting/phase1_phase2_forecasting_agent.py", False),
    ("scripts/phase3_advanced_forecasting.py", "scripts/forecasting/phase3_advanced_forecasting.py", False),
    ("scripts/rapids_gpu_forecasting.py", "scripts/forecasting/rapids_gpu_forecasting.py", False),
    ("scripts/rapids_forecasting_agent.py", "scripts/forecasting/rapids_forecasting_agent.py", False),
    ("scripts/phase1_phase2_summary.py", "scripts/forecasting/phase1_phase2_summary.py", False),
    
    # Testing scripts
    ("scripts/test_chat_functionality.py", "scripts/testing/test_chat_functionality.py", False),
    ("scripts/test_rapids_forecasting.py", "scripts/testing/test_rapids_forecasting.py", False),
    
    # Tools
    ("scripts/migrate.py", "scripts/tools/migrate.py", False),
    ("scripts/simple_migrate.py", "scripts/tools/simple_migrate.py", False),
    ("scripts/debug_chat_response.py", "scripts/tools/debug_chat_response.py", False),
    ("scripts/benchmark_gpu_milvus.py", "scripts/tools/benchmark_gpu_milvus.py", False),
    ("scripts/gpu_demo.py", "scripts/tools/gpu_demo.py", False),
    ("scripts/mcp_gpu_integration_demo.py", "scripts/tools/mcp_gpu_integration_demo.py", False),
    ("scripts/build-and-tag.sh", "scripts/tools/build-and-tag.sh", False),
]

# Data files to move
DATA_MAPPINGS = [
    # Forecast JSON files
    ("all_sku_forecasts.json", "data/sample/forecasts/all_sku_forecasts.json", False),
    ("phase1_phase2_forecasts.json", "data/sample/forecasts/phase1_phase2_forecasts.json", False),
    ("phase3_advanced_forecasts.json", "data/sample/forecasts/phase3_advanced_forecasts.json", False),
    ("rapids_gpu_forecasts.json", "data/sample/forecasts/rapids_gpu_forecasts.json", False),
    ("phase1_phase2_summary.json", "data/sample/forecasts/phase1_phase2_summary.json", False),
    ("historical_demand_summary.json", "data/sample/forecasts/historical_demand_summary.json", False),
    
    # Test documents
    ("test_invoice.pdf", "data/sample/test_documents/test_invoice.pdf", False),
    ("test_invoice.png", "data/sample/test_documents/test_invoice.png", False),
    ("test_invoice.txt", "data/sample/test_documents/test_invoice.txt", False),
    ("test_status_fix.pdf", "data/sample/test_documents/test_status_fix.pdf", False),
    ("test_document.txt", "data/sample/test_documents/test_document.txt", False),
    
    # Other data files
    ("document_statuses.json", "data/sample/document_statuses.json", False),
    ("gpu_demo_results.json", "data/sample/gpu_demo_results.json", False),
    ("mcp_gpu_integration_results.json", "data/sample/mcp_gpu_integration_results.json", False),
    ("pipeline_test_results_*.json", "data/sample/pipeline_test_results/", False),  # Pattern
]

# Test files to move
TEST_FILE_PATTERNS = [
    ("test_*.py", "tests/unit/", False),  # Move test_*.py files to tests/unit/
]

# Import path replacements
IMPORT_REPLACEMENTS = [
    # Old imports -> New imports
    (r"from chain_server\.", "from src.api."),
    (r"import chain_server\.", "import src.api."),
    (r"from inventory_retriever\.", "from src.retrieval."),
    (r"import inventory_retriever\.", "import src.retrieval."),
    (r"from memory_retriever\.", "from src.memory."),
    (r"import memory_retriever\.", "import src.memory."),
    (r"from adapters\.", "from src.adapters."),
    (r"import adapters\.", "import src.adapters."),
]


def create_directories():
    """Create all necessary directories."""
    directories = [
        "src/api",
        "src/retrieval",
        "src/memory",
        "src/adapters",
        "src/ui",
        "deploy/compose",
        "deploy/helm",
        "deploy/scripts",
        "deploy/kubernetes",
        "data/sample/forecasts",
        "data/sample/test_documents",
        "data/config/guardrails",
        "scripts/setup",
        "scripts/data",
        "scripts/forecasting",
        "scripts/testing",
        "scripts/tools",
        "notebooks/forecasting",
        "notebooks/retrieval",
        "notebooks/demos",
        "tests/unit",
        "data/sample/pipeline_test_results",
    ]
    
    for directory in directories:
        dir_path = BASE_DIR / directory
        dir_path.mkdir(parents=True, exist_ok=True)
        print(f"Created directory: {directory}")


def move_files(mappings: List[Tuple[str, str, bool]]):
    """Move files and directories to new locations."""
    for source, destination, is_directory in mappings:
        source_path = BASE_DIR / source
        dest_path = BASE_DIR / destination
        
        if not source_path.exists():
            print(f"Warning: Source not found: {source}")
            continue
        
        # Create destination directory if needed
        if is_directory:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
        else:
            dest_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Move the file/directory
        if source_path.is_dir():
            if dest_path.exists():
                print(f"Warning: Destination exists, merging: {destination}")
                # Merge directories
                for item in source_path.iterdir():
                    shutil.move(str(item), str(dest_path / item.name))
                source_path.rmdir()
            else:
                shutil.move(str(source_path), str(dest_path))
        else:
            shutil.move(str(source_path), str(dest_path))
        
        print(f"Moved: {source} -> {destination}")


def move_pattern_files(pattern: str, destination: str):
    """Move files matching a pattern."""
    import glob
    source_dir = BASE_DIR
    matches = list(source_dir.glob(pattern))
    
    dest_dir = BASE_DIR / destination
    dest_dir.mkdir(parents=True, exist_ok=True)
    
    for match in matches:
        if match.is_file():
            dest_path = dest_dir / match.name
            shutil.move(str(match), str(dest_path))
            print(f"Moved pattern match: {match.name} -> {destination}")


def update_imports_in_file(file_path: Path):
    """Update import statements in a Python file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # Apply import replacements
        for old_pattern, new_pattern in IMPORT_REPLACEMENTS:
            content = re.sub(old_pattern, new_pattern, content)
        
        # Update sys.path modifications if any
        content = re.sub(
            r'sys\.path\.append\([^)]*chain_server[^)]*\)',
            lambda m: m.group(0).replace('chain_server', 'src/api'),
            content
        )
        
        if content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"Updated imports in: {file_path.relative_to(BASE_DIR)}")
            return True
    except Exception as e:
        print(f"Error updating {file_path}: {e}")
    return False


def update_dockerfile_paths(file_path: Path):
    """Update paths in Dockerfiles."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # Update COPY commands
        replacements = [
            (r'COPY chain_server/', 'COPY src/api/'),
            (r'COPY inventory_retriever/', 'COPY src/retrieval/'),
            (r'COPY memory_retriever/', 'COPY src/memory/'),
            (r'COPY adapters/', 'COPY src/adapters/'),
            (r'COPY ui/', 'COPY src/ui/'),
            (r'COPY requirements\.txt', 'COPY requirements.txt'),
        ]
        
        for old_pattern, new_pattern in replacements:
            content = re.sub(old_pattern, new_pattern, content)
        
        # Update WORKDIR if needed
        if 'WORKDIR' in content and '/chain_server' in content:
            content = re.sub(r'WORKDIR /chain_server', 'WORKDIR /src/api', content)
        
        if content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"Updated Dockerfile: {file_path.relative_to(BASE_DIR)}")
            return True
    except Exception as e:
        print(f"Error updating Dockerfile {file_path}: {e}")
    return False


def update_docker_compose_paths(file_path: Path):
    """Update paths in docker-compose files."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # Update volume mounts and build contexts
        replacements = [
            (r'\./chain_server:', './src/api:'),
            (r'\./inventory_retriever:', './src/retrieval:'),
            (r'\./memory_retriever:', './src/memory:'),
            (r'\./adapters:', './src/adapters:'),
            (r'\./ui:', './src/ui:'),
            (r'context: \./(chain_server|inventory_retriever|memory_retriever|adapters|ui)', 
             lambda m: f"context: ./src/{m.group(1).replace('chain_server', 'api').replace('inventory_retriever', 'retrieval').replace('memory_retriever', 'memory')}"),
        ]
        
        for old_pattern, new_pattern in replacements:
            if callable(new_pattern):
                content = re.sub(old_pattern, new_pattern, content)
            else:
                content = re.sub(old_pattern, new_pattern, content)
        
        if content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"Updated docker-compose: {file_path.relative_to(BASE_DIR)}")
            return True
    except Exception as e:
        print(f"Error updating docker-compose {file_path}: {e}")
    return False


def update_script_paths(file_path: Path):
    """Update paths in shell scripts."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            content = f.read()
        
        original_content = content
        
        # Update paths in scripts
        replacements = [
            (r'chain_server/', 'src/api/'),
            (r'inventory_retriever/', 'src/retrieval/'),
            (r'memory_retriever/', 'src/memory/'),
            (r'adapters/', 'src/adapters/'),
            (r'ui/', 'src/ui/'),
            (r'docker-compose\.yaml', 'deploy/compose/docker-compose.yaml'),
            (r'docker-compose\.dev\.yaml', 'deploy/compose/docker-compose.dev.yaml'),
        ]
        
        for old_pattern, new_pattern in replacements:
            content = re.sub(old_pattern, new_pattern, content)
        
        if content != original_content:
            with open(file_path, 'w', encoding='utf-8') as f:
                f.write(content)
            print(f"Updated script: {file_path.relative_to(BASE_DIR)}")
            return True
    except Exception as e:
        print(f"Error updating script {file_path}: {e}")
    return False


def update_all_files():
    """Update imports and paths in all relevant files."""
    print("\nUpdating imports and paths in files...")
    
    # Update Python files
    for py_file in BASE_DIR.rglob("*.py"):
        if py_file.is_file() and not py_file.name.startswith('.'):
            update_imports_in_file(py_file)
    
    # Update Dockerfiles
    for dockerfile in BASE_DIR.glob("Dockerfile*"):
        if dockerfile.is_file():
            update_dockerfile_paths(dockerfile)
    
    # Update docker-compose files
    for compose_file in (BASE_DIR / "deploy" / "compose").glob("*.yaml"):
        if compose_file.is_file():
            update_docker_compose_paths(compose_file)
    for compose_file in (BASE_DIR / "deploy" / "compose").glob("*.yml"):
        if compose_file.is_file():
            update_docker_compose_paths(compose_file)
    
    # Update shell scripts
    for script_file in BASE_DIR.rglob("*.sh"):
        if script_file.is_file():
            update_script_paths(script_file)


def main():
    """Main migration function."""
    print("=" * 60)
    print("Repository Structure Migration")
    print("=" * 60)
    
    # Step 1: Create directories
    print("\nStep 1: Creating directory structure...")
    create_directories()
    
    # Step 2: Move files
    print("\nStep 2: Moving files...")
    move_files(FILE_MAPPINGS)
    move_files(SCRIPT_MAPPINGS)
    move_files(DATA_MAPPINGS)
    
    # Step 3: Move pattern-based files
    print("\nStep 3: Moving pattern-based files...")
    move_pattern_files("pipeline_test_results_*.json", "data/sample/pipeline_test_results")
    move_pattern_files("test_*.py", "tests/unit")
    
    # Step 4: Update imports and paths
    print("\nStep 4: Updating imports and paths...")
    update_all_files()
    
    print("\n" + "=" * 60)
    print("Migration completed!")
    print("=" * 60)
    print("\nNext steps:")
    print("1. Review the changes")
    print("2. Test the application")
    print("3. Update documentation")
    print("4. Commit the changes")


if __name__ == "__main__":
    main()

