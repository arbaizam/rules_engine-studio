# Vendored rules-engine snapshot

The `rules_engine/` package is an unmodified source snapshot of:

- Repository: `https://github.com/arbaizam/rules_engine`
- Commit: `667f80d5fa9e660687268d9752b53fbaced2e8f1`
- Package version: `2.1`

The snapshot is stored in this repository because Streamlit Community Cloud
can authenticate while checking out this private application repository, but
its Python dependency installer cannot authenticate to a second private Git
repository referenced from `requirements.txt`.

When upgrading the production engine, replace every file in `rules_engine/`
from the new pinned commit as one atomic change, update the commit above, and
run the complete Studio test suite before deployment.
