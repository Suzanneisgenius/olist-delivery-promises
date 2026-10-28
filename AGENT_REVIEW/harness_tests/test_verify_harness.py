"""Tests of the verification harness itself: AGENT_REVIEW/verify_all.sh and the scripts it runs (its step 11).

Kept outside tests/ on purpose: the registered suite is fixed at 362 tests (claim C17), and pyproject's testpaths
collects only tests/. Every test works in a fresh copy of the package, so the evidence in this tree is never touched.
Step 06 (the full test suite) and step 11 itself are never run from here.
"""
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BASH = shutil.which("bash")
SAVED = ["outputs/e1/final_recheck/recheck.json", "outputs/e1/score_verification.csv",
         "outputs/e1/supplementary_verification.csv", "outputs/e1/posthoc/e_olist_interval.json"]
WRITING_STEPS = ["01_manifest", "07_recompute_E", "08_recompute_supp", "09_claims", "10_final_recheck"]
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()


@pytest.fixture
def pkg(tmp_path):
    dst = tmp_path / "pkg"
    shutil.copytree(ROOT, dst, symlinks=True,
                    ignore=shutil.ignore_patterns(".git", ".venv", "verify_output", "__pycache__", ".pytest_cache"))
    yield dst
    shutil.rmtree(dst, ignore_errors=True)


def env_for(tmp_path, hide_pdf_tools=False):
    """`python3` is this interpreter. With hide_pdf_tools, PATH holds only what verify_all.sh needs (no pdftotext)
    and a stub `pypdf` that raises ImportError comes first on the import path."""
    bin_ = tmp_path / "bin"
    bin_.mkdir(exist_ok=True)
    pythonpath = ""
    if hide_pdf_tools:
        stub = tmp_path / "stub/pypdf"
        stub.mkdir(parents=True, exist_ok=True)
        (stub / "__init__.py").write_text('raise ImportError("pypdf hidden by the harness test")\n')
        pythonpath = f"{stub.parent}" + "${PYTHONPATH:+:$PYTHONPATH}"
        for tool in ("bash", "sh", "sha256sum", "cut", "head", "grep", "mkdir", "dirname", "cat", "env"):
            if shutil.which(tool) and not (bin_ / tool).exists():
                (bin_ / tool).symlink_to(shutil.which(tool))
    py = bin_ / "python3"
    py.write_text("#!/bin/sh\n" + (f'PYTHONPATH="{pythonpath}" ' if pythonpath else "") + f'exec "{sys.executable}" "$@"\n')
    py.chmod(0o755)
    return {**os.environ, "PATH": str(bin_) if hide_pdf_tools else f"{bin_}{os.pathsep}{os.environ['PATH']}"}


def run(args, cwd, env=None):
    return subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True, timeout=900)


def has_pdf_extractor():
    try:
        import pypdf  # noqa: F401
    except ImportError:
        return shutil.which("pdftotext") is not None
    return True


def test_missing_pdf_tools_is_skip_never_pass(pkg, tmp_path):
    env = env_for(tmp_path, hide_pdf_tools=True)
    r = run([BASH, "AGENT_REVIEW/verify_all.sh", "10_final_recheck"], pkg, env)
    assert r.returncode == 3, r.stdout + r.stderr
    assert "PREFLIGHT NOTE" in r.stdout
    assert "SKIP  10_final_recheck" in r.stdout and "PASS  10_final_recheck" not in r.stdout
    assert "PASSED WITH SKIPS (1)" in r.stdout and "ALL CHECKS PASSED" not in r.stdout
    rec = json.loads((pkg / "AGENT_REVIEW/verify_output/recheck.json").read_text())
    assert rec["4_documents"]["status"] == "SKIP" and rec["4_documents"]["ok"] is False
    assert rec["status"] == "SKIP" and rec["all_ok"] is False
    strict = run([BASH, "AGENT_REVIEW/verify_all.sh", "--strict", "10_final_recheck"], pkg, env)
    assert strict.returncode == 1 and "FAIL  10_final_recheck" in strict.stdout, strict.stdout
    assert "CHECKS PASSED" not in strict.stdout


