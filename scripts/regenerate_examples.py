"""Regenerate repository examples from the Studio's canonical demo project."""

from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> None:
    """Write compiler-produced YAML and structured sample rows."""
    project_root = Path(__file__).resolve().parents[1]
    sys.path.insert(0, str(project_root))
    from studio import sample_data, yaml_io

    examples = project_root / "examples"
    examples.mkdir(exist_ok=True)
    (examples / "loan_review.yaml").write_text(
        yaml_io.to_yaml(sample_data.demo_ruleset()),
        encoding="utf-8",
    )
    (examples / "loan_review_sample.json").write_text(
        json.dumps(sample_data.DEMO_ROWS, indent=2) + "\n",
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
