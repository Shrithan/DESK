"""Regenerate JSON Schema files from the Pydantic contracts.

    python -m shared.contracts.export_schemas

A test fails if the committed schemas drift from the models.
"""

from __future__ import annotations

import json
from pathlib import Path

from shared.contracts.tilt import TILT_MODELS

SCHEMA_DIR = Path(__file__).parent / "schemas"


def render_schemas() -> dict[str, str]:
    return {
        f"{name}.schema.json": json.dumps(model.model_json_schema(), indent=2, sort_keys=True) + "\n"
        for name, model in TILT_MODELS.items()
    }


def main() -> None:
    SCHEMA_DIR.mkdir(exist_ok=True)
    for filename, text in render_schemas().items():
        (SCHEMA_DIR / filename).write_text(text)
        print(f"wrote {SCHEMA_DIR / filename}")


if __name__ == "__main__":
    main()