@pytest.mark.parametrize("damage", ["garbage", "truncated", "empty"])
def test_unreadable_pdf_is_fail_not_crash(pkg, tmp_path, damage):
    pdf = pkg / "documents/current/E1_main_report.pdf"
    pdf.write_bytes({"garbage": b"%PDF-1.7\nnot really a pdf\n" * 50, "truncated": pdf.read_bytes()[:2000],
                     "empty": b""}[damage])
    v = run([BASH, "AGENT_REVIEW/verify_all.sh", "10_final_recheck"], pkg, env_for(tmp_path))
    log = (pkg / "AGENT_REVIEW/verify_output/10_final_recheck.log").read_text()
    assert "Traceback" not in log, log
    part = json.loads((pkg / "AGENT_REVIEW/verify_output/recheck.json").read_text())["4_documents"]
    if not has_pdf_extractor():        # nothing can read the PDF here: the part must be SKIP, never PASS
        assert v.returncode == 3 and part["status"] == "SKIP", v.stdout + log
        return
    assert v.returncode == 1 and "FAIL  10_final_recheck" in v.stdout, v.stdout + log
    assert part["status"] == "FAIL" and part["ok"] is False
    if damage != "truncated":          # a truncated file may still yield some text; then the wording checks fail
        assert "E1_main_report.pdf" in part["unreadable"]


def test_two_runs_leave_the_evidence_unchanged(pkg, tmp_path):
    """A run without PDF tools changes no manifest-listed file, so a second run passes step 01 too."""
    env = env_for(tmp_path, hide_pdf_tools=True)
    if (ROOT / ".git").is_dir():
        shutil.copytree(ROOT / ".git", pkg / ".git", symlinks=True)
    git = (pkg / ".git").exists() and shutil.which("git")
    status = lambda: run(["git", "status", "--porcelain"], pkg).stdout
    before, git_before = {p: sha(pkg / p) for p in SAVED}, git and status()
    for i in (1, 2):
        r = run([BASH, "AGENT_REVIEW/verify_all.sh", *WRITING_STEPS], pkg, env)
        assert "PASS  01_manifest" in r.stdout and "FAIL" not in r.stdout, f"run {i}:\n{r.stdout}"
        assert r.returncode == 3 and "SKIP  10_final_recheck" in r.stdout, f"run {i}:\n{r.stdout}"
    assert {p: sha(pkg / p) for p in SAVED} == before
    assert run(["sha256sum", "-c", "AGENT_REVIEW/PACKAGE_MANIFEST.sha256", "--quiet"], pkg).returncode == 0
    if git:
        assert status() == git_before


def test_runs_from_a_symlinked_path(pkg, tmp_path):
    """Started from a path through a symlink (on macOS /tmp is one), verify_all.sh must hand Python the physical path:
    the entry-module provenance checks compare module files with the resolved package path. Through the symlink,
    tests/test_e1_final.py failed (review 2026-10-27, 1 failed and 19 errors in step 06)."""
    link = tmp_path / "via_symlink"
    link.symlink_to(pkg, target_is_directory=True)
    env = env_for(tmp_path)
    seen = tmp_path / "seen_by_python3.txt"
    py = tmp_path / "bin/python3"
    py.write_text(f'#!/bin/sh\necho "$PWD|$PYTHONPATH" >> "{seen}"\nexec "{sys.executable}" "$@"\n')
    shell_env = {**env, "PWD": str(link)}          # as a shell started in the symlinked folder would have it
    r = run([BASH, "AGENT_REVIEW/verify_all.sh", "02_config_hash"], link, shell_env)
    assert r.returncode == 0 and "PASS  02_config_hash" in r.stdout, r.stdout + r.stderr
    pwd, pythonpath = seen.read_text().splitlines()[0].split("|")
    t = run([sys.executable, "-m", "pytest", "-q", "-p", "no:cacheprovider", "tests/test_e1_final.py"], pwd,
            {**os.environ, "PWD": pwd, "PYTHONPATH": pythonpath})    # the paths verify_all.sh gave its python3
    assert t.returncode == 0, t.stdout[-3000:] + t.stderr[-2000:]
    assert (pwd, pythonpath) == (str(pkg.resolve()), str(pkg.resolve() / "src"))


def test_recompute_compares_with_the_saved_copy(pkg):
    saved = pkg / "outputs/e1/posthoc/e_olist_interval.json"
    d = json.loads(saved.read_text())
    d["Cstar@0.9126"]["day_diff_ci95_iid"][0] += 0.01
    saved.write_text(json.dumps(d, indent=2))
    tampered = sha(saved)
    r = run([sys.executable, "scripts/e1_verify_score.py"], pkg, {**os.environ, "PYTHONPATH": str(pkg / "src")})
    assert r.returncode == 1 and "reproduced to within 1e-9: False" in r.stdout, r.stdout + r.stderr
    assert sha(saved) == tampered
