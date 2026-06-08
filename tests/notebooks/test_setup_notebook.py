"""Validate structure of the setup notebook."""

import json
from pathlib import Path

NOTEBOOK_PATH = Path("notebooks/setup/complete_setup_guide.ipynb")

REQUIRED_SECTIONS = [
    "Prerequisites",
    "Repository Setup",
    "Environment Setup",
    "NVIDIA API Key",
    "Database Setup",
    "Verification",
]


def test_notebook_structure() -> None:
    """Notebook has expected cells and documentation sections."""
    with open(NOTEBOOK_PATH, encoding="utf-8") as handle:
        notebook = json.load(handle)

    assert notebook["cells"], "Notebook should have cells"

    markdown_cells = [
        cell for cell in notebook["cells"] if cell["cell_type"] == "markdown"
    ]
    code_cells = [cell for cell in notebook["cells"] if cell["cell_type"] == "code"]
    assert markdown_cells, "Notebook should have markdown cells"
    assert code_cells, "Notebook should have code cells"

    content = " ".join("".join(cell.get("source", [])) for cell in notebook["cells"])
    for section in REQUIRED_SECTIONS:
        assert section.lower() in content.lower(), f"Missing section: {section}"
