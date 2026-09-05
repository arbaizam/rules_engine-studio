"""Browser-local recovery for in-progress rulesets and sample rows."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping
from typing import Any

import pandas as pd
import streamlit as st

from rules_engine.canonical_values import canonical_json_value, decode_json_types

from .. import state
from ..schema import Ruleset

_SCHEMA_VERSION = 2
_STORAGE_KEY = "rules-engine-studio:working-draft:v2"
_COMPONENT_KEY = "browser_autosave_bridge"
_CHECKED = "_browser_autosave_checked"
_NOTICE = "_browser_autosave_notice"
_CLEAR = "_browser_autosave_clear"
_RESTORE_PENDING = "_browser_autosave_restore_pending"
_MAX_PAYLOAD_BYTES = 4_000_000

_BRIDGE_DEFINITION = {
    "name": "studio_browser_autosave",
    "html": '<p class="studio-autosave" role="status" aria-live="polite"></p>',
    "css": """
        :host {
            display: block;
            width: 100%;
        }

        .studio-autosave {
            color: #AFC1CF;
            font-size: 0.78rem;
            line-height: 1.35;
            margin: 0.15rem 0 0;
        }
    """,
    "js": """
        export default function ({ parentElement, data, setTriggerValue }) {
            const status = parentElement.querySelector(".studio-autosave");
            const storageKey = String(data?.storageKey ?? "");
            try {
                if (data?.mode === "restore") {
                    const saved = window.localStorage.getItem(storageKey) ?? "";
                    status.textContent = saved ? "Recovering browser autosave…" : "Autosave ready";
                    window.setTimeout(
                        () => setTriggerValue("restore", { payload: saved }),
                        50
                    );
                    return undefined;
                } else if (data?.mode === "hold") {
                    status.textContent = "Recovering browser autosave…";
                    return undefined;
                } else if (data?.mode === "clear") {
                    window.localStorage.removeItem(storageKey);
                    status.textContent = "Invalid autosave cleared";
                    return undefined;
                } else {
                    const payload = typeof data?.payload === "string" ? data.payload : "";
                    if (payload && window.localStorage.getItem(storageKey) !== payload) {
                        window.localStorage.setItem(storageKey, payload);
                    }
                    status.textContent = payload ? "Autosaved in this browser" : "Autosave paused";
                }
            } catch (error) {
                status.textContent = "Browser autosave is unavailable";
                if (data?.mode === "restore") setTriggerValue("restore", "");
            }
            return undefined;
        }
    """,
}

_BRIDGE = None
_BRIDGE_RUNTIME = None


def _bridge_component():
    """Register the autosave bridge once for each Streamlit runtime."""
    from streamlit.runtime import Runtime

    global _BRIDGE, _BRIDGE_RUNTIME
    runtime = Runtime.instance()
    if _BRIDGE is None or _BRIDGE_RUNTIME is not runtime:
        _BRIDGE = st.components.v2.component(**_BRIDGE_DEFINITION)
        _BRIDGE_RUNTIME = runtime
    return _BRIDGE


def _pack(value: Any) -> Any:
    """Use the engine's collision-safe, lossless literal persistence contract."""
    return canonical_json_value(value)


