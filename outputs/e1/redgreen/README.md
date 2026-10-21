# Fix evidence: freeze guard and invalid inputs (checkpoint-2 review 4)

| File | What |
|---|---|
| `fix.diff` | unified diff, checkpoint-2 bundle -> fixed working copy: `e1_freeze.py`, `e1_models.py`, `tests/test_e1.py` |
| `new_behaviour_tests.diff` | `tests/test_e1_red_green.py` (new; behaviour-only, runs on both versions) |
| `red_before_fix.log` | those 33 tests on the PRE-FIX modules: 22 failed, 11 passed |
| `green_after_fix.log` | the same 33 tests on the FIXED modules: 33 passed |

Each log starts with the file path and SHA-256 of the `e1_freeze.py` / `e1_models.py` actually imported.
Pre-fix modules: e1_freeze `83e624c3…bce2b4`, e1_models `812021f0…580e55` (= checkpoint-2 bundle).
Fixed modules: e1_freeze `b1916172…`, e1_models `0ea2895e…`.
The red run overrides the project's pytest `pythonpath` setting (`-o pythonpath=`); without it pytest put the
working copy's `src` first and silently tested the fixed code (a first attempt showed 33 passed for that reason).

The fix was written (patch 1) before these behaviour tests, so "red first" is shown by running the new tests on the
saved pre-fix files, not by a chronological red -> green sequence.

The 11 tests that already passed on the pre-fix code: the untampered-record control; `shift` already rejected
non-finite PREDICTIONS; 99 / 101 predictions for 100 labels failed through numpy's shape error (incidental, not a
deliberate check). Length 1 broadcast silently in `pinball` and `policy_score`.

## Test counts (full suite, `pytest` from the project root)

| Version | Total | of which E1 | Source |
|---|---:|---:|---|
| checkpoint-2 bundle | 185 | 30 (`test_e1.py`) | its `pytest_junit.xml` (tests="185") |
| patch 1 | 243 | 88 (`test_e1.py`) | its `pytest_junit.xml` (tests="243") |
| patch 1 + `test_e1_red_green.py` | 276 | 88 + 33 | 276 = 243 + 33; the "33 new" are counted on top of patch 1 |
| + `test_e1_select.py` (checkpoint 3, step 2) | 286 | 88 + 33 + 10 | run before the selection run |

Non-E1 tests: 155 in every version. Counts are parametrized cases.
