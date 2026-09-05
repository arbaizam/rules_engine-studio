# Vendored rules-engine snapshot

The `rules_engine/` package is an unmodified source snapshot of:

- Repository: `https://github.com/arbaizam/rules_engine`
- Branch: `simplify_harden` (the refactor branch, ahead of `main`)
- Commit: `ad26d54a8b57fd359b3ff3c0b9addf87f9b43f3f`
- Package version: `3.0`

The snapshot is stored in this repository because Streamlit Community Cloud
can authenticate while checking out this private application repository, but
its Python dependency installer cannot authenticate to a second private Git
repository referenced from `requirements.txt`.

The per-file SHA-256 manifest is in `rules_engine_snapshot.json`. The integrity
test checks every vendored source file against that manifest. Studio adapters
target this contract directly; there is no fallback to the 2.1 APIs.

To reproduce this snapshot from a local production checkout:

```powershell
.venv/Scripts/python.exe scripts/vendor_rules_engine.py ../rules_engine
```

To upgrade, set `PINNED_COMMIT` in that script, update this provenance and the
snapshot test, run the script with `--commit <full-commit-hash>`, and run the
complete Studio test suite. The script reads Git objects from the selected
commit, so uncommitted source changes cannot leak into the snapshot.
