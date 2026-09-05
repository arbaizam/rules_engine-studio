# Canonical contract review

Studio was reviewed against the production `rules_engine` refactor on
`simplify_harden`, commit `ad26d54a8b57fd359b3ff3c0b9addf87f9b43f3f`
(engine 3.0). The previous Studio snapshot was engine 2.1 at `667f80d`.

## Corrections

| Area | Finding and correction |
|---|---|
| Production dependency | The old snapshot predates stricter validation, exact value handling, and current execution APIs. Replace the complete package from Git and verify its source hashes. |
| Runtime adapters | Removed row-evaluator APIs caused startup failure after upgrade. Use the current engine APIs and prepare sample schemas through the production validator. |
| Evaluation results | Compact and full audit previously ran through separate paths, including duplicate evaluation and overwriting normalized values. Use the production worker contract for both result modes. |
| Focused tests | Assignment and condition previews must honor active rules, preceding assignments, stop-on-match, and the enclosing rule's match before claiming an assignment was applied. |
| Draft fidelity | Imported type hints, typed nulls, temporal values, containers, and exact numbers must survive editing and export. Preserve authored values rather than inferring new persisted metadata while rendering. |
| Validation | Duplicate ordering and invalid condition options were silently repaired on load. Preserve them and report canonical compiler/validator diagnostics. |
| Function arguments | Consume the current ordered-sequence contracts, preserve nested operands, and exclude inactive or same-rule assignment producers from prior-assignment choices. |
| Literal controls | Avoid binary-float conversion and browser numeric precision limits for integers and decimals. Preserve exact container values and report incomplete edits. |
| Browser recovery | Use lossless, unambiguous value encoding so user mappings cannot collide with codec tags and tuple/set/temporal/decimal types survive. |
| Explanations | Empty groups are invalid; inactive conditions evaluate as false. Update the expression text to match engine semantics. |
| Sample input | Preserve JSON precision, reject duplicate names/keys, and retain invalid date text and timestamp information. |
| Starter rules | Give every `DecisionDetail` assignment the same struct fields and regenerate the canonical example. |
| Export | Protect multiline identity comments from changing YAML structure and report invalid UTF-8 imports without crashing the app. |

## Verification and deployment boundary

Regression coverage includes canonical compile/export round trips, exact values,
current function contracts, browser recovery, runtime behavior and Streamlit
interactions. Run the suite and lint with:

```powershell
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check app.py studio scripts tests
```

Verified on 2026-09-05: **138 tests passed**, Ruff passed, and `git diff --check`
passed. A local browser pass verified authoring controls, full audit output with
engine 3.0 identity, all 10 starter rows with zero errors, and enabled canonical
YAML export. Automated Streamlit tests also exercise invalid edits across tabs,
export/evaluation blocking, correction, ordering controls, and live previews.

The vendored source is checked without local modifications to engine semantics.
Sample schema validation runs without starting Spark. It cannot establish the
schema, keys, permissions, or persistence behavior of a remote Databricks table.
Those require checks in the target workspace when Databricks Apps is available.

The UI remains Streamlit. `app.yaml` retains the Databricks Apps entrypoint;
Streamlit Cloud continues to install the vendored engine without credentials for
a second private repository. This change does not deploy either host.
