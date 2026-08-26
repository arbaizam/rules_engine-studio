"""
Canonical YAML compilation, export, and ruleset validation.

Rules Engine Studio delegates document parsing, semantic validation, and YAML
rendering to ``rules_engine``. Studio-only diagnostics are limited to warnings
about input fields missing from the uploaded test data.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

import yaml
from rules_engine.exceptions import RulesEngineError
from rules_engine.exporter_yaml import YamlRulesetExporter

from . import authoring
from .schema import Ruleset, referenced_columns


def to_yaml(ruleset: Ruleset) -> str:
    """
    Compile and export a studio draft as canonical rules-engine YAML.

    Parameters
    ----------
    ruleset : Ruleset
        Mutable studio draft.

    Returns
    -------
    str
        Canonical YAML accepted by ``YamlRulesetCompiler``.
    """
    return YamlRulesetExporter().export_text(authoring.compile_payload(ruleset.to_dict()))


def from_yaml(text: str) -> Ruleset:
    """
    Compile canonical YAML and restore a mutable studio draft.

    Parameters
    ----------
    text : str
        Canonical ruleset YAML.

    Returns
    -------
    Ruleset
        Mutable studio draft.
    """
    compiled = authoring.compile_text(text)
    return Ruleset.from_dict(YamlRulesetExporter().export_payload(compiled))


@dataclass(frozen=True)
class Issue:
    """
    Presentation form for one engine or sample-data diagnostic.

    Parameters
    ----------
    severity : str
        ``error`` for engine failures or ``warning`` for sample-data coverage.
    where : str
        Object identifier associated with the diagnostic.
    message : str
        Human-readable diagnostic text.
    check_name : str
        Stable engine check identifier.
    """

    severity: str
    where: str
    message: str
    check_name: str = ""

    def __str__(self) -> str:
        """Return a compact diagnostic string for logs and tests."""
        return f"{self.where}: {self.message}"


@dataclass(frozen=True)
class YamlSnapshot:
    """One compiler-backed live view of the current mutable draft."""

    document: str
    issues: tuple[Issue, ...]
    compiled: bool

    @property
    def exportable(self) -> bool:
        """Return whether the snapshot passed every production error check."""
        return not any(issue.severity == "error" for issue in self.issues)

    @property
    def error_count(self) -> int:
        """Return the number of diagnostics that block canonical export."""
        return sum(issue.severity == "error" for issue in self.issues)


def build_snapshot(
    ruleset: Ruleset,
    columns: Iterable[str] = (),
) -> YamlSnapshot:
    """
    Compile, validate, and render one live YAML snapshot of a mutable draft.

    Drafts rejected by the production compiler still receive a best-effort
    YAML representation, so authoring feedback never disappears while a field
    is temporarily incomplete.
    """
    payload = ruleset.to_dict()
    compiled, issues = _compile_and_validate(ruleset, columns)
    if compiled is None:
        return YamlSnapshot(
            document=_draft_yaml(payload),
            issues=tuple(issues),
            compiled=False,
        )

    try:
        document = YamlRulesetExporter().export_text(compiled)
    except (RulesEngineError, TypeError, ValueError) as exc:
        issues.append(
            Issue(
                severity="error",
                where=ruleset.ruleset_id or "Ruleset",
                message=str(exc),
                check_name="RULESET_EXPORT_FAILED",
            )
        )
        document = _draft_yaml(payload)
    return YamlSnapshot(document=document, issues=tuple(issues), compiled=True)


def validate(
    ruleset: Ruleset,
    columns: Iterable[str] = (),
    functions: Iterable[str] = (),
) -> list[Issue]:
    """
    Validate a draft through the production compiler and semantic validator.

    Parameters
    ----------
    ruleset : Ruleset
        Mutable studio draft.
    columns : Iterable[str], default ()
        Test-data fields used only for authoring coverage warnings.
    functions : Iterable[str], default ()
        Retained for API compatibility. Function validation uses the
        authoritative registry.

    Returns
    -------
    list[Issue]
        Engine errors followed by sample-data coverage warnings.
    """
    del functions
    _, issues = _compile_and_validate(ruleset, columns)
    return issues


def _compile_and_validate(
    ruleset: Ruleset,
    columns: Iterable[str],
) -> tuple[Any | None, list[Issue]]:
    """Return one compiled draft and its production and sample-data diagnostics."""
    try:
        compiled = authoring.compile_payload(ruleset.to_dict())
    except (RulesEngineError, TypeError, ValueError) as exc:
        return None, [
            Issue(
                severity="error",
                where=ruleset.ruleset_id or "Ruleset",
                message=str(exc),
                check_name="RULESET_COMPILATION_FAILED",
            )
        ]

    result = authoring.validate(compiled)
    issues = [
        Issue(
            severity="error",
            where=issue.object_id,
            message=issue.message,
            check_name=issue.check_name,
        )
        for issue in result.issues
    ]

    available = {str(column) for column in columns}
    if available:
        for field_name in sorted(referenced_columns(ruleset) - available):
            issues.append(
                Issue(
                    severity="warning",
                    where=ruleset.ruleset_id,
                    message=f"Input field {field_name!r} is absent from the current test data.",
                    check_name="TEST_DATA_FIELD_MISSING",
                )
            )
    return compiled, issues


def _draft_yaml(payload: Mapping[str, Any]) -> str:
    """Render compiler-rejected authoring data with safe, portable YAML values."""
    return yaml.safe_dump(
        _yaml_safe(payload),
        sort_keys=False,
        allow_unicode=True,
        default_flow_style=False,
    )


def _yaml_safe(value: Any) -> Any:
    """Normalize mutable authoring values for PyYAML's safe dumper."""
    if isinstance(value, Mapping):
        return {str(key): _yaml_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_yaml_safe(item) for item in value]
    if isinstance(value, set):
        return [_yaml_safe(item) for item in sorted(value, key=str)]
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (date, datetime, time)):
        return value.isoformat()
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def has_errors(issues: list[Issue]) -> bool:
    """Return whether any diagnostic blocks canonical export or evaluation."""
    return any(issue.severity == "error" for issue in issues)


def renumber(ruleset: Ruleset, step: int = 10) -> None:
    """
    Rewrite rule order values to a deterministic gapped sequence.

    Parameters
    ----------
    ruleset : Ruleset
        Mutable studio draft.
    step : int, default 10
        Positive gap between adjacent rule order values.
    """
    for index, rule in enumerate(ruleset.ordered_rules(), start=1):
        rule.rule_order = index * step


__all__ = [
    "Issue",
    "YamlSnapshot",
    "build_snapshot",
    "from_yaml",
    "has_errors",
    "renumber",
    "to_yaml",
    "validate",
]
