"""Serializable rule model used by both Streamlit and the evaluator."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import uuid4


@dataclass
class FieldDefinition:
    key: str
    label: str
    data_type: str = "text"
    choices: list[str] = field(default_factory=list)
    example: Any = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "FieldDefinition":
        return cls(
            key=data["key"],
            label=data.get("label", data["key"].replace("_", " ").title()),
            data_type=data.get("data_type", "text"),
            choices=list(data.get("choices", [])),
            example=data.get("example"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Condition:
    field: str
    operator: str
    value: Any = None
    id: str = field(default_factory=lambda: uuid4().hex[:10])

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Condition":
        return cls(
            id=data.get("id", uuid4().hex[:10]),
            field=data.get("field", ""),
            operator=data.get("operator", "equals"),
            value=data.get("value"),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Outcome:
    kind: str = "Decision"
    value: str = "Review"
    message: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Outcome":
        return cls(
            kind=data.get("kind", "Decision"),
            value=data.get("value", "Review"),
            message=data.get("message", ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Rule:
    name: str
    description: str
    conditions: list[Condition]
    outcome: Outcome
    fields: list[FieldDefinition]
    match: str = "all"
    priority: int = 100
    enabled: bool = True
    id: str = field(default_factory=lambda: uuid4().hex)
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Rule":
        return cls(
            id=data.get("id", uuid4().hex),
            name=data.get("name", "Untitled rule"),
            description=data.get("description", ""),
            match=data.get("match", "all"),
            conditions=[Condition.from_dict(item) for item in data.get("conditions", [])],
            outcome=Outcome.from_dict(data.get("outcome", {})),
            fields=[FieldDefinition.from_dict(item) for item in data.get("fields", [])],
            priority=int(data.get("priority", 100)),
            enabled=bool(data.get("enabled", True)),
            tags=list(data.get("tags", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "match": self.match,
            "conditions": [condition.to_dict() for condition in self.conditions],
            "outcome": self.outcome.to_dict(),
            "fields": [definition.to_dict() for definition in self.fields],
            "priority": self.priority,
            "enabled": self.enabled,
            "tags": self.tags,
        }
