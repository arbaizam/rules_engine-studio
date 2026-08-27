"""Engine-owned authoring contract adapter for Rules Engine Studio.

The adapter constructs one standard function registry and uses it for the
public authoring manifest, compilation, semantic validation, and runtime
evaluation.  Studio modules consume this narrow boundary instead of importing
engine contract constants or function specifications independently.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Any

from rules_engine import (
    FunctionRegistry,
    RulesetValidator,
    YamlRulesetCompiler,
    build_authoring_manifest,
    register_standard_functions,
)
from rules_engine.models import Ruleset as CompiledRuleset
from rules_engine.models import ValidationResult

_REGISTRY = register_standard_functions(FunctionRegistry())
_COMPILER = YamlRulesetCompiler()
_VALIDATOR = RulesetValidator(_REGISTRY)


def registry() -> FunctionRegistry:
    """Return the registry shared by the manifest, validator, and runtime."""
    return _REGISTRY


@lru_cache(maxsize=1)
def manifest() -> dict[str, Any]:
    """Return the cached public authoring manifest for the shared registry."""
    return build_authoring_manifest(_REGISTRY)


def compile_payload(payload: Any) -> CompiledRuleset:
    """Compile one canonical authoring payload with the production compiler."""
    return _COMPILER.compile_payload(payload)


def compile_text(text: str) -> CompiledRuleset:
    """Compile canonical YAML text with the production compiler."""
    return _COMPILER.compile_text(text)


def validate(ruleset: CompiledRuleset) -> ValidationResult:
    """Validate compiled metadata with the shared production registry."""
    return _VALIDATOR.validate(ruleset)


def comparison_operators() -> tuple[dict[str, Any], ...]:
    """Return comparison operator contracts in engine-defined order."""
    return tuple(manifest()["comparison_operators"])


def logical_operators() -> tuple[str, ...]:
    """Return canonical logical operators in engine-defined order."""
    return tuple(manifest()["logical_operators"])


def operand_kinds() -> tuple[str, ...]:
    """Return canonical operand kinds in engine-defined order."""
    return tuple(manifest()["operand_kinds"])


def literal_type_hints() -> tuple[dict[str, Any], ...]:
    """Return canonical scalar literal hints and their accepted aliases."""
    return tuple(manifest()["literal_type_hints"])


def canonical_literal_type_hint(type_hint: str) -> str:
    """Return the canonical scalar hint for a canonical name or alias."""
    for contract in literal_type_hints():
        if type_hint == contract["name"] or type_hint in contract["aliases"]:
            return str(contract["name"])
    return type_hint


def function_argument_type_hints() -> tuple[str, ...]:
    """Return every engine-supported function argument type hint."""
    return tuple(manifest()["function_argument_type_hints"])


def fixed_function_return_type_hints() -> tuple[str, ...]:
    """Return every fixed engine-supported function return type hint."""
    return tuple(manifest()["function_return_type_hints"]["fixed"])


def dynamic_function_return_type_templates() -> tuple[str, ...]:
    """Return engine-supported dynamic function return type templates."""
    return tuple(manifest()["function_return_type_hints"]["dynamic_templates"])


def function_contracts() -> tuple[dict[str, Any], ...]:
    """Return registered function contracts in engine-defined order."""
    return tuple(manifest()["functions"])


__all__ = [
    "canonical_literal_type_hint",
    "comparison_operators",
    "compile_payload",
    "compile_text",
    "dynamic_function_return_type_templates",
    "fixed_function_return_type_hints",
    "function_argument_type_hints",
    "function_contracts",
    "literal_type_hints",
    "logical_operators",
    "manifest",
    "operand_kinds",
    "registry",
    "validate",
]
