# E1 final fixes — change record (2026-10-21)

Applies to the **final repository version** (main report v6, mathematical note, `notebooks/e1_by_hand.ipynb`).
Scope: wording, one post-hoc helper, the reproduction guide and documentation. `FREEZE.json`, the fitted models, the
registered results and the registered verdicts are unchanged. **No further post-hoc analysis is added to E1.**

## Changes

| # | Item | Change |
|---|---|---|
| 1 | Rounding helper `scripts/e1_rounding_rules.py` | Refuses NaN / ±inf or non-scalar shifts, empty or 2-d predictions, overflowing sums, and labels that are not whole numbers ≥ 1 |
| 2 | One-day minimum | The untruncated identity Y ≤ U ⇔ Y ≤ ⌊U⌋ is now kept separate from the one-day minimum, which can only increase coverage. Subtract-one is described as "not coverage-preserving in general". Boundary tests added for Y = 1, U < 1 and U = 1 |
| 3 | Recipe B (`docs/REPRODUCE_E1.md`) | Reads `$SAVED/freeze/FREEZE.json`, the location the preparation step moved it to. Recipes B and C use separate saved directories. Erratum: `docs/REPRODUCE_E1_ERRATUM_2026-10-21b.md` |
| 4 | Meaning of "coverage ≥ k/n" | Main report table and both versions of the mathematical note now say it is a necessary consequence of the calibration rule. On its own it neither verifies the implementation (a shift wrongly set to 1,000 days would also satisfy it) nor establishes coverage on future orders. The direct check named is recomputing the k-th residual against the frozen shift |
| 5 | Exchangeability of C and E | Main report: "has not been established, so the guarantee is not asserted for E". It no longer says exchangeability fails. No new test |
| 6 | Other main-report and supplement wording | Window sentence narrowed. Rounding up "adds less than a day". Summary reframed around whether a matched procedure gives comparable dates. Test count unified at 362 (317 + 45). Contribution statement: AI review is not peer review; math note and notebook listed; author items left open |
| 7 | Mathematical note (en/zh) | Opening sentence: the results are standard, stated and applied here, not new. Beta paragraph removed. "The mean does not generally minimise the asymmetric loss". "Rounding up adds less than one day; the minimum is a separate adjustment" |
| 8 | Notebook | New "How to run" block: version, run folder, three input files with SHA-256. A check cell names any missing or changed file; sections 1–3 run without them and section 4 stops with a clear message |
| 9 | Repository front page | `README.md` shows the current version only. Old reports are in `documents/archive/`; the pipeline README is in `docs/archive/` |

## Re-verification and where the evidence is

Everything below is in this repository and can be re-run: `bash AGENT_REVIEW/verify_all.sh` (10 steps), or
`python3 scripts/e1_final_recheck.py` for the targeted part.

| Check | Result | Evidence |
|---|---|---|
| Helper guards (`pytest -k refuses`) | 11 passed | `outputs/e1/final_recheck/recheck.json` |
| One-day minimum, boundary cells, counterexamples | 8 passed | same |
| Red/green for the guards | r4 helper: 8 failed; current: 45 passed | `outputs/e1/redgreen_rounding/` |
| Recipe B reads the saved freeze; separate saved directories | yes | `recheck.json`, `docs/REPRODUCE_E1.md` |
| End-to-end reruns from raw CSVs (needs the Kaggle data) | B: policy table, H1–H3, shifts, 9/9 model hashes, E per-order promises equal. C: policy table equal | `outputs/e1/recipeB_acceptance/` (scripts, logs, comparison) |
| Wording: corrected text present, old text absent (main, supplement, note) | 16 / 16 present, 8 / 8 absent | `recheck.json` |
| Freeze, config, scoring-code fingerprint, model files | unchanged | `recheck.json` |
| `results.json`, `policy_table.csv` | byte-identical to the sealed v2 archive | `recheck.json` |
| Full test suite | 362 passed | `AGENT_REVIEW/verify_output/06_pytest.log` after running `verify_all.sh` |
| Notebook | runs top to bottom from `notebooks/`; without inputs, sections 1–3 run and section 4 stops with a message | `notebooks/e1_by_hand.ipynb` (executed), `.html` |

The end-to-end reruns were done by the author's assistant in the recorded environment (Python 3.13.16). They were not
independently repeated by a reviewer. Until they are, they count as author-reported evidence with logs, not as
independent replication.
