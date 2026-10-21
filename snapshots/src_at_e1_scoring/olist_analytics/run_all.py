"""Rebuild everything from the nine raw CSVs, in order:

    stage 1 → stage 2 → stage 3 → independent verification → stage 4 → stage 5 (backtest) → stage 7 (date policy)
    → stage 7 part 3 (monitoring)

    PYTHONPATH=src python -m olist_analytics.run_all

Stops at the first failure and exits non-zero. Each stage leaves its own RELEASE_BLOCKED.json;
a failed verification leaves outputs/stage3/qa/VERIFY_FAILED.json and stage 4 does not run.
Stage 3 removes the previous verification, so stage 4 can never consume evidence from an older run.
Browser checks and UAT come after this (see docs/refresh_checklist.md).
"""
from __future__ import annotations

import subprocess
import sys
import time

from . import run_stage1, run_stage2, run_stage3, run_stage4, run_stage5, run_stage7, run_stage7_monitor
from .io import ROOT


class VerificationFailed(SystemExit):
    pass


def verify_stage3() -> None:
    """Run the verifier in an isolated interpreter (-I: no project modules on the path)."""
    r = subprocess.run([sys.executable, "-I", str(ROOT / "scripts" / "verify_stage3.py")])
    if r.returncode != 0:
        raise VerificationFailed("independent verification failed; stage 4 not run "
                                 "(see outputs/stage3/qa/VERIFY_FAILED.json)")


STEPS = [("stage 1", run_stage1.main), ("stage 2", run_stage2.main), ("stage 3", run_stage3.main),
         ("independent verification", verify_stage3), ("stage 4", run_stage4.main),
         ("stage 5 (backtest)", run_stage5.main), ("stage 7 (date policy)", run_stage7.main),
         ("stage 7 part 3 (monitoring)", run_stage7_monitor.main)]


def main(steps=None) -> list[str]:
    done = []
    for name, fn in steps or STEPS:
        t = time.time()
        fn()
        done.append(name)
        print(f"{name}: ok ({time.time() - t:.0f}s)")
    print("Pages: outputs/weekly_review.html · outputs/data_quality.html · outputs/model_report.html")
    return done


if __name__ == "__main__":
    main()
