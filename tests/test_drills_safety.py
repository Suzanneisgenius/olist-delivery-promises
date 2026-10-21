"""The failure-drill script must never delete its backup unless the raw files were restored intact."""
import os
import pathlib
import shutil
import subprocess

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "docs" / "repro_evidence" / "failure_drills.sh"
RAW = ["olist_customers_dataset.csv", "olist_geolocation_dataset.csv", "olist_order_items_dataset.csv",
       "olist_order_payments_dataset.csv", "olist_order_reviews_dataset.csv", "olist_orders_dataset.csv",
       "olist_products_dataset.csv", "olist_sellers_dataset.csv", "product_category_name_translation.csv"]

pytestmark = pytest.mark.skipif(shutil.which("bash") is None or shutil.which("cmp") is None, reason="needs bash and cmp")


def fake_project(tmp_path, py_body):
    proj = tmp_path / "proj"
    (proj / "src" / "olist_analytics").mkdir(parents=True)
    (proj / "pyproject.toml").write_text("")
    raw = proj / "data" / "raw"
    raw.mkdir(parents=True)
    for f in RAW:
        (raw / f).write_text(f"original {f}\n")
    py = tmp_path / "fakepy"
    py.write_text("#!/usr/bin/env bash\n" + py_body)
    py.chmod(0o755)
    tmp = tmp_path / "tmp"
    tmp.mkdir()
    return proj, py, tmp


def run(proj, py, tmp, ev):
    env = dict(os.environ, TMPDIR=str(tmp))
    return subprocess.run(["bash", str(SCRIPT), str(proj), str(py), str(ev)], env=env, capture_output=True, text=True)


def test_backup_is_removed_after_a_clean_restore(tmp_path):
    # the baseline run fails after damaging a raw file: the script stops, restores and cleans up
    proj, py, tmp = fake_project(tmp_path, 'echo damaged > data/raw/olist_orders_dataset.csv; exit 1\n')
    r = run(proj, py, tmp, tmp_path / "ev")
    assert r.returncode != 0
    assert (proj / "data" / "raw" / "olist_orders_dataset.csv").read_text() == "original olist_orders_dataset.csv\n"
    assert list(tmp.glob("olist_drills.*")) == []


def test_backup_is_kept_when_restore_fails(tmp_path):
    # the run replaces the raw folder with a file, so copying back fails: the backup must survive
    proj, py, tmp = fake_project(tmp_path, 'rm -rf data/raw && echo x > data/raw; exit 1\n')
    r = run(proj, py, tmp, tmp_path / "ev")
    assert r.returncode != 0 and "KEPT" in r.stderr
    kept = list(tmp.glob("olist_drills.*"))
    assert len(kept) == 1 and sorted(p.name for p in kept[0].iterdir()) == sorted(RAW)
