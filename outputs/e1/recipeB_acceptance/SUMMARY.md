# Recipe B acceptance run (2026-10-21, after the fifth review)

What was run: `run_recipeB.sh`, assembled mechanically from the code blocks of the corrected `docs/REPRODUCE_E1.md`
("Common preparation" with RECIPE=B, then recipe B and its comparison block, verbatim). Only two edits: the two
`/path/to/...` placeholders were filled in, and the nine raw Olist CSVs were copied into `data/raw/` (the guide's
comment step). Input: a fresh extraction of the sealed `olist-e1-snapshot-v2.zip` (2b113576…26b4). Environment:
Python 3.13.16, Linux x86_64 (the recorded E1 environment).

Result (exit 0; `recipeB.log.gz`, `comparison.json`):
- the fingerprint check read `$SAVED/freeze/FREEZE.json` and matched the historical scoring code;
- raw CSVs match `outputs/qa/source_manifest.csv` (9 / 9);
- stages 1–7 and E1 prep, select, fit-freeze, score all completed;
- `policy_table.csv` and `linear_ablation.csv`: no diff; H1, H2, H3 and M_vs_olist in results.json equal;
- 22 files byte-identical; every other result table equal in content (gzip headers and run metadata differ);
  E per-order promises, C predictions, V predictions and bootstrap draws equal; freeze shifts, partition id hashes,
  all 9 model-file hashes and the scoring-code fingerprint equal; selection.json, FIT_SUMMARY.json and results.json
  equal apart from runtimes and registration hashes.
- Expected differences: the saved `select/` came from the first selection run (before the publish-last fix), so its
  post-run check list is shorter and its aborted-attempt logs have no counterpart; the rerun's selection equals both
  the saved `select/` and `select_repro1/` in content.

Not covered: no cross-environment check (same Python 3.13.16 as recorded).

## Recipe C (added the same day)

`run_recipeC.sh` (same construction, `RECIPE=C`, separate WORK and SAVED directories, current hardened `src/`) also
completed (exit 0, `recipeC.log.gz`): stages 1–7 and E1 prep / select / fit-freeze / score ran; the new FREEZE.json
records input content hashes inline; `policy_table.csv` is identical to the saved one and H1, H2, H3 and
M_vs_olist equal. Its freeze hash differs from the historical one, as the guide says it should.
