"""JSON import/export and local persistence for authored rulebooks."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .models import Rule


FORMAT_VERSION = 1


def serialize_rulebook(rules: list[Rule], name: str = "My rulebook") -> str:
    payload = {
        "format_version": FORMAT_VERSION,
        "name": name,
        "rules": [rule.to_dict() for rule in rules],
    }
    return json.dumps(payload, indent=2, ensure_ascii=False)


def deserialize_rulebook(content: str | bytes) -> tuple[str, list[Rule]]:
    if isinstance(content, bytes):
        content = content.decode("utf-8")
    payload: Any = json.loads(content)
    if isinstance(payload, list):
        return "Imported rulebook", [Rule.from_dict(item) for item in payload]
    if not isinstance(payload, dict) or not isinstance(payload.get("rules"), list):
        raise ValueError("Expected a rulebook object with a 'rules' list.")
    return payload.get("name", "Imported rulebook"), [Rule.from_dict(item) for item in payload["rules"]]


def save_rulebook(path: Path, rules: list[Rule], name: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = path.with_suffix(path.suffix + ".tmp")
    temporary_path.write_text(serialize_rulebook(rules, name), encoding="utf-8")
    temporary_path.replace(path)


def load_rulebook(path: Path) -> tuple[str, list[Rule]] | None:
    if not path.exists():
        return None
    return deserialize_rulebook(path.read_text(encoding="utf-8"))
