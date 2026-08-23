# Rules Engine Studio

A guided Streamlit app for turning business policy into rules that non-developers can read, test, and share.

The app deliberately keeps technical expressions out of the main workflow. Authors pick familiar data fields, build a **When → Then** sentence, and try realistic records while the studio explains why each condition passed or failed.

## What is included

- Guided rule authoring with plain-language previews
- Transaction review, support priority, and order discount starters
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

## Typical workflow

1. Choose the starter closest to the decision you are automating.
2. Rename the rule and explain why it exists.
3. Define the fields and conditions in the same language your team uses.
4. Choose one concrete outcome and add handoff instructions.
5. Save and test with both a matching and non-matching example.
6. Download the rulebook JSON to share it or put it under version control.

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
