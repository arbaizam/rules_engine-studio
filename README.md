# Rules Engine Studio

A Streamlit app for drafting `rules_engine` rulesets: build rules in a form,
test them against your own rows, export the YAML.

It runs locally today with nothing but Streamlit, pandas and PyYAML. It is
built to move to Databricks Apps later without a rewrite — see
[Running on Databricks](#running-on-databricks).

```
pip install -r requirements.txt
streamlit run app.py
```

---

## What it does

**Draft.** A rule is edited as *When … Then set …*. Conditions live in nestable
all/any groups, each with an active toggle and an empty-value policy.
Assignments are target field plus a value source. Nothing about YAML is visible
while you are writing rules.

**Test.** Every expression can be evaluated against real rows before export: a
single condition, a single assignment, one rule, the whole ruleset, or an ad-hoc
expression typed in a one-line syntax. Results show the resolved left and right
values, not just true/false — the usual question is not *did it match* but *what
did the engine actually see*.

**Export.** The YAML tab shows the file as it will be written, with a validation
pass that separates what blocks export (duplicate rule ids, an operator with no
right-hand value) from what merely deserves a look (a rule with no conditions, a
column the sample data does not have).

---

## Design notes

**Left rail is the ruleset, centre is one rule.** Rule authoring is inherently
one-at-a-time, and a list of forty rules in an accordion is unusable. The
sidebar holds ruleset identity, the ordered rule list, and the two output
switches (`column_prefix`, `full_audit`) that affect every preview.

**Order is a first-class control, not a field.** Rules are listed and executed in
`rule_order`. Up / Down swap orders, and "Renumber 10, 20, 30…" reflows the whole
set, because merge-order collisions between two authors are the failure mode
worth designing against.

**Overrides are shown where they happen.** A rule that sets a field a later rule
also sets gets an inline note naming the winner. Last-write-wins is correct
engine behaviour and quietly surprising to authors, so the editor says it out
loud rather than leaving it to be discovered in production output.

**`full_audit` is a preview switch, never a rule property.** It sits with the
output settings, and the Evaluate tab has a one-click comparison that asserts
compact and full-audit modes agree on `error`, `matched`, `matched_rule_ids` and
`assign`. If they ever diverge, that is a defect, and the studio should be able
to say so.

**Structural edits are deferred.** Streamlit reruns the script on every
interaction, so add/delete/reorder are queued during render and applied after it
(`state.queue` / `state.flush`). Mutating a list while rendering widgets keyed
off it is the reliable way to get ghost widgets.

**No `st.columns` inside a column.** Everything in `studio/ui/` stacks
vertically so it can be dropped into a column without breaking the layout tree.
Condition nesting uses bordered containers instead.

---

## Layout

```
┌─ sidebar ─────────┬─ Rules │ Sample data │ Evaluate │ YAML ──────────────┐
│ Ruleset details   │                                                      │
│                   │  rule id        what this rule does                  │
│ Rules             │  runs at   active   stop on match                    │
│  10 · senior_eng  │  ───────────────────────────────────────────────     │
│  20 · part_time   │  When                                                │
│  30 · fallback ⏹  │  ┌ match all of ───────── add test · add group ─┐    │
│                   │  │ ┌ if [column ▾] [equals ▾] [value ▾]   on 🗑 ┐│    │
│ add · duplicate   │  │ └───────────────────────────────────────────┘│    │
│ up · down · del   │  └─────────────────────────────────────────────┘     │
│                   │  Then set                                            │
│ Output            │  ┌ [hierarchy_node] = [value ▾ ENG.LEADERSHIP] 🗑 ┐   │
│  column_prefix    │  └────────────────────────────────────────────────┘  │
│  full_audit  ○—   │  Try this rule → ✓ matches, left=Engineering …       │
│                   │                                                      │
│ ✓ Ready to export │                                                      │
└───────────────────┴──────────────────────────────────────────────────────┘
```

---

## Structure

| Path | Role |
|---|---|
| `app.py` | Entry point: sidebar, tabs, deferred-edit flush |
| `studio/schema.py` | Draft model + operator catalogue. **The file to reconcile with `rules_engine`.** |
| `studio/yaml_io.py` | Export, import, validation |
| `studio/engine.py` | Preview evaluator (see [docs/PARITY.md](docs/PARITY.md)) |
| `studio/text_operands.py` | One-line operand syntax for nested function arguments |
| `studio/custom_functions.py` | Function registry used by draft rules |
| `studio/state.py` | Session state and rule-list operations |
| `studio/sample_data.py` | Demo rows and demo ruleset |
| `studio/ui/` | Streamlit views — no business logic |
| `tests/test_studio.py` | Core tests; imports no Streamlit |

The core is deliberately import-clean of Streamlit, so `pytest -q` runs in CI
with no browser and no Spark.

---

## Two things to confirm before this is trusted

**1. The YAML shape is inferred, not verified.** Field names came from the 0.4.0
audit review (Rule / Condition / Assignment structure, operand resolution,
serializer hash exclusions), not from `rules_engine.models`. The operator names
in `schema.OPERATORS` and the empty-value policy in `NULL_RESULTS` are the most
likely to be wrong. All of it is confined to `schema.py` and `yaml_io.py`.

**2. The preview evaluator is not the engine.** `studio/engine.py` reimplements
the documented semantics in pure Python. It agrees with the engine on rule
order, active flags, last-write-wins, `stop_on_match` scoping and error
quarantine — but not necessarily on type coercion, decimal handling, or Spark
null semantics. See [docs/PARITY.md](docs/PARITY.md) for how to retire it.

---

## Running on Databricks

Not deployed yet, by design. What is already in place:

- Streamlit is a supported Databricks Apps runtime; `app.yaml` holds the
  entrypoint.
- `requirements.txt` pins only what Apps can install.
- No local file writes: sample data and drafts live in session state, and export
  is a browser download.

What deployment will need:

- Somewhere to persist rulesets — a Unity Catalog volume or a governed table —
  instead of download-only. This is the main open product question.
- The real evaluator: swap the preview for `evaluate_dataframe` against a Spark
  session, which Apps can obtain via the Databricks SDK.
- Auth and authorship: Apps passes the signed-in user, which is what
  `published_by` should be filled from rather than typed.
