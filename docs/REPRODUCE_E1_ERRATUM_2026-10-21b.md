# Erratum to REPRODUCE_E1.md (second, 2026-10-21, after the fifth review)

Applies to the guide shipped in the sealed `olist-e1-snapshot-v2.zip` and in review packages r2–r4. The sealed
archive is not changed; the corrected guide is `docs/REPRODUCE_E1.md` in this package.

1. **Recipe B read the freeze after it had been moved.** The common preparation moves `outputs/e1/freeze` aside,
   but recipe B's fingerprint check still opened `outputs/e1/freeze/FREEZE.json`, which no longer exists there.
   It now reads the saved copy, `$SAVED/freeze/FREEZE.json`, and the comparison commands read `$SAVED/...` too.
2. **One saved directory per recipe.** Recipes B and C used the same `../e1_saved`, so a second preparation could
   nest or overwrite the first. Each recipe now sets `RECIPE`, `WORK=/path/to/e1-rerun-$RECIPE` and
   `SAVED="$WORK-saved"`; `mkdir "$SAVED"` fails rather than overwrite.
3. **Test count.** The comment now reads 362 for the r5 review package (345 in r4; 317 in the sealed v2 snapshot).

No result, freeze record or source file is affected.

Verification: see the 2026-10-21 row on the fifth review in `docs/E1_DECISIONS.md` and
`outputs/e1/recipeB_acceptance/` for an end-to-end run of the corrected recipe B, executed from the guide's own code
blocks in a fresh extraction of the sealed v2 snapshot.
