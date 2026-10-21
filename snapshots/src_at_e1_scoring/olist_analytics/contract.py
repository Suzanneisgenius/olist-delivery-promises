"""Execute the data contract: keys, required fields, parse failures, allowed values,
zip format, foreign-key coverage. Returns one result row per check."""
from __future__ import annotations

import pandas as pd

from .io import CONTRACT


def _row(table, check, n, total, policy, detail=""):
    status = "PASS" if n == 0 else ("FAIL" if policy == "hard" else "WARN")
    return {"table": table, "check": check, "violations": int(n), "rows": int(total),
            "status": status, "policy": policy, "detail": detail}


def check_contract(t: dict[str, pd.DataFrame], raw_strings: dict[str, pd.DataFrame] | None = None) -> pd.DataFrame:
    out = []
    for name, spec in CONTRACT.items():
        df = t[name]
        n = len(df)
        if spec["key"]:
            dup = df.duplicated(spec["key"], keep=False).sum()
            out.append(_row(name, f"unique key ({'+'.join(spec['key'])})", dup, n, "hard"))
        for c in spec.get("required", []):
            out.append(_row(name, f"required: {c}", df[c].isna().sum(), n, "hard" if c in spec["key"] else "soft"))
        for c, allowed in spec.get("allowed", {}).items():
            bad = ~df[c].isin(allowed) & df[c].notna()
            out.append(_row(name, f"allowed values: {c}", bad.sum(), n, "hard"))
        for c in spec.get("zip", []):
            bad = ~df[c].fillna("").str.fullmatch(r"\d{5}")
            out.append(_row(name, f"zip prefix is 5 digits (string): {c}", bad.sum(), n, "hard"))
        if raw_strings is not None:                     # parse failures = value present but unparseable
            raw = raw_strings[name]
            for c in spec.get("datetimes", []) + spec.get("numeric", []):
                bad = raw[c].notna() & df[c].isna()
                out.append(_row(name, f"parses: {c}", bad.sum(), n, "hard"))
        for c, ref in spec.get("foreign_keys", {}).items():
            rt, rc = ref.split(".")
            miss = ~df[c].isin(t[rt][rc]) & df[c].notna()
            out.append(_row(name, f"foreign key {c} -> {ref}", miss.sum(), n, "soft",
                            "rows whose reference is absent; handled per use, not dropped globally"))
    return pd.DataFrame(out)
