"""Package source and aggregate evidence only; exclude raw and order-level records."""
import hashlib
import json
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile

root = Path(__file__).resolve().parents[1]
destination = Path(sys.argv[1])
destination.parent.mkdir(parents=True, exist_ok=True)
if destination.exists():
    raise SystemExit(f"Refusing to overwrite an existing package: {destination}")
files = []
for p in sorted(root.rglob('*')):
    if not p.is_file():
        continue
    rel = p.relative_to(root)
    if any(x in rel.parts for x in ['__pycache__', '.pytest_cache', '.venv', 'history']):
        continue
    if rel.parts[:2] in [('data','raw'), ('outputs','marts')] and p.name != '.gitkeep':
        continue
    files.append(p)
with ZipFile(destination, 'w', ZIP_DEFLATED) as archive:
    for p in files:
        archive.write(p, Path('olist-delivery-risk') / p.relative_to(root))
with ZipFile(destination) as archive:
    assert archive.testzip() is None
    assert not any(x.endswith('.csv') and ('/data/raw/' in x or '/outputs/marts/' in x) for x in archive.namelist())
receipt = {'package': destination.name, 'files': len(files), 'bytes': destination.stat().st_size,
           'sha256': hashlib.sha256(destination.read_bytes()).hexdigest(),
           'raw_data_included': False, 'order_mart_included': False}
(destination.parent / (destination.name+'.json')).write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt,indent=2))
