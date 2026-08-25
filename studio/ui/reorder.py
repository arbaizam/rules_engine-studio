"""Integrated Streamlit v2 rule sorting with native-button fallback support."""

from __future__ import annotations

from collections.abc import Sequence

import streamlit as st

from .. import state
from ..schema import Rule

_COMPONENT_KEY = "rule_drag_sorter"

_SORTER_DEFINITION = {
    "name": "studio_rule_sorter",
    "html": """
        <div class="studio-sorter" role="list" aria-label="Rule order"></div>
        <p class="studio-sorter-help">Click or tap a rule to open it. Click and hold anywhere, then move to drag it. Focus the grip and use the arrow keys for keyboard reordering.</p>
    """,
    "css": """
        :host {
            display: block;
            width: 100%;
        }

        .studio-sorter {
            display: flex;
            flex-direction: column;
            gap: 0.45rem;
            width: 100%;
        }

        .studio-sorter-item {
            align-items: center;
            background: #071E2D;
            border: 2px solid #52758F;
            border-radius: 0.55rem;
            color: #F8FAFC;
            cursor: grab;
            display: grid;
            font: inherit;
            gap: 0.55rem;
            grid-template-columns: 2rem minmax(0, 1fr);
            min-height: 2.8rem;
            padding: 0.4rem 0.65rem 0.4rem 0.4rem;
            touch-action: none;
            transition: border-color 120ms ease, opacity 120ms ease, transform 120ms ease;
            user-select: none;
        }

        .studio-sorter-item:hover,
        .studio-sorter-item:focus-within {
            border-color: #93B1CC;
        }

        .studio-sorter-item.dragging {
            border-color: #AAAD00;
            opacity: 0.72;
            transform: scale(0.99);
        }

        .studio-sorter-item:active {
            cursor: grabbing;
        }

        .studio-sorter-item.selected {
            background: #0B4057;
            border-color: #058AA8;
            box-shadow: inset 4px 0 0 #AAAD00;
        }

        .studio-sorter-handle {
            align-items: center;
            appearance: none;
            background: #0D2C43;
            border: 1px solid #7194AE;
            border-radius: 0.35rem;
            color: #F8FAFC;
            cursor: grab;
            display: inline-flex;
            font: inherit;
            height: 2rem;
            justify-content: center;
            padding: 0;
            touch-action: none;
            user-select: none;
            width: 2rem;
        }

        .studio-sorter-handle:active {
            cursor: grabbing;
        }

        .studio-sorter-handle:focus-visible {
            outline: 2px solid #AAAD00;
            outline-offset: 2px;
        }

        .studio-sorter-label {
            font-size: 0.88rem;
            line-height: 1.35;
            min-width: 0;
            overflow-wrap: anywhere;
        }

        .studio-sorter-help {
            color: #AFC1CF;
            font-size: 0.78rem;
            line-height: 1.35;
            margin: 0.55rem 0 0;
        }
    """,
    "js": """
        export default function ({ parentElement, data, setTriggerValue }) {
            const list = parentElement.querySelector(".studio-sorter");
            const items = Array.isArray(data?.items) ? data.items : [];
            const renderSignature = JSON.stringify(
                items.map((item) => ({
                    uid: String(item.uid),
                    label: String(item.label ?? item.uid),
                    selected: Boolean(item.selected),
                }))
            );
            const existingRows = list.querySelectorAll(".studio-sorter-item");
            if (
                list.dataset.renderSignature === renderSignature
                && existingRows.length === items.length
            ) {
                return undefined;
            }
            list.dataset.renderSignature = renderSignature;
            const initialOrder = items.map((item) => String(item.uid));
            let dragElement = null;
            let dropped = false;

            const order = () =>
                Array.from(list.querySelectorAll(".studio-sorter-item"))
                    .map((element) => element.dataset.uid);

            const emitOrder = () => {
                const nextOrder = order();
                if (nextOrder.join("|") !== initialOrder.join("|")) {
                    setTriggerValue("order", nextOrder);
                }
            };

            const restoreOrder = () => {
                const byUid = new Map(
                    Array.from(list.querySelectorAll(".studio-sorter-item"))
                        .map((element) => [element.dataset.uid, element])
                );
                initialOrder.forEach((uid) => {
                    const element = byUid.get(uid);
                    if (element) list.appendChild(element);
                });
            };

            const moveAt = (clientY) => {
                if (!dragElement) return;
                const siblings = Array.from(
                    list.querySelectorAll(".studio-sorter-item:not(.dragging)")
                );
                const before = siblings.find((element) => {
                    const rect = element.getBoundingClientRect();
                    return clientY < rect.top + rect.height / 2;
                });
                if (before) list.insertBefore(dragElement, before);
                else list.appendChild(dragElement);
            };

            const finishPointerDrag = (commit) => {
                if (!dragElement) return;
                dragElement.classList.remove("dragging");
                if (commit) emitOrder();
                else restoreOrder();
                dragElement = null;
            };

            list.replaceChildren();
            items.forEach((item) => {
                const uid = String(item.uid);
                const label = String(item.label ?? uid);
                const selected = Boolean(item.selected);
                let pointerId = null;
                let pointerDragging = false;
                let pointerStartY = 0;
                let ignoreNextClick = false;
                const row = document.createElement("div");
                row.className = `studio-sorter-item${selected ? " selected" : ""}`;
                row.dataset.uid = uid;
                row.draggable = true;
                row.setAttribute("role", "listitem");
                row.setAttribute("aria-current", selected ? "true" : "false");
                row.tabIndex = 0;

                const handle = document.createElement("button");
                handle.className = "studio-sorter-handle";
                handle.type = "button";
                handle.textContent = "↕";
                handle.setAttribute("aria-label", `Move ${label}`);

                const text = document.createElement("span");
                text.className = "studio-sorter-label";
                text.textContent = label;

                row.append(handle, text);
                list.appendChild(row);

                row.onclick = () => {
                    if (ignoreNextClick) {
                        ignoreNextClick = false;
                        return;
                    }
                    if (!selected) setTriggerValue("select", uid);
                };
                row.onkeydown = (event) => {
                    if (event.target !== row || event.key !== "Enter") return;
                    event.preventDefault();
                    if (!selected) setTriggerValue("select", uid);
                };

                row.ondragstart = (event) => {
                    dropped = false;
                    dragElement = row;
                    row.classList.add("dragging");
                    event.dataTransfer.effectAllowed = "move";
                    event.dataTransfer.setData("text/plain", uid);
                };
                row.ondragend = () => {
                    row.classList.remove("dragging");
                    if (!dropped) restoreOrder();
                    dragElement = null;
                    dropped = false;
                };

                row.onpointerdown = (event) => {
                    if (event.pointerType === "mouse") return;
                    pointerId = event.pointerId;
                    pointerDragging = false;
                    pointerStartY = event.clientY;
                    row.setPointerCapture(event.pointerId);
                };
                row.onpointermove = (event) => {
                    if (event.pointerId !== pointerId) return;
                    if (!pointerDragging && Math.abs(event.clientY - pointerStartY) >= 6) {
                        pointerDragging = true;
                        dragElement = row;
                        row.classList.add("dragging");
                    }
                    if (!pointerDragging) return;
                    event.preventDefault();
                    moveAt(event.clientY);
                };
                row.onpointerup = (event) => {
                    if (event.pointerId === pointerId) {
                        ignoreNextClick = true;
                        if (pointerDragging) finishPointerDrag(true);
                        else if (!selected) setTriggerValue("select", uid);
                        pointerDragging = false;
                        pointerId = null;
                    }
                };
                row.onpointercancel = (event) => {
                    if (event.pointerId !== pointerId) return;
                    if (pointerDragging) finishPointerDrag(false);
                    pointerDragging = false;
                    pointerId = null;
                };
                handle.onkeydown = (event) => {
                    if (event.key === "Enter") {
                        event.preventDefault();
                        if (!selected) setTriggerValue("select", uid);
                        return;
                    }
                    if (event.key !== "ArrowUp" && event.key !== "ArrowDown") return;
                    event.preventDefault();
                    const sibling = event.key === "ArrowUp"
                        ? row.previousElementSibling
                        : row.nextElementSibling;
                    if (!sibling) return;
                    if (event.key === "ArrowUp") list.insertBefore(row, sibling);
                    else list.insertBefore(sibling, row);
                    emitOrder();
                };
            });

            list.ondragover = (event) => {
                if (!dragElement) return;
                event.preventDefault();
                event.dataTransfer.dropEffect = "move";
                moveAt(event.clientY);
            };
            list.ondrop = (event) => {
                if (!dragElement) return;
                event.preventDefault();
                dropped = true;
                dragElement.classList.remove("dragging");
                emitOrder();
                dragElement = null;
            };

            return undefined;
        }
    """,
}

