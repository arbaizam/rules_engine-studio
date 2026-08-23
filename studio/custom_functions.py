"""
Authoritative custom-function registry for Rules Engine Studio.

The studio registers the same metadata contracts and Python implementations
used by ``rules_engine``. Function selectors, argument editors, validation, and
row evaluation therefore share one registry instead of maintaining parallel
demo behavior.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from rules_engine.registry import CustomFunctionSpec, FunctionRegistry
from rules_engine.standard_functions import STANDARD_FUNCTION_SPECS, register_standard_functions

_REGISTRY = register_standard_functions(FunctionRegistry())
_SPECS: dict[str, CustomFunctionSpec] = {
    specification.function_name: specification for specification in STANDARD_FUNCTION_SPECS
}


def registry() -> FunctionRegistry:
    """Return the registry used by validation and production row evaluation."""
    return _REGISTRY


def specs() -> tuple[CustomFunctionSpec, ...]:
    """Return every active function contract in canonical name order."""
    return tuple(_SPECS[name] for name in sorted(_SPECS) if _SPECS[name].active_flag)


def spec(function_name: str) -> CustomFunctionSpec:
    """
    Return metadata for one registered function.

    Parameters
    ----------
    function_name : str
        Canonical registered function name.

    Returns
    -------
    CustomFunctionSpec
        Registered metadata contract.
    """
    return _REGISTRY.get_spec(function_name)


def names(*, in_assignment: bool | None = None) -> list[str]:
    """
    Return active function names permitted in the requested authoring context.

    Parameters
    ----------
    in_assignment : bool | None, default None
        ``True`` filters for assignment use, ``False`` filters for condition
        use, and ``None`` returns every active function.

    Returns
    -------
    list[str]
        Sorted canonical function names.
    """
    available: Iterable[CustomFunctionSpec] = specs()
    if in_assignment is True:
        available = (
            specification
            for specification in available
            if specification.allowed_in_assignment_flag
        )
    elif in_assignment is False:
        available = (
            specification
            for specification in available
            if specification.allowed_in_condition_flag
        )
    return sorted(specification.function_name for specification in available)


def call(function_name: str, authored_args: dict[str, Any]) -> Any:
    """
    Execute one registered function using its declared named-argument contract.

    Parameters
    ----------
    function_name : str
        Canonical registered function name.
    authored_args : dict[str, Any]
        Authored named arguments. Optional defaults are bound by the spec.

    Returns
    -------
    Any
        Function result.
    """
    specification = _REGISTRY.get_spec(function_name)
    implementation = _REGISTRY.get_implementation(function_name)
    return implementation(**specification.bind_args(authored_args))
