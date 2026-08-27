# Runtime parity

Rules Engine Studio does not contain a preview evaluator.

| Studio operation | Authoritative implementation |
|---|---|
| Authoring choices and function metadata | `rules_engine.build_authoring_manifest` |
| Draft compilation | `rules_engine.compiler_yaml.YamlRulesetCompiler` |
| Semantic validation | `rules_engine.validator.RulesetValidator` |
| YAML export | `rules_engine.exporter_yaml.YamlRulesetExporter` |
| Function implementations | `FunctionRegistry` populated by `register_standard_functions` |
| Row evaluation | `rules_engine.runtime.SparkRowEvaluator` |

`SparkRowEvaluator` is the production row implementation used inside Spark
workers. The studio invokes it directly against uploaded Python row mappings,
which avoids starting a Spark session while retaining engine comparison, null,
assignment, stop-on-match, assigned-value, and custom-function behavior.

The studio adds presentation and authoring guidance only:

- Exceptions are captured per test row and displayed in an `error` field.
- Missing fields in the uploaded test data are authoring warnings. They are not
  engine validation issues.
- Focused rule, condition, and assignment tests reproduce assignments committed
  by earlier rules before invoking the production evaluator.
- Sample values infer advisory field types used to hide predictably incompatible
  editor choices. Unknown and mixed fields remain available, and the production
  compiler and validator still make the final decision.

The manifest supplies authoring-time behavior and the semantic validator checks
complete documents. Uploaded CSV data does not provide authoritative Spark
precision, nullability, or production table metadata, so the Studio does not
claim production-schema compatibility.

The dependency is pinned to a specific `rules_engine` commit. Updating that pin
must be accompanied by the contract tests in `tests/test_studio.py`.
