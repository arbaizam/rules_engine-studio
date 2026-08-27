"""
Session-state management for mutable authoring data.

Streamlit reruns the whole script on every interaction, so the draft lives in
``st.session_state`` and every widget writes straight back into the dataclasses.
Structural edits (add / delete / reorder) are queued during render and applied
after it, because mutating a list while iterating it in the same pass is how you
get a widget-key collision.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from decimal import Decimal
from typing import Any

import pandas as pd
import streamlit as st

from rules_engine import FunctionRegistry

from . import custom_functions, sample_data, type_compatibility
from .schema import TOLERANCE_OPERATORS, Ruleset, new_rule

DRAFT = "draft_ruleset"
SAMPLE = "sample_frame"
SELECTED = "selected_rule_uid"
ACTIONS = "pending_actions"
PREFIX = "column_prefix"


def init() -> None:
    if DRAFT not in st.session_state:
        st.session_state[DRAFT] = sample_data.demo_ruleset()
    if SAMPLE not in st.session_state:
        st.session_state[SAMPLE] = sample_data.demo_frame()
    if SELECTED not in st.session_state:
        rules = draft().rules
        st.session_state[SELECTED] = rules[0].uid if rules else None
    if ACTIONS not in st.session_state:
        st.session_state[ACTIONS] = []
    if PREFIX not in st.session_state:
        st.session_state[PREFIX] = "rules_engine"


# --------------------------------------------------------------------------
# accessors
# --------------------------------------------------------------------------


def draft() -> Ruleset:
    """Return the current mutable ruleset draft."""
    return st.session_state[DRAFT]


def set_draft(ruleset: Ruleset) -> None:
    """Replace the current draft and select its first rule."""
    normalize_ruleset(ruleset)
    st.session_state[DRAFT] = ruleset
    st.session_state[SELECTED] = ruleset.rules[0].uid if ruleset.rules else None


def frame() -> pd.DataFrame:
    """Return the current editable test-data frame."""
    return st.session_state[SAMPLE]


def set_frame(df: pd.DataFrame) -> None:
    """Replace the current test-data frame."""
    st.session_state[SAMPLE] = sample_data.normalize_frame(df)


def columns() -> list[str]:
    """Return test-data field names as strings."""
    return [str(c) for c in frame().columns]


def rows() -> list[dict[str, Any]]:
    """Return test data as Python row mappings for production evaluation."""
    return type_compatibility.normalized_records(frame())


def column_profiles() -> dict[str, type_compatibility.ValueProfile]:
    """Return value-derived semantic types for current sample columns."""
    return type_compatibility.column_profiles(frame())


def selected_rule():
    """Return the selected rule or the first available rule."""
    uid = st.session_state.get(SELECTED)
    for rule in draft().rules:
        if rule.uid == uid:
            return rule
    return draft().rules[0] if draft().rules else None


def select_rule(uid: str | None) -> None:
    """Select a rule by its transient widget identifier."""
    st.session_state[SELECTED] = uid


def functions() -> FunctionRegistry:
    """Return the authoritative function registry used by the studio."""
    return custom_functions.registry()


def normalize_ruleset(ruleset: Ruleset) -> None:
    """Repair legacy widget state that cannot be represented by active controls."""
    ordered = ruleset.ordered_rules()
    if len({rule.rule_order for rule in ordered}) != len(ordered):
        for index, rule in enumerate(ordered, start=1):
            rule.rule_order = index * 10
    for rule in ruleset.rules:
        for condition in rule.conditions.walk_conditions():
            if condition.operator not in TOLERANCE_OPERATORS:
                condition.tolerance_abs = Decimal(0)
            if condition.operator in {"is_null", "is_not_null"}:
                condition.error_on_null = False


# --------------------------------------------------------------------------
# deferred structural edits
# --------------------------------------------------------------------------


def queue(action: Callable[[], None]) -> None:
    """Queue a structural mutation until the current render completes."""
    st.session_state[ACTIONS].append(action)


def flush() -> bool:
    """Apply queued edits and return whether the caller should rerun."""
    pending = st.session_state.get(ACTIONS) or []
    if not pending:
        return False
    st.session_state[ACTIONS] = []
    for action in pending:
        action()
    return True


# --------------------------------------------------------------------------
# rule list operations
# --------------------------------------------------------------------------


def add_rule() -> None:
    """Append and select a uniquely named rule after the current sequence."""
    ruleset = draft()
    next_order = (max((r.rule_order for r in ruleset.rules), default=0)) + 10
    default_col = columns()[0] if columns() else ""
    rule = new_rule(next_order, default_col)
    rule.rule_id = _unique_rule_id(ruleset, f"rule_{len(ruleset.rules) + 1:03d}")
    ruleset.rules.append(rule)
    select_rule(rule.uid)


def duplicate_rule(uid: str) -> None:
    """Duplicate one rule with fresh metadata and widget identifiers."""
    ruleset = draft()
    for rule in list(ruleset.rules):
        if rule.uid != uid:
            continue
        clone = rule.copy()
        clone.rule_id = _unique_rule_id(ruleset, f"{rule.rule_id}_copy")
        clone.rule_order = _next_free_rule_order(ruleset, rule.rule_order + 1)
        ruleset.rules.append(clone)
        select_rule(clone.uid)
        return


def delete_rule(uid: str) -> None:
    """Delete one rule and select the first remaining rule."""
    ruleset = draft()
    ruleset.rules = [r for r in ruleset.rules if r.uid != uid]
    select_rule(ruleset.rules[0].uid if ruleset.rules else None)


def move_rule(uid: str, offset: int) -> None:
    """Swap ``rule_order`` with the neighbor in the requested direction."""
    ordered = draft().ordered_rules()
    if len({rule.rule_order for rule in ordered}) != len(ordered):
        for index, rule in enumerate(ordered, start=1):
            rule.rule_order = index * 10
    index = next((i for i, r in enumerate(ordered) if r.uid == uid), None)
    if index is None:
        return
    target = index + offset
    if target < 0 or target >= len(ordered):
        return
    a, b = ordered[index], ordered[target]
    a.rule_order, b.rule_order = b.rule_order, a.rule_order


def reorder_rules(uid_order: Sequence[str]) -> bool:
    """Apply a complete drag order while preserving the current order values."""
    ruleset = draft()
    ordered = ruleset.ordered_rules()
    current_uids = [rule.uid for rule in ordered]
    requested_uids = list(uid_order)
    if len(requested_uids) != len(current_uids) or set(requested_uids) != set(current_uids):
        return False
    if requested_uids == current_uids:
        return False

    order_values = [rule.rule_order for rule in ordered]
    if len(set(order_values)) != len(order_values):
        order_values = list(range(10, 10 * (len(ordered) + 1), 10))
    rules_by_uid = {rule.uid: rule for rule in ordered}
    for rule_order, uid in zip(order_values, requested_uids, strict=True):
        rules_by_uid[uid].rule_order = rule_order
    ruleset.rules = [rules_by_uid[uid] for uid in requested_uids]
    return True


def _unique_rule_id(ruleset: Ruleset, candidate: str) -> str:
    """Return a ruleset-unique rule identifier based on a candidate value."""
    existing = {r.rule_id for r in ruleset.rules}
    if candidate not in existing:
        return candidate
    counter = 2
    while f"{candidate}_{counter}" in existing:
        counter += 1
    return f"{candidate}_{counter}"


def _next_free_rule_order(ruleset: Ruleset, candidate: int) -> int:
    """Return the first unused rule order at or after a candidate value."""
    existing = {rule.rule_order for rule in ruleset.rules}
    while candidate in existing:
        candidate += 1
    return candidate
