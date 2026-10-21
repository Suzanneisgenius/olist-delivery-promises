"""Load raw Olist tables exactly as the data contract describes, and fingerprint them."""
from __future__ import annotations

import hashlib
from pathlib import Path

import pandas as pd
import yaml

ROOT = Path(__file__).resolve().parents[2]


def load_yaml(name: str) -> dict:
    return yaml.safe_load((ROOT / "config" / name).read_text(encoding="utf-8"))


CONTRACT = load_yaml("data_contract.yaml")["tables"]
ASSUMPTIONS = load_yaml("assumptions.yaml")


def raw_dir() -> Path:
    return ROOT / ASSUMPTIONS["data"]["raw_dir"]


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def read_table(name: str, directory: Path | None = None) -> pd.DataFrame:
    """Every column is read as string first, so IDs and zip prefixes keep
    leading zeros; only contract-declared columns are converted."""
    spec = CONTRACT[name]
    path = (directory or raw_dir()) / spec["file"]
    df = pd.read_csv(path, dtype=str, keep_default_na=False, na_values=[""])
    # 1-based record number in the file. NOT a physical line number: review comments
    # contain embedded newlines, so one record can span several lines.
    df.insert(0, "source_record_no", range(1, len(df) + 1))
    for c in spec.get("datetimes", []):
        df[c] = pd.to_datetime(df[c], errors="coerce", format="%Y-%m-%d %H:%M:%S")
    for c in spec.get("numeric", []):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def load_all(directory: Path | None = None) -> dict[str, pd.DataFrame]:
    return {name: read_table(name, directory) for name in CONTRACT}


def source_manifest(directory: Path | None = None) -> pd.DataFrame:
    d = directory or raw_dir()
    rows = []
    for name, spec in CONTRACT.items():
        p = d / spec["file"]
        df = pd.read_csv(p, dtype=str)                    # record count, not line count:
        lines = sum(1 for _ in open(p, encoding="utf-8")) - 1   # review comments contain newlines
        rows.append({"table": name, "file": spec["file"], "bytes": p.stat().st_size, "records": len(df),
                     "physical_lines": lines, "columns": len(df.columns), "sha256": sha256(p)})
    return pd.DataFrame(rows)
