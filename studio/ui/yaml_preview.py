"""Collapsible live YAML preview beside the active Studio workspace."""

from __future__ import annotations

import re

import streamlit as st

from .. import state, yaml_io
from ..schema import Ruleset

OPEN = "yaml_preview_open"

_RULE_LINE = re.compile(r"^\s*-\s+rule_id\s*:")
_SCROLLER_DEFINITION = {
    "name": "studio_yaml_rule_scroller",
    "html": '<span class="studio-yaml-scroll-bridge" aria-hidden="true"></span>',
    "css": """
        :host {
            display: none;
            height: 0;
            overflow: hidden;
            width: 0;
        }
    """,
    "js": """
        export default function ({ parentElement, data }) {
            const ownerDocument = parentElement.ownerDocument;
            const targetLine = Math.max(1, Number(data?.line ?? 1));
            const selectionKey = String(data?.selectionKey ?? "");
            let cancelled = false;

            const positionPreview = (attempt = 0) => {
                if (cancelled) return;
                const panel = ownerDocument.querySelector(
                    '[class*="st-key-yaml_preview_panel"]'
                );
                const codeBlock = panel?.querySelector('[data-testid="stCode"]');
                const scroller = codeBlock?.querySelector("pre");
                const code = codeBlock?.querySelector("code");
                if (!panel || !scroller || !code) {
                    if (attempt < 12) {
                        window.requestAnimationFrame(() => positionPreview(attempt + 1));
                    }
                    return;
                }

                const signature = `${selectionKey}:${targetLine}`;
                if (panel.dataset.yamlRuleAnchor === signature) return;
                panel.dataset.yamlRuleAnchor = signature;
                const style = window.getComputedStyle(code);
                const fontSize = Number.parseFloat(style.fontSize) || 14;
                const lineHeight = Number.parseFloat(style.lineHeight) || fontSize * 1.5;
                const offset = Math.max(0, scroller.clientHeight * 0.16);
                scroller.scrollTop = Math.max(0, (targetLine - 1) * lineHeight - offset);
            };

            window.requestAnimationFrame(() => positionPreview());
            return () => {
                cancelled = true;
            };
        }
    """,
}

_SCROLLER = None
_SCROLLER_RUNTIME = None


def init() -> None:
    """Initialize the browser-session display preference."""
    if OPEN not in st.session_state:
        st.session_state[OPEN] = True


def workspace_columns():
    """Return the authoring workspace and its expanded panel or collapsed rail."""
    init()
    widths = [12, 7] if st.session_state[OPEN] else [30, 1]
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
            height="stretch",
        )
        _scroll_to_selected_rule(snapshot)
        st.caption("Read-only live view · Import and download remain in the YAML tab.")


def _set_open(value: bool) -> None:
    """Persist the panel preference for the current browser session."""
    st.session_state[OPEN] = value


def _scroller_component():
    """Register the code-scroll bridge once for each Streamlit runtime."""
    from streamlit.runtime import Runtime

    global _SCROLLER, _SCROLLER_RUNTIME
    runtime = Runtime.instance()
    if _SCROLLER is None or _SCROLLER_RUNTIME is not runtime:
        _SCROLLER = st.components.v2.component(**_SCROLLER_DEFINITION)
        _SCROLLER_RUNTIME = runtime
    return _SCROLLER


def _scroll_to_selected_rule(snapshot: yaml_io.YamlSnapshot) -> None:
    """Align the preview with the selected rule without moving the page itself."""
    selected = state.selected_rule()
    if selected is None:
        return
    scroller = _scroller_component()
    scroller(
        data={
            "line": _selected_rule_line(snapshot.document, state.draft(), selected.uid),
            "selectionKey": selected.uid,
        },
        key="yaml_preview_rule_scroller",
        width="content",
        height="content",
    )


def _selected_rule_line(document: str, ruleset: Ruleset, selected_uid: str) -> int:
    """Return the one-based YAML line where the selected ordered rule begins."""
    ordered = ruleset.ordered_rules()
    selected_index = next(
        (index for index, rule in enumerate(ordered) if rule.uid == selected_uid),
        0,
    )
    rule_lines = [
        line_number
        for line_number, line in enumerate(document.splitlines(), start=1)
        if _RULE_LINE.match(line)
    ]
    if not rule_lines:
        return 1
    return rule_lines[min(selected_index, len(rule_lines) - 1)]


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
