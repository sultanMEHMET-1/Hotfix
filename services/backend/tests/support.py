"""Shared test-root builder for the per-workflow contracts layout.

A test root holds only the schema files plus one workflow's definition and selector map, so it can
never pick up the repository's real workflows or selector maps by accident.
"""

import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[3]


def make_root(root: Path, workflow_id: str, definition: dict, selector_map: dict) -> Path:
    """Create contracts/ under root and return the path of the workflow's selector map."""
    contracts = root / "contracts"
    contracts.mkdir(parents=True, exist_ok=True)
    for schema in (ROOT / "contracts").glob("*.schema.json"):
        shutil.copy(schema, contracts / schema.name)
    (contracts / "workflows").mkdir(exist_ok=True)
    (contracts / "selectors").mkdir(exist_ok=True)
    (contracts / "workflows" / f"{workflow_id}.json").write_text(json.dumps(definition))
    path = contracts / "selectors" / f"{workflow_id}.json"
    path.write_text(json.dumps(selector_map))
    return path
