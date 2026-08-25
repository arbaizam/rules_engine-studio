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
        <p class="studio-sorter-help">Drag the handle or focus it and use the arrow keys.</p>
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
            display: grid;
            font: inherit;
            gap: 0.55rem;
            grid-template-columns: 2rem minmax(0, 1fr);
            min-height: 2.8rem;
            padding: 0.4rem 0.65rem 0.4rem 0.4rem;
            transition: border-color 120ms ease, opacity 120ms ease, transform 120ms ease;
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
                let pointerId = null;
                const row = document.createElement("div");
                row.className = "studio-sorter-item";
                row.dataset.uid = uid;
                row.draggable = true;
                row.setAttribute("role", "listitem");

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

                row.ondragstart = (event) => {
                    dragElement = row;
                    dropped = false;
                    row.classList.add("dragging");
                    event.dataTransfer.effectAllowed = "move";
                    event.dataTransfer.setData("text/plain", uid);
                };
                row.ondragend = () => {
                    row.classList.remove("dragging");
                    if (!dropped) restoreOrder();
                    dragElement = null;
                };

                handle.onpointerdown = (event) => {
                    if (event.pointerType === "mouse" && event.button !== 0) return;
                    event.preventDefault();
                    dragElement = row;
                    row.classList.add("dragging");
                    pointerId = event.pointerId;
                    handle.setPointerCapture(event.pointerId);
                };
                handle.onpointermove = (event) => {
                    if (!dragElement || event.pointerId !== pointerId) return;
                    event.preventDefault();
                    moveAt(event.clientY);
                };
                handle.onpointerup = (event) => {
                    if (event.pointerId === pointerId) {
                        finishPointerDrag(true);
                        pointerId = null;
                    }
                };
                handle.onpointercancel = () => {
                    finishPointerDrag(false);
                    pointerId = null;
                };
                handle.onkeydown = (event) => {
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

            return () => {
                list.ondragover = null;
                list.ondrop = null;
            };
        }
    """,
}


def _apply_drag_order() -> None:
    """Apply the transient order emitted by the v2 component."""
    component_state = st.session_state.get(_COMPONENT_KEY, {})
    requested = component_state.get("order") if component_state else None
    if not isinstance(requested, Sequence) or isinstance(requested, (str, bytes)):
        return
    normalized = tuple(str(uid) for uid in requested)
    state.queue(lambda order=normalized: state.reorder_rules(order))


def render_drag_sorter(rules: Sequence[Rule]) -> None:
    """Render the integrated sortable list for the supplied ordered rules."""
    sorter = st.components.v2.component(**_SORTER_DEFINITION)
    sorter(
        data={
            "items": [
                {
                    "uid": rule.uid,
                    "label": (
                        f"{rule.rule_order} · {rule.rule_id or 'untitled'}"
                        f" — {rule.rule_name or 'Unnamed rule'}"
                    ),
                }
                for rule in rules
            ]
        },
        key=_COMPONENT_KEY,
        on_order_change=_apply_drag_order,
        width="stretch",
        height="content",
    )


__all__ = ["render_drag_sorter"]
