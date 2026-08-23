"""
Canonical YAML compilation, export, and ruleset validation.

Rules Engine Studio delegates document parsing, semantic validation, and YAML
rendering to ``rules_engine``. Studio-only diagnostics are limited to warnings
about input fields missing from the uploaded test data.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from rules_engine.compiler_yaml import YamlRulesetCompiler
from rules_engine.exceptions import RulesEngineError
from rules_engine.exporter_yaml import YamlRulesetExporter
from rules_engine.validator import RulesetValidator

from . import custom_functions
from .engine import compile_ruleset
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
    return YamlRulesetExporter().export_text(compile_ruleset(ruleset))


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
    compiled = YamlRulesetCompiler().compile_text(text)
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
    issues: list[Issue] = []
    try:
        compiled = compile_ruleset(ruleset)
    except (RulesEngineError, TypeError, ValueError) as exc:
        return [
            Issue(
                severity="error",
                where=ruleset.ruleset_id or "Ruleset",
                message=str(exc),
                check_name="RULESET_COMPILATION_FAILED",
            )
        ]

    result = RulesetValidator(custom_functions.registry()).validate(compiled)
    issues.extend(
        Issue(
            severity="error",
            where=issue.object_id,
            message=issue.message,
            check_name=issue.check_name,
        )
        for issue in result.issues
    )

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
    return issues


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
    "from_yaml",
    "has_errors",
    "renumber",
    "to_yaml",
    "validate",
]
