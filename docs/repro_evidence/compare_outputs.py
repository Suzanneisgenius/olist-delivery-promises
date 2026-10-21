"""Compare two outputs/ folders file by file and keep a full manifest (SHA-256 of every file on both sides).

    python compare_outputs.py <outputs_a> <outputs_b> <out.json>

Skips history/ and screenshots. The JSON lists, for every relative path, the hash on each side and its status
(identical / different / only_a / only_b), so the comparison can be re-checked without the original folders.
"""
import hashlib
import json
import pathlib
import sys

a, b, out = map(pathlib.Path, sys.argv[1:4])


def files(root):
    return {p.relative_to(root).as_posix(): p for p in root.rglob("*")
            if p.is_file() and "history" not in p.parts and "screens" not in p.parts}


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


fa, fb = files(a), files(b)
manifest = {}
for k in sorted(set(fa) | set(fb)):
    ha, hb = (sha(fa[k]) if k in fa else None), (sha(fb[k]) if k in fb else None)
    status = "only_b" if ha is None else "only_a" if hb is None else "identical" if ha == hb else "different"
    manifest[k] = {"a": ha, "b": hb, "status": status}
counts = {s: sum(v["status"] == s for v in manifest.values()) for s in ("identical", "different", "only_a", "only_b")}
out.write_text(json.dumps({"a": str(a), "b": str(b), "counts": counts, "files": manifest}, indent=1))
print(counts)
