"""Collapsible live YAML preview beside the active Studio workspace."""

from __future__ import annotations

import streamlit as st

from .. import state, yaml_io
from ..schema import Ruleset

OPEN = "yaml_preview_open"


def init() -> None:
    """Initialize the browser-session display preference."""
    if OPEN not in st.session_state:
        st.session_state[OPEN] = True


def workspace_columns():
    """Return the authoring workspace and its expanded panel or collapsed rail."""
    init()
    widths = [3, 1] if st.session_state[OPEN] else [30, 1]
    return st.columns(widths, gap="small")


def current_snapshot() -> yaml_io.YamlSnapshot:
    """Return the cached compiler snapshot for the fully rendered live draft."""
    return _cached_snapshot(state.draft().to_dict(), tuple(state.columns()))


@st.cache_data(show_spinner=False)
def _cached_snapshot(
    payload: dict,
    columns: tuple[str, ...],
) -> yaml_io.YamlSnapshot:
    """Compile a payload once for all YAML and validation surfaces on a rerun."""
    return yaml_io.build_snapshot(Ruleset.from_dict(payload), columns)


def render(snapshot: yaml_io.YamlSnapshot) -> None:
    """Render the expanded preview or its narrow reopen ribbon."""
    if not st.session_state[OPEN]:
        with st.container(key="yaml_preview_rail"):
            st.button(
                "YAML",
                key="yaml_preview_open_button",
                help="Open the live YAML preview",
                type="tertiary",
                width="stretch",
                on_click=_set_open,
                args=(True,),
            )
            _rail_status(snapshot)
        return

    with st.container(key="yaml_preview_panel", border=True):
        with st.container(
            key="yaml_preview_header",
            horizontal=True,
            horizontal_alignment="distribute",
            vertical_alignment="center",
        ):
            st.markdown("### YAML Preview")
            st.button(
                "›",
                key="yaml_preview_close_button",
                help="Collapse the live YAML preview",
                type="tertiary",
                on_click=_set_open,
                args=(False,),
            )

        _status(snapshot)
        st.code(
            snapshot.document,
            language="yaml",
            line_numbers=True,
            wrap_lines=False,
            height=480,
        )
        st.caption("Read-only live view · Import and download remain in the YAML tab.")


def _set_open(value: bool) -> None:
    """Persist the panel preference for the current browser session."""
    st.session_state[OPEN] = value


def _status(snapshot: yaml_io.YamlSnapshot) -> None:
    """Render a compact status banner above the live document."""
    warning_count = sum(issue.severity == "warning" for issue in snapshot.issues)
    if snapshot.exportable:
        detail = "Canonical YAML · Live"
        if warning_count:
            detail += f" · {warning_count} sample-data warning"
            if warning_count != 1:
                detail += "s"
        modifier = "ready"
    elif snapshot.compiled:
        detail = f"Draft YAML · {snapshot.error_count} error"
        if snapshot.error_count != 1:
            detail += "s"
        detail += " · Not exportable"
        modifier = "blocked"
    else:
        detail = "Draft preview · Compiler blocked · Not exportable"
        modifier = "blocked"

    st.markdown(
        f'<div class="studio-yaml-status {modifier}"><span></span>{detail}</div>',
        unsafe_allow_html=True,
    )


def _rail_status(snapshot: yaml_io.YamlSnapshot) -> None:
    """Keep export readiness visible while the preview is collapsed."""
    modifier = "ready" if snapshot.exportable else "blocked"
    label = "YAML is exportable" if snapshot.exportable else "YAML has blocking errors"
    st.markdown(
        f'<div class="studio-yaml-rail-status {modifier}" title="{label}"></div>',
        unsafe_allow_html=True,
    )


__all__ = ["OPEN", "current_snapshot", "init", "render", "workspace_columns"]
