# Rules Engine Studio

Streamlit authoring and test surface for the canonical
[`rules_engine`](https://github.com/arbaizam/rules_engine) metadata contract.

The studio edits mutable drafts, but it does not maintain its own rule dialect.
Every validation, YAML import/export, custom-function contract, and row test is
delegated to the pinned production package. Editor choices are built from the
engine-owned authoring manifest using the same function registry as validation
and evaluation.

The current engine is **3.0**, pinned to refactor branch `simplify_harden` at
`ad26d54a8b57fd359b3ff3c0b9addf87f9b43f3f`. Studio targets this contract directly.

## Capabilities

- Author ordered rules with nested `all` / `any` groups.
- Navigate and reorder rules in one list: click, tap, or press Enter to open;
  drag, use the arrow keys, or use the always-available move buttons to reorder.
- Recover the in-progress ruleset and sample rows from browser-local autosave
  after a reload or deployment restart.
- Configure all canonical operands: `field`, `assigned`, `literal`, and
  `custom_function`.
- Configure operand null defaults, condition tolerances, null errors, active
  flags, assignment IDs, and stop-on-match behavior.
- Filter operators, fields, literals, functions, and prior assignments using
  value types inferred from the current sample data. Unknown and mixed columns
  remain available and are labeled instead of being silently discarded.
- Select all 58 standard functions from the engine registry and author their
  exact named argument contracts.
- Upload CSV, TSV, JSON, or Parquet test data and edit it in the browser.
- Evaluate one condition, rule, assignment, row, or the entire uploaded file
  with the production row evaluator and Spark worker result contract.
- Import and export YAML through `YamlRulesetCompiler` and
  `YamlRulesetExporter`.
- Watch a collapsible, read-only YAML preview update beside the active editor,
  follow the selected rule, and remain viewport-aligned while authoring,
  including best-effort draft syntax while production validation is blocked.
- Validate through `RulesetValidator` before export.

## Run locally

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\streamlit.exe run app.py
```

The default Streamlit theme is dark. The in-progress ruleset and sample rows
are autosaved only in the current browser. Evaluated CSV and canonical YAML
remain explicit downloads.

## Architecture

| Path | Responsibility |
|---|---|
| `studio/authoring.py` | Cached engine manifest, shared registry, compiler, and semantic validator adapter |
| `studio/schema.py` | Mutable draft models plus Studio-owned labels and widget state |
| `studio/custom_functions.py` | Manifest-backed function metadata and runtime calls |
| `studio/engine.py` | Production row evaluation, sample schema preparation, and Spark worker results |
| `studio/yaml_io.py` | Production compiler, exporter, and validator adapter |
| `studio/ui/` | Streamlit authoring and test views |
| `studio/ui/reorder.py` | Integrated mouse, touch, and keyboard rule sorter |
| `studio/ui/yaml_preview.py` | Cached live YAML snapshot and collapsible right-side preview |
| `studio/ui/browser_state.py` | Strict-JSON browser-local working-draft recovery |
| `studio/sample_data.py` | Valid starter ruleset and representative rows |
| `studio/type_compatibility.py` | Sample-value type inference and compatibility filtering |
| `tests/test_studio.py` | Contract, registry, YAML, CSV, and runtime tests |

The exact `rules_engine` source used by local and Streamlit Cloud installs is
vendored from a pinned production commit. See
[`docs/VENDORED_RULES_ENGINE.md`](docs/VENDORED_RULES_ENGINE.md) for provenance
and upgrade instructions.

Sample evaluation uses the engine's Spark compatibility validator against types
inferred from the uploaded rows. These checks describe the sample, not a remote
table. Exact production compatibility requires validating against the actual
Databricks DataFrame schema. No Spark session or JVM is needed for Studio's
local row tests.

JSON sample imports preserve exact decimal numbers and reject duplicate keys.
Date-named columns are inferred as dates only when every non-null value is a
valid date-only value. Invalid date text and timestamp strings remain visible;
use explicit conversion functions for text that needs parsing. CSV type inference
is advisory; use JSON or Parquet when explicit value types matter.

## Hosting

Streamlit remains the UI framework for both Streamlit Cloud and the eventual
Databricks Apps deployment. `app.yaml` supplies the Streamlit entrypoint for
Databricks Apps; enabling Apps and configuring a remote workspace is separate
from this local authoring surface. Browser autosave is specific to the hosting
origin, so download canonical YAML to transfer drafts between hosts.

The checked-in examples are generated from the same canonical starter project:

```powershell
.\.venv\Scripts\python.exe scripts\regenerate_examples.py
```