_SORTER = None
_SORTER_RUNTIME = None


def _sorter_component():
    """Register the sorter once for each Streamlit runtime."""
    from streamlit.runtime import Runtime

    global _SORTER, _SORTER_RUNTIME
    runtime = Runtime.instance()
    if _SORTER is None or _SORTER_RUNTIME is not runtime:
        _SORTER = st.components.v2.component(**_SORTER_DEFINITION)
        _SORTER_RUNTIME = runtime
    return _SORTER


def _apply_drag_order() -> None:
    """Apply an emitted order before the event-triggered app redraw."""
    component_state = st.session_state.get(_COMPONENT_KEY, {})
    requested = component_state.get("order") if component_state else None
    if not isinstance(requested, Sequence) or isinstance(requested, (str, bytes)):
        return
    normalized = tuple(str(uid) for uid in requested)
    state.reorder_rules(normalized)


def _apply_rule_selection() -> None:
    """Open the rule emitted by a double-click or keyboard selection."""
    component_state = st.session_state.get(_COMPONENT_KEY, {})
    requested = component_state.get("select") if component_state else None
    if not isinstance(requested, str):
        return
    selected = state.selected_rule()
    if selected is not None and selected.uid == requested:
        return
    if any(rule.uid == requested for rule in state.draft().rules):
        state.select_rule(requested)


def render_drag_sorter(rules: Sequence[Rule], selected_uid: str | None) -> None:
    """Render the integrated sortable list for the supplied ordered rules."""
    sorter = _sorter_component()
    sorter(
        data={
            "items": [
                {
                    "uid": rule.uid,
                    "label": (
                        f"{rule.rule_order} · {rule.rule_id or 'untitled'}"
                        f" — {rule.rule_name or 'Unnamed rule'}"
                    ),
                    "selected": rule.uid == selected_uid,
                }
                for rule in rules
            ]
        },
        key=_COMPONENT_KEY,
        on_order_change=_apply_drag_order,
        on_select_change=_apply_rule_selection,
        width="stretch",
        height="content",
    )


__all__ = ["render_drag_sorter"]
