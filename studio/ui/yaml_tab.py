"""Canonical rules-engine YAML validation, export, and import view."""

from __future__ import annotations

from datetime import datetime, timezone

import streamlit as st
from rules_engine.exceptions import RulesEngineError

from .. import state, yaml_io
from ..schema import Ruleset
from .widgets import issue_list


def render() -> None:
    """Render production validation and canonical YAML interchange controls."""
    ruleset = state.draft()
    issues = yaml_io.validate(ruleset, state.columns())

    st.subheader("Checks")
    issue_list(issues, "Checks")

    st.subheader("Ruleset file")
    document = ""
    if yaml_io.has_errors(issues):
        st.warning("Canonical YAML is available after production validation passes.")
    else:
        document = _with_header(yaml_io.to_yaml(ruleset), ruleset)
        st.code(document, language="yaml")

    cols = st.columns([2, 2, 3])
    cols[0].download_button(
        "Download YAML",
        data=document.encode("utf-8"),
        file_name=f"{ruleset.ruleset_id or 'ruleset'}_{ruleset.version or '0.1.0'}.yaml",
        mime="application/x-yaml",
        type="primary",
        disabled=yaml_io.has_errors(issues),
    )
    if yaml_io.has_errors(issues):
        cols[1].caption("Fix the errors above to enable the download.")
    if cols[2].button("Renumber rules 10, 20, 30…"):
        state.queue(lambda: yaml_io.renumber(state.draft()))

    st.divider()
    _import()


def _with_header(body: str, ruleset: Ruleset) -> str:
    """Add non-semantic authoring comments to canonical YAML text."""
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    return (
        f"# {ruleset.ruleset_id} {ruleset.version}\n"
        f"# Drafted in Rules Engine Studio on {stamp}\n"
        f"{body}"
    )


def _import() -> None:
    """Render canonical YAML file and pasted-text import controls."""
    st.subheader("Open an existing ruleset")
    st.caption("Importing replaces the current draft. Download first if you want to keep it.")

    cols = st.columns(2)

    with cols[0]:
        upload = st.file_uploader(
            "YAML file", type=["yaml", "yml"], key="ruleset_upload", label_visibility="collapsed"
        )
        if upload is not None and st.button("Replace draft with this file", key="do_ruleset_upload"):
            _load(upload.getvalue().decode("utf-8"))

    with cols[1]:
        pasted = st.text_area(
            "Paste YAML",
            key="ruleset_paste",
            height=160,
            placeholder=(
                "ruleset_id: position_hierarchy\n"
                "ruleset_name: Position hierarchy\n"
                "version: 0.1.0\n"
                "rules: []"
            ),
            label_visibility="collapsed",
        )
        if pasted.strip() and st.button("Replace draft with pasted YAML", key="do_ruleset_paste"):
            _load(pasted)


def _load(text: str) -> None:
    """Compile imported YAML and replace the current mutable draft."""
    try:
        ruleset = yaml_io.from_yaml(text)
    except (RulesEngineError, TypeError, UnicodeError, ValueError) as exc:
        st.error(f"Could not read that ruleset: {exc}")
        return
    state.set_draft(ruleset)
    st.success(f"Opened {ruleset.ruleset_id} {ruleset.version}.")
    st.rerun()