def _sample_scalars(value: Any) -> Any:
    """Remove dataframe missing sentinels without changing authored literal types."""
    if value is pd.NA or value is pd.NaT:
        return None
    if isinstance(value, float) and math.isnan(value):
        return None
    if isinstance(value, Mapping):
        return {key: _sample_scalars(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_sample_scalars(item) for item in value]
    if isinstance(value, tuple):
        return tuple(_sample_scalars(item) for item in value)
    if isinstance(value, set):
        return {_sample_scalars(item) for item in value}
    to_list = getattr(value, "tolist", None)
    if callable(to_list):
        return _sample_scalars(to_list())
    scalar = getattr(value, "item", None)
    if callable(scalar):
        return _sample_scalars(scalar())
    return value


def _unpack(value: Any) -> Any:
    """Restore tagged authored values from strict JSON data."""
    return decode_json_types(value)


def snapshot_json() -> str:
    """Serialize the current incomplete draft and test rows for local recovery."""
    if state.editor_errors():
        raise ValueError("Browser autosave is paused while an editor value is invalid.")
    frame = state.frame()
    selected = state.selected_rule()
    payload = {
        "schema_version": _SCHEMA_VERSION,
        "ruleset": _pack(state.draft().to_dict()),
        "sample": {
            "columns": [str(column) for column in frame.columns],
            "rows": _pack(_sample_scalars(frame.to_dict("records"))),
        },
        "column_prefix": str(st.session_state.get(state.PREFIX, "rules_engine")),
        "selected_rule_index": next(
            (index for index, rule in enumerate(state.draft().ordered_rules()) if rule is selected),
            None,
        ),
    }
    encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
    if len(encoded.encode("utf-8")) > _MAX_PAYLOAD_BYTES:
        raise ValueError("The working draft is too large for browser autosave.")
    return encoded


def restore_json(encoded: str) -> None:
    """Validate and restore a browser-local working snapshot."""
    if not isinstance(encoded, str) or not encoded:
        return
    if len(encoded.encode("utf-8")) > _MAX_PAYLOAD_BYTES:
        raise ValueError("Browser autosave exceeds the supported size.")
    payload = json.loads(encoded)
    if not isinstance(payload, Mapping) or payload.get("schema_version") != _SCHEMA_VERSION:
        raise ValueError("Browser autosave uses an unsupported format.")
    ruleset_payload = _unpack(payload.get("ruleset"))
    sample_payload = payload.get("sample")
    if not isinstance(ruleset_payload, Mapping) or not isinstance(sample_payload, Mapping):
        raise ValueError("Browser autosave is incomplete.")
    rows = _unpack(sample_payload.get("rows", []))
    columns = sample_payload.get("columns", [])
    if (
        not isinstance(rows, list)
        or not all(isinstance(row, Mapping) for row in rows)
        or not isinstance(columns, list)
        or not all(isinstance(column, str) for column in columns)
        or len(set(columns)) != len(columns)
        or any(set(row) != set(columns) for row in rows)
    ):
        raise ValueError("Browser autosave sample data is invalid.")

    restored = Ruleset.from_dict(ruleset_payload)
    restored_frame = pd.DataFrame(rows, columns=columns, dtype=object)
    prefix = payload.get("column_prefix", "rules_engine")
    if not isinstance(prefix, str):
        raise ValueError("Browser autosave column prefix must be a string.")
    selected_index = payload.get("selected_rule_index")
    if selected_index is not None and (
        type(selected_index) is not int or not 0 <= selected_index < len(restored.rules)
    ):
        raise ValueError("Browser autosave selection is invalid.")

    # Prepare every fallible conversion before replacing the current draft.
    state.set_frame(restored_frame)
    state.set_draft(restored)
    st.session_state["sample_editor_revision"] = (
        st.session_state.get("sample_editor_revision", 0) + 1
    )
    st.session_state[state.PREFIX] = prefix
    if selected_index is not None:
        state.select_rule(restored.rules[selected_index].uid)


def _restore_from_component() -> None:
    """Handle the one-time browser restore trigger for a fresh Python session."""
    st.session_state[_CHECKED] = True
    st.session_state[_RESTORE_PENDING] = True
    component_state = st.session_state.get(_COMPONENT_KEY, {})
    restore_event = component_state.get("restore") if component_state else None
    if isinstance(restore_event, Mapping):
        encoded = restore_event.get("payload")
    else:
        encoded = restore_event
    if not encoded:
        st.session_state[_RESTORE_PENDING] = False
        return

    def restore() -> None:
        try:
            restore_json(str(encoded))
        except Exception:  # noqa: BLE001 - corrupt browser data must never block startup
            st.session_state[_CLEAR] = True
            st.session_state[_NOTICE] = "Browser autosave could not be recovered; using demo data."
        else:
            st.session_state[_NOTICE] = "Recovered your browser-autosaved project."
        finally:
            st.session_state[_RESTORE_PENDING] = False

    state.queue(restore)


def render() -> None:
    """Mount the recovery bridge and surface recovery status in the sidebar."""
    checked = bool(st.session_state.get(_CHECKED, False))
    clear = bool(st.session_state.pop(_CLEAR, False))
    restore_pending = bool(st.session_state.get(_RESTORE_PENDING, False))
    payload = ""
    if checked and not clear and not restore_pending:
        try:
            payload = snapshot_json()
        except ValueError as exc:
            st.caption(str(exc))
    mode = "clear" if clear else "hold" if restore_pending else "save" if checked else "restore"
    bridge = _bridge_component()
    bridge(
        data={
            "mode": mode,
            "payload": payload,
            "storageKey": _STORAGE_KEY,
        },
        key=_COMPONENT_KEY,
        on_restore_change=_restore_from_component,
        width="stretch",
        height="content",
    )
    notice = st.session_state.pop(_NOTICE, None)
    if notice:
        st.toast(str(notice))


__all__ = ["render", "restore_json", "snapshot_json"]
