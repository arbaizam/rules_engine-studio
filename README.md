# Rules Engine Studio

A Streamlit workbench for authoring, validating, and testing executable business rules.

The studio combines structured condition editing, outcome configuration, decision traces, rule ordering, and portable JSON rulebooks in one compact workspace.

## What is included

- Compact rule editor with effective-logic previews
- Optional transaction, support, and commerce templates
- Custom text, number, yes/no, and date fields
- `ALL` / `ANY` condition groups and type-appropriate comparisons
- Live tests with matching and non-matching sample records
- Condition-by-condition decision explanations
- Rule library with priorities, active/inactive status, copy, edit, and delete
- Automatic local saves plus JSON import/export
- A framework-independent evaluator with unit tests

## Run locally

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
streamlit run app.py
```

Open the local URL Streamlit prints, normally `http://localhost:8501`.

## Workflow

1. Define or load the field schema.
2. Author conditions, match mode, priority, and outcome.
3. Save the rule and run records through the test bench.
4. Inspect the condition trace and adjust the rule.
5. Export the rulebook JSON for integration or version control.

Saved rules are written to `data/rulebook.json`. This runtime file is intentionally ignored by Git; the examples remain available as a clean first-run experience.

## Run tests

The evaluator and storage tests use only the Python standard library:

```powershell
python -m unittest discover -v
```

## Project layout

```text
app.py                     Streamlit interface
rules_engine/models.py     Serializable rule model
rules_engine/engine.py     Evaluation and human-readable traces
rules_engine/examples.py   Starter scenarios and sample records
rules_engine/storage.py    Local JSON persistence and import/export
tests/                     Evaluator and storage regression tests
```

The JSON file is intentionally straightforward so another service can consume it without depending on Streamlit. Rules run in ascending priority order, and inactive rules are skipped when evaluating a full rulebook.
