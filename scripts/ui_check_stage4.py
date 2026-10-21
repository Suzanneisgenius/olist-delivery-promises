"""Browser checks for the three stage-4 pages (developer UAT evidence, not business sign-off).

    python scripts/ui_check_stage4.py

Needs Playwright with a Chromium build. Opens each page from disk, records console errors,
checks layout at desktop and phone widths, compares displayed numbers with the exports,
exercises the weekly page's controls, and follows the navigation links.
Writes outputs/stage4/ui_checks.csv, outputs/stage4/ui_evidence.json, outputs/stage4/screens/*.png
and outputs/stage4/UI_CHECKS.md. The evidence records the SHA-256 of the three pages it tested and of the
stage-4 lineage; build_uat.py rejects it if the pages have changed since. Exit 1 if any check fails.
"""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import pandas as pd
from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "outputs"
SHOTS = OUT / "stage4" / "screens"
PAGES = ["weekly_review.html", "data_quality.html", "model_report.html"]


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main() -> int:
    SHOTS.mkdir(parents=True, exist_ok=True)
    lineage_path = OUT / "stage4" / "lineage.json"
    if not lineage_path.exists() or (OUT / "stage4" / "qa" / "RELEASE_BLOCKED.json").exists():
        print("no current stage-4 release: run stage 4 first", file=sys.stderr)
        return 1
    lineage = json.loads(lineage_path.read_text())
    before = {n: sha(OUT / n) for n in PAGES}
    sample = pd.read_csv(OUT / "qa" / "manual_check_sample.csv")
    reviewed = f"{int(sample.reviewer_ok.notna().sum())} of {len(sample)}"
    tm = pd.read_csv(OUT / "stage3" / "test_metrics.csv").set_index("model")
    head = json.loads((OUT / "stage3" / "lineage.json").read_text())["headline"]
    facts = json.loads((OUT / "qa" / "stage1_facts.json").read_text())["cohort_proposal"]["selected"]
    pairs = pd.read_csv(OUT / "stage2" / "decomposition_pairs.csv")
    worst = pairs.loc[pairs.change.idxmin()]
    rows = []
    add = lambda case, expected, observed: rows.append(
        {"case": case, "expected": str(expected), "observed": str(observed), "pass": str(expected) == str(observed)})
    by_key = {"weekly_review.html": "weekly", "data_quality.html": "dq", "model_report.html": "model"}
    add("pages under test == pages of the current stage-4 release (SHA-256)", "[]",
        json.dumps([n for n in PAGES if before[n] != lineage["pages"][by_key[n]]]))

    with sync_playwright() as p:
        b = p.chromium.launch()
        for name in PAGES:
            for scheme, width in [("light", 1280), ("dark", 1280), ("light", 390)]:
                pg = b.new_page(viewport={"width": width, "height": 900}, color_scheme=scheme)
                errors = []
                pg.on("console", lambda m, e=errors: e.append(m.text) if m.type == "error" else None)
                pg.on("pageerror", lambda exc, e=errors: e.append(str(exc)))
                pg.goto((OUT / name).as_uri())
                pg.wait_for_timeout(300)
                over = pg.evaluate("document.documentElement.scrollWidth - document.documentElement.clientWidth")
                tag = f"{name} {scheme} {width}px"
                add(f"{tag}: no console or page errors", "[]", json.dumps(errors))
                add(f"{tag}: no page-wide horizontal overflow (px)", 0, max(int(over), 0))
                pg.screenshot(path=str(SHOTS / f"{name[:-5]}_{scheme}_{width}.png"), full_page=True)
                pg.close()

        pg = b.new_page(viewport={"width": 1280, "height": 900})
        pg.goto((OUT / "model_report.html").as_uri())
        txt = lambda key: pg.locator(f'[data-check="{key}"] strong').inner_text()
        add("model page: headline AP shown == test_metrics.csv", f"{tm.loc[head, 'average_precision']:.3f}", txt("ap"))
        add("model page: ROC AUC shown == test_metrics.csv", f"{tm.loc[head, 'roc_auc']:.3f}", txt("auc"))
        add("model page: top-10% precision shown", f"{tm.loc[head, 'precision_at_top'] * 100:.1f}%", txt("p10"))
        add("model page: top-10% recall shown", f"{tm.loc[head, 'recall_at_top'] * 100:.1f}%", txt("r10"))
        add("model page: independent check says all match", True, "all match" in pg.locator('[data-check="verify"]').inner_text())
        pg.click('nav.site a[href="data_quality.html"]')
        add("nav: model → data quality", "data_quality.html", pg.url.rsplit("/", 1)[-1])
        add("data-quality page: orders shown", "99,441", pg.locator('[data-check="orders"] strong').inner_text())
        add("data-quality page: human-reviewed count == manual_check_sample.csv", True,
        f"Human review: {reviewed}" in pg.locator('[data-check="sample"]').inner_text())
        pg.click('nav.site a[href="weekly_review.html"]')
        add("nav: data quality → weekly review", "weekly_review.html", pg.url.rsplit("/", 1)[-1])
        add("weekly page: whole-window on-time shown", f"{facts['otd_rate'] * 100:.2f}%",
            pg.locator("#window-metrics .metric strong").first.inner_text())
        pg.click("#decline")
        s = pg.locator("#pair-summary").inner_text()
        add("weekly page: 'Largest decline' selects the worst pair", f"{worst.change * 100:+.2f}".replace("+", ""),
            s.split("(")[1].split(" ")[0])
        with pg.expect_download() as dl:
            pg.click("details:has(#state-table) summary")
            pg.click("#download-pair")
        csv = pd.read_csv(dl.value.path())
        n_states = len(pd.read_csv(OUT / "stage2" / "decomposition_by_state_all_pairs.csv")
                       .query("current_week == @worst.current_week"))
        add("weekly page: downloaded pair CSV has every state of that pair", n_states, len(csv))
        from urllib.parse import unquote, urlparse
        hrefs = pg.eval_on_selector_all("a[href]", "as => as.map(a => a.href)")
        files = [Path(unquote(urlparse(h).path)) for h in hrefs if h.startswith("file:")]
        add("weekly page: every link target exists on disk (stage-2 links rebased)", "[]",
            json.dumps([str(f.relative_to(OUT)) for f in files if not f.exists()]))
        browser_version = f"chromium {b.version}"
        b.close()

    add("pages unchanged during the browser run (SHA-256)", "[]",
        json.dumps([n for n in PAGES if sha(OUT / n) != before[n]]))
    df = pd.DataFrame(rows)
    df.to_csv(OUT / "stage4" / "ui_checks.csv", index=False)
    (OUT / "stage4" / "ui_evidence.json").write_text(json.dumps({
        "generated_at": pd.Timestamp.now(tz="UTC").isoformat(), "pages_sha256": before,
        "stage4_lineage_sha256": sha(lineage_path), "ui_checks_sha256": sha(OUT / "stage4" / "ui_checks.csv"),
        "checks": len(df), "checks_pass": bool(df["pass"].all()), "browser": browser_version}, indent=2) + "\n")
    lines = ["# Stage 4 browser checks", "",
             f"Pages tested (SHA-256): " + ", ".join(f"`{n}` {h[:12]}…" for n, h in before.items()), "",
             "Run by `scripts/ui_check_stage4.py` (Playwright, headless Chromium) against the generated pages.",
             "Developer evidence only; this is **not** the project owner's business UAT sign-off.", "",
             f"Result: **{int(df['pass'].sum())} of {len(df)} checks pass.** Screenshots: `outputs/stage4/screens/`.", "",
             "| Case | Expected | Observed | Pass |", "|---|---|---|---|"]
    esc = lambda v: str(v).replace("|", "\\|").replace("\n", " ")
    lines += [f"| {esc(r.case)} | {esc(r.expected)} | {esc(r.observed)} | {'yes' if r['pass'] else '**NO**'} |" for _, r in df.iterrows()]
    (OUT / "stage4" / "UI_CHECKS.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(df.to_string(index=False))
    return 0 if df["pass"].all() else 1


if __name__ == "__main__":
    sys.exit(main())
