"""Browser-local recovery for in-progress rulesets and sample rows."""

from __future__ import annotations

import json
import math
from collections.abc import Mapping, Sequence
from datetime import date, datetime, time
from decimal import Decimal
from typing import Any

import pandas as pd
import streamlit as st

from .. import state
from ..schema import Ruleset

_SCHEMA_VERSION = 1
_STORAGE_KEY = "rules-engine-studio:working-draft:v1"
_COMPONENT_KEY = "browser_autosave_bridge"
_CHECKED = "_browser_autosave_checked"
_NOTICE = "_browser_autosave_notice"
_MAX_PAYLOAD_BYTES = 4_000_000
_TYPE_KEY = "__studio_type__"

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
                } else {
                    const payload = typeof data?.payload === "string" ? data.payload : "";
                    if (payload && window.localStorage.getItem(storageKey) !== payload) {
                        window.localStorage.setItem(storageKey, payload);
                    }
                    status.textContent = "Autosaved in this browser";
                }
            } catch (error) {
                status.textContent = "Browser autosave is unavailable";
                if (data?.mode === "restore") setTriggerValue("restore", "");
            }
            return undefined;
        }
    """,
}


def _pack(value: Any) -> Any:
    """Convert authored values and dataframe scalars into strict JSON data."""
    if value is None or isinstance(value, (bool, int, str)):
        return value
    if isinstance(value, float):
        return value if math.isfinite(value) else None
    if isinstance(value, Decimal):
        return {_TYPE_KEY: "decimal", "value": format(value, "f")}
    if isinstance(value, datetime):
        return {_TYPE_KEY: "datetime", "value": value.isoformat()}
    if isinstance(value, date):
        return {_TYPE_KEY: "date", "value": value.isoformat()}
    if isinstance(value, time):
        return {_TYPE_KEY: "time", "value": value.isoformat()}
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        return _pack(to_dict())
    if isinstance(value, Mapping):
        return {str(key): _pack(item) for key, item in value.items()}
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_pack(item) for item in value]
    if isinstance(value, set):
        return [_pack(item) for item in sorted(value, key=str)]
    scalar = getattr(value, "item", None)
    if callable(scalar):
        return _pack(scalar())
    try:
        return None if bool(pd.isna(value)) else str(value)
    except (TypeError, ValueError):
        return str(value)


def _unpack(value: Any) -> Any:
    """Restore tagged authored values from strict JSON data."""
    if isinstance(value, list):
        return [_unpack(item) for item in value]
    if not isinstance(value, Mapping):
        return value
    tag = value.get(_TYPE_KEY) if set(value) == {_TYPE_KEY, "value"} else None
    raw = value.get("value")
    if tag == "decimal" and isinstance(raw, str):
        return Decimal(raw)
    if tag == "datetime" and isinstance(raw, str):
        return datetime.fromisoformat(raw)
    if tag == "date" and isinstance(raw, str):
        return date.fromisoformat(raw)
    if tag == "time" and isinstance(raw, str):
        return time.fromisoformat(raw)
    return {str(key): _unpack(item) for key, item in value.items()}


def snapshot_json() -> str:
    """Serialize the current incomplete draft and test rows for local recovery."""
    frame = state.frame()
    selected = state.selected_rule()
    payload = {
        "schema_version": _SCHEMA_VERSION,
        "ruleset": _pack(state.draft().to_dict()),
        "sample": {
            "columns": [str(column) for column in frame.columns],
            "rows": _pack(frame.to_dict("records")),
        },
        "column_prefix": str(st.session_state.get(state.PREFIX, "rules_engine")),
        "selected_rule_id": selected.rule_id if selected is not None else None,
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
    if not isinstance(rows, list) or not isinstance(columns, list):
        raise ValueError("Browser autosave sample data is invalid.")

    restored = Ruleset.from_dict(ruleset_payload)
    state.set_draft(restored)
    state.set_frame(pd.DataFrame(rows, columns=[str(column) for column in columns]))
    st.session_state.pop("sample_editor", None)
    st.session_state[state.PREFIX] = str(payload.get("column_prefix") or "rules_engine")
    selected_rule_id = payload.get("selected_rule_id")
    selected = next((rule for rule in restored.rules if rule.rule_id == selected_rule_id), None)
    if selected is not None:
        state.select_rule(selected.uid)


def _restore_from_component() -> None:
    """Handle the one-time browser restore trigger for a fresh Python session."""
    st.session_state[_CHECKED] = True
    component_state = st.session_state.get(_COMPONENT_KEY, {})
    restore_event = component_state.get("restore") if component_state else None
    if isinstance(restore_event, Mapping):
        encoded = restore_event.get("payload")
    else:
        encoded = restore_event
    if not encoded:
        return

    def restore() -> None:
        try:
            restore_json(str(encoded))
        except (TypeError, ValueError, json.JSONDecodeError):
            st.session_state[_NOTICE] = (
                "Browser autosave could not be recovered; using demo data."
            )
        else:
            st.session_state[_NOTICE] = "Recovered your browser-autosaved project."

    state.queue(restore)


def render() -> None:
    """Mount the recovery bridge and surface recovery status in the sidebar."""
    checked = bool(st.session_state.get(_CHECKED, False))
    payload = ""
    if checked:
        try:
            payload = snapshot_json()
        except ValueError as exc:
            st.caption(str(exc))
    bridge = st.components.v2.component(**_BRIDGE_DEFINITION)
    bridge(
        data={
            "mode": "save" if checked else "restore",
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
