"""Custom functions available to draft rules.

The real engine resolves ``CustomFunctionOperand`` against its own registry. The
studio keeps a parallel registry so authors can build and test rules that call
those functions before deployment.

Two ways to populate it:
  1. Register a Python callable here (fine for pure, cheap functions).
  2. Point the studio at the engine's registry -- see ``load_engine_registry``,
     which is a no-op until ``rules_engine`` is importable.

Studio functions must be pure and cheap: the preview evaluator calls them once
per row per condition, and an author will run them hundreds of times while
editing. Anything that hits a network or a warehouse belongs behind a stub here.
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Any, Callable

_REGISTRY: dict[str, Callable[..., Any]] = {}


def register(name: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    def wrap(fn: Callable[..., Any]) -> Callable[..., Any]:
        _REGISTRY[name] = fn
        return fn

    return wrap


def registry() -> dict[str, Callable[..., Any]]:
    return dict(_REGISTRY)


def names() -> list[str]:
    return sorted(_REGISTRY)


def call(name: str, args: list[Any]) -> Any:
    if name not in _REGISTRY:
        raise KeyError(f"Custom function '{name}' is not registered in the studio.")
    return _REGISTRY[name](*args)


def load_engine_registry() -> list[str]:
    """Merge in the real engine's custom functions when it is installed.

    Returns the names that were added. The attribute path below is a guess and
    needs confirming against the engine's registration API.
    """
    try:  # pragma: no cover - depends on the environment
        import rules_engine  # type: ignore

        source = getattr(rules_engine, "custom_function_registry", None)
        if callable(source):
            source = source()
        if isinstance(source, dict):
            added = [k for k in source if k not in _REGISTRY]
            _REGISTRY.update(source)
            return added
    except Exception:
        pass
    return []


# --------------------------------------------------------------------------
# demo functions -- replace with the real ones
# --------------------------------------------------------------------------


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return datetime.fromisoformat(str(value)).date()


@register("upper")
def _upper(value: Any) -> str:
    return str(value).upper()


@register("coalesce")
def _coalesce(*values: Any) -> Any:
    for value in values:
        if value is not None and value != "":
            return value
    return None


@register("concat")
def _concat(*values: Any) -> str:
    return "".join("" if v is None else str(v) for v in values)


@register("days_between")
def _days_between(start: Any, end: Any) -> int:
    return (_as_date(end) - _as_date(start)).days


@register("leaf_key")
def _leaf_key(*parts: Any) -> str:
    """Demo stand-in for the position-hierarchy leaf key builder."""
    return "/".join(str(p).strip().lower() for p in parts if p not in (None, ""))
