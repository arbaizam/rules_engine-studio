"""Manifest-backed custom-function access for Rules Engine Studio.

Authoring metadata comes from the engine-owned manifest built for the same
registry used by validation and row evaluation. Runtime calls continue through
the registered production implementations.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from rules_engine import FunctionRegistry

from . import authoring


def registry() -> FunctionRegistry:
    """Return the registry used by validation and production row evaluation."""
    return authoring.registry()


def specs() -> tuple[dict[str, Any], ...]:
    """Return active manifest function contracts in canonical name order."""
    return tuple(
        specification
        for specification in authoring.function_contracts()
        if specification["active_flag"]
    )


def spec(function_name: str) -> dict[str, Any]:
    """
    Return metadata for one registered function.

    Parameters
    ----------
    function_name : str
        Canonical registered function name.

    Returns
    -------
    dict[str, Any]
        Engine-owned manifest contract.
    """
    return next(
        specification
        for specification in authoring.function_contracts()
        if specification["function_name"] == function_name
    )


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
    available: Iterable[dict[str, Any]] = specs()
    if in_assignment is True:
        available = (
            specification
            for specification in available
            if specification["allowed_in_assignment_flag"]
        )
    elif in_assignment is False:
        available = (
            specification
            for specification in available
            if specification["allowed_in_condition_flag"]
        )
    return sorted(specification["function_name"] for specification in available)


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
    shared_registry = registry()
    specification = shared_registry.get_spec(function_name)
    implementation = shared_registry.get_implementation(function_name)
    return implementation(**specification.bind_args(authored_args))
