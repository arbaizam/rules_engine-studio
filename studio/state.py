"""Session state: one draft ruleset, one sample dataset, one selection.

Streamlit reruns the whole script on every interaction, so the draft lives in
``st.session_state`` and every widget writes straight back into the dataclasses.
Structural edits (add / delete / reorder) are queued during render and applied
after it, because mutating a list while iterating it in the same pass is how you
get a widget-key collision.
"""

from __future__ import annotations

from typing import Any, Callable

import pandas as pd
import streamlit as st

from . import custom_functions, sample_data
from .schema import Ruleset, new_rule

DRAFT = "draft_ruleset"
SAMPLE = "sample_frame"
SELECTED = "selected_rule_uid"
ACTIONS = "pending_actions"
PREFIX = "column_prefix"
FULL_AUDIT = "full_audit"


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
    if FULL_AUDIT not in st.session_state:
        st.session_state[FULL_AUDIT] = False
    custom_functions.load_engine_registry()


# --------------------------------------------------------------------------
# accessors
# --------------------------------------------------------------------------


def draft() -> Ruleset:
    return st.session_state[DRAFT]


def set_draft(ruleset: Ruleset) -> None:
    st.session_state[DRAFT] = ruleset
    st.session_state[SELECTED] = ruleset.rules[0].uid if ruleset.rules else None


def frame() -> pd.DataFrame:
    return st.session_state[SAMPLE]


def set_frame(df: pd.DataFrame) -> None:
    st.session_state[SAMPLE] = df


def columns() -> list[str]:
    return [str(c) for c in frame().columns]


def rows() -> list[dict[str, Any]]:
    return frame().to_dict("records")


def selected_rule():
    uid = st.session_state.get(SELECTED)
    for rule in draft().rules:
        if rule.uid == uid:
            return rule
    return draft().rules[0] if draft().rules else None


def select_rule(uid: str | None) -> None:
    st.session_state[SELECTED] = uid


def functions() -> dict[str, Callable[..., Any]]:
    return custom_functions.registry()


# --------------------------------------------------------------------------
# deferred structural edits
# --------------------------------------------------------------------------


def queue(action: Callable[[], None]) -> None:
    st.session_state[ACTIONS].append(action)


def flush() -> bool:
    """Apply queued edits. Returns True when the caller should rerun."""
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
    ruleset = draft()
    next_order = (max((r.rule_order for r in ruleset.rules), default=0)) + 10
    default_col = columns()[0] if columns() else ""
    rule = new_rule(next_order, default_col)
    rule.rule_id = _unique_rule_id(ruleset, f"rule_{len(ruleset.rules) + 1:03d}")
    ruleset.rules.append(rule)
    select_rule(rule.uid)


def duplicate_rule(uid: str) -> None:
    ruleset = draft()
    for rule in list(ruleset.rules):
        if rule.uid != uid:
            continue
        clone = rule.copy()
        clone.rule_id = _unique_rule_id(ruleset, f"{rule.rule_id}_copy")
        clone.rule_order = rule.rule_order + 1
        ruleset.rules.append(clone)
        select_rule(clone.uid)
        return


def delete_rule(uid: str) -> None:
    ruleset = draft()
    ruleset.rules = [r for r in ruleset.rules if r.uid != uid]
    select_rule(ruleset.rules[0].uid if ruleset.rules else None)


def move_rule(uid: str, offset: int) -> None:
    """Swap rule_order with the neighbour in the given direction."""
    ordered = draft().ordered_rules()
    index = next((i for i, r in enumerate(ordered) if r.uid == uid), None)
    if index is None:
        return
    target = index + offset
    if target < 0 or target >= len(ordered):
        return
    a, b = ordered[index], ordered[target]
    a.rule_order, b.rule_order = b.rule_order, a.rule_order


def _unique_rule_id(ruleset: Ruleset, candidate: str) -> str:
    existing = {r.rule_id for r in ruleset.rules}
    if candidate not in existing:
        return candidate
    counter = 2
    while f"{candidate}_{counter}" in existing:
        counter += 1
    return f"{candidate}_{counter}"
