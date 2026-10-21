# E1 freeze record — template (`outputs/e1/freeze/FREEZE.json` + `FREEZE.sha256`)

Written once, at execution step 5, after all final models are fitted on F and all shifts are computed on C.
`e1_freeze.write_freeze` refuses an incomplete or malformed record and writes the record's own SHA-256 next to it; that
hash is also reported to the owner. `e1_freeze.require_frozen` re-checks everything before any evaluation-set (E)
number is computed; any gap or change stops the run. Until the record exists, no run (B series included) may produce an
E comparison. Debugging before the freeze may check inputs, shapes and finiteness only.

| Key | Content | Checked at E time by |
|---|---|---|
| `config_sha256` | SHA-256 of `config/date_model_e1.yaml` | must equal the file AND the latest registered hash |
| `partition_id_sha256` | exactly `{F0, V, F, C, E}` → SHA-256 of the sorted order ids | recomputed from the ids actually scored |
| `runs` | the 9 registered E runs (`B1@0.90`, `B1c@0.90`, `B2@0.90`, `B3@0.90`, `Cstar@0.90`, `Dstar@0.90`, `B1c@0.9126`, `Cstar@0.9126`, `Dstar@0.9126`) → `{"status": "frozen"}` or `{"status": "failed", "reason": ...}` | no run may be missing or added; failed → "not evaluable" |
| `feature_rules` | per frozen run: `snapshot` (U / O / none, must match the registration) and the feature list | schema |
| `preprocessing_and_selected_hyperparameters` | per frozen run: model family, q, target scale, dow encoding, alpha, solver (fallback used?), HGB depth / iterations; V losses of every candidate, including failures | schema (family and q must match) |
| `fitted_model_files_sha256` | per frozen run: `{"path": "outputs/e1/models/<run>.joblib", "sha256": ...}` | every file re-hashed |
| `shifts_by_policy_and_q` | per shifted run: `{"n": 17056, "k": ceil((n+1)q), "shift_days": finite}` | n, k checked; shift recomputed on C from the frozen model |
| `scoring_code_sha256`, `code_files_sha256` | combined hash and per-file hashes of every `.py` in `src/olist_analytics` (features, date policy, E1 modules, I/O) | recomputed; the changed file is named |
| `environment` | numpy, pandas, scipy, scikit-learn versions | must match |
| `thresholds` | `e1_freeze.THRESHOLDS`: practical rule (1 day / 1 pt), monthly rule (1,000 orders / 3 pts), H1 (0.5 day / 0.5 pt), H2 (g ≥ 2%, interval upper end < 0), ties (0.001 / 0.01), bootstrap (2,000, seed 20261015, week) | must equal the constants the verdict functions use |

Also stored next to it: `frozen_at` (UTC).
