"""Stage 2 outputs: analysis.md (finding - evidence - limitation - check) and a draft review page."""
from __future__ import annotations

import html

import numpy as np
import pandas as pd

from .decompose import GROUP

pts = lambda x: f"{x * 100:+.2f} pts"
pct = lambda x, d=1: "n/a" if x is None or pd.isna(x) else f"{x * 100:.{d}f}%"
day = lambda t: pd.Timestamp(t).date()


def md_table(df):
    cols = list(df.columns)
    out = ["| " + " | ".join(map(str, cols)) + " |", "|" + "---|" * len(cols)]
    for _, r in df.iterrows():
        out.append("| " + " | ".join("" if (isinstance(v, float) and np.isnan(v)) else str(v).replace("|", "&#124;") for v in r.values) + " |")
    return "\n".join(out)


def top_states(d: pd.DataFrame, k: int = 3) -> pd.DataFrame:
    return d[~d.small_sample].sort_values("total").head(k)


def state_lines(d: pd.DataFrame, k: int = 3) -> str:
    t = top_states(d, k)
    return "; ".join(f"{r[GROUP]} {pts(r.total)} (OTD {pct(r.otd_prior)} → {pct(r.otd_current)}, "
                     f"n {r.eligible_prior}→{r.eligible_current})" for _, r in t.iterrows())


def figure_table(d: pd.DataFrame, k: int = 8) -> pd.DataFrame:
    """Top-k states by |total| (ranked states only) + one row for everything else, so rows still sum to the change."""
    ranked = d[~d.small_sample].reindex(d[~d.small_sample].total.abs().sort_values(ascending=False).index).head(k)
    rest = d.drop(ranked.index)
    rows = ranked[[GROUP, "eligible_prior", "eligible_current", "otd_prior", "otd_current",
                   "performance", "mix", "entry", "exit", "total"]].copy()
    if len(rest):
        rows.loc[len(rows) + 10_000] = {GROUP: f"other {len(rest)} states", "eligible_prior": rest.eligible_prior.sum(),
                                        "eligible_current": rest.eligible_current.sum(), "otd_prior": np.nan,
                                        "otd_current": np.nan, "performance": rest.performance.sum(), "mix": rest.mix.sum(),
                                        "entry": rest.entry.sum(), "exit": rest.exit.sum(), "total": rest.total.sum()}
    return rows.reset_index(drop=True)


def write(r: dict, path, outdir) -> None:
    wk, pairs = r["wk"], r["pairs"]
    sel = r["sel"]
    ld, ls = r["latest"]
    bd, bs = r["big"]
    ok = pairs[pairs.status == "OK"].copy()
    ok["abs_perf"], ok["abs_mix"] = ok.sum_performance.abs(), (ok.sum_mix + ok.sum_entry + ok.sum_exit).abs()
    mix_dominant = int((ok.abs_mix > ok.abs_perf).sum())
    lo, hi = wk.loc[wk.otd_rate.idxmin()], wk.loc[wk.otd_rate.idxmax()]
    dist, lim = r["dist"], r["lim"]
    dm = dist.pivot(index="stage", columns="group", values="median_h")
    dp = dist.pivot(index="stage", columns="group", values="p90_h")
    lim = lim.set_index("group")
    drop = ok.loc[ok.change.idxmin()]
    dd = pd.read_csv(outdir / "decomposition_by_state_all_pairs.csv", parse_dates=["prior_week", "current_week"])
    dd = dd[(dd.prior_week == drop.prior_week) & (dd.current_week == drop.current_week)]
    wk_view = wk[["estimated_week", "eligible_orders", "U", "X", "otd_rate", "outcome_coverage",
                  "cycle_hours_median", "cycle_hours_p90"]].copy()
    wk_view["estimated_week"] = wk_view.estimated_week.dt.date
    for c in ["otd_rate", "outcome_coverage"]:
        wk_view[c] = wk_view[c].map(pct)
    for c in ["cycle_hours_median", "cycle_hours_p90"]:
        wk_view[c] = wk_view[c].round(1)
    ft = figure_table(ld)
    ftv = ft.copy()
    for c in ["otd_prior", "otd_current"]:
        ftv[c] = ftv[c].map(pct)
    for c in ["performance", "mix", "entry", "exit", "total"]:
        ftv[c] = ftv[c].map(lambda v: f"{v * 100:+.2f}")
    stage_tbl = pd.DataFrame({
        "stage": dm.index,
        "median on time (h)": dm["on time (A)"].round(1).values, "median late (h)": dm["late (L)"].round(1).values,
        "P90 on time (h)": dp["on time (A)"].round(1).values, "P90 late (h)": dp["late (L)"].round(1).values})
    stage_tbl = stage_tbl.set_index("stage").loc[["approval", "handling", "transit", "total"]].reset_index()
    n_stage = dist[dist.stage == "total"].set_index("group").n
    c = r["checks"][["check", "expected", "actual", "pass"]]

    L = [
        "# Stage 2 — Weekly Delivery Review, State Decomposition, Stage Timing",
        "",
        "Public Olist data, independent offline analysis. Retrospective: estimated-delivery weeks "
        f"{sel['first_week']} → {sel['last_week']} ({sel['weeks']} weeks, approved window). Every number comes from "
        "`python -m olist_analytics.run_stage2`, which runs only on a READY stage-1 release and writes this file only "
        "after every check in §7 passes. Main KPI: **on-time rate among delivered orders with valid dates**, A/(A+L).",
        "",
        "## 1. Weekly trend",
        f"- Window: {pct(sel['otd_rate'], 2)} on-time over {sel['A'] + sel['L']:,} eligible orders; U {sel['U']:,}, "
        f"X {sel['X']:,}, outcome coverage {pct(sel['outcome_coverage'], 2)}.",
        f"- Lowest week: {day(lo.estimated_week)} at {pct(lo.otd_rate)} (n={int(lo.eligible_orders):,}). "
        f"Highest: {day(hi.estimated_week)} at {pct(hi.otd_rate)} (n={int(hi.eligible_orders):,}).",
        f"- Weekly outcome coverage ranges {pct(wk.outcome_coverage.min())}–{pct(wk.outcome_coverage.max())}; "
        "the main KPI is always read next to it.",
        "- Full weekly table: `outputs/stage2/weekly_kpis.csv` (cycle and stage hours each carry their own n).",
        "",
        "## 2. Figure 04A — latest pair of weeks",
        f"**Question.** Which customer states contributed to the on-time change between estimated weeks "
        f"{day(ls['prior_week'])} and {day(ls['current_week'])}?",
        "",
        f"- **Finding.** On-time fell {pct(ls['P0'], 2)} → {pct(ls['P1'], 2)} ({pts(ls['change'])}). Largest ranked "
        f"contributors: {state_lines(ld)}.",
        f"- **Evidence.** Performance terms sum to {pts(ls['sum_performance'])}; mix {pts(ls['sum_mix'])}; entry "
        f"{pts(ls['sum_entry'])}; exit {pts(ls['sum_exit'])}. Eligible orders {ls['eligible_prior']:,} → "
        f"{ls['eligible_current']:,}. All terms add up to the change exactly (identity checked).",
        "- **Limitation.** Descriptive decomposition only: a state's performance term can still hide seller, "
        "category or route changes inside that state. States with fewer than 30 eligible orders in either week "
        "stay in the totals but are not ranked. The current week is the last one admitted by the 31-day horizon; "
        "with a 45- or 60-day horizon it would be excluded, so its on-time rate may still be biased upward by censoring.",
        f"- **Recommended check.** Look at {top_states(ld, 1).iloc[0][GROUP]} orders that were late in the week of "
        f"{day(ls['current_week'])}: which sellers and stages they share (stage-timing view below).",
        "",
        md_table(ftv),
        "",
        "Rates in %; terms in percentage points. The last row aggregates every state not shown, so the column "
        "`total` sums to the overall change.",
        "",
        "## 3. Largest weekly decline in the window",
        f"- **Finding.** {day(drop.prior_week)} → {day(drop.current_week)}: {pct(drop.P0, 2)} → {pct(drop.P1, 2)} "
        f"({pts(drop.change)}). Ranked contributors: {state_lines(dd)}.",
        f"- **Evidence.** Performance {pts(drop.sum_performance)}, mix {pts(drop.sum_mix)}, entry + exit "
        f"{pts(drop.sum_entry + drop.sum_exit)}.",
        "- **Limitation.** The decline is broad, not one state; the data cannot say why. Any external cause "
        "(weather, strikes, holidays) would need a separate source and is not claimed here.",
        "- **Recommended check.** Compare that week's late orders by seller state and stage before naming a cause.",
        "",
        "## 4. Performance vs mix across all weekly pairs",
        f"- {len(ok)} consecutive pairs. Mix + entry + exit outweighs performance in {mix_dominant} of them.",
        f"- Median |performance| {ok.abs_perf.median() * 100:.2f} pts vs median |mix + entry + exit| "
        f"{ok.abs_mix.median() * 100:.2f} pts.",
        "- Reading: week-to-week swings in this window mostly come from on-time changes **within** states, not from "
        "orders shifting between states. This is a description of the window, not a forecast.",
        "",
        "## 5. Stage-timing diagnosis (not responsibility)",
        f"Orders in the window that are OTD-eligible and stage-eligible: on time n={int(n_stage['on time (A)']):,}, "
        f"late n={int(n_stage['late (L)']):,}.",
        "",
        md_table(stage_tbl),
        "",
        f"- **Finding.** Late orders are slower in both stages, and the gap is far larger in transit "
        f"(median {dm.loc['transit', 'late (L)']:.0f} h vs {dm.loc['transit', 'on time (A)']:.0f} h) than in seller handling "
        f"(median {dm.loc['handling', 'late (L)']:.0f} h vs {dm.loc['handling', 'on time (A)']:.0f} h).",
        f"- **Evidence.** Handed to the carrier after the seller's `shipping_limit_date`: "
        f"{pct(lim.loc['late (L)', 'share_after_limit'])} of late orders vs "
        f"{pct(lim.loc['on time (A)', 'share_after_limit'])} of on-time orders.",
        "- **Limitation.** Groups are selected using the delivery outcome relative to each order's estimate; "
        "the stage differences are descriptive, not estimates of what causes lateness. Medians of stages do not add up "
        "to the median total. The deadline used is the earliest `shipping_limit_date` among an order's items. "
        "This compares an order-level handoff with an item-level deadline, including multi-seller orders; "
        "it is a deadline proxy and cannot establish individual seller compliance. Transit has no comparable standard in the data. So this shows *where "
        "time is spent*, not *who caused the delay*. No 'share of delay caused by seller / carrier' is reported.",
        "- **Recommended check.** In stage 3, test whether purchase-time signals (distance, seller history, "
        "estimated days) predict the long-transit cases; that is a prediction question, not attribution.",
        "",
        "## 6. Weekly table",
        md_table(wk_view),
        "",
        "## 7. Blocking checks",
        md_table(c),
        "",
        "## 8. Limits that apply to every number above",
        "- Retrospective window inside an inferred observation boundary; late cohorts near the end may be censored "
        "(stage-1 report §9, sensitivity table).",
        "- The KPI covers delivered orders with valid dates only; U and X are reported next to it, never folded in.",
        "- Estimated delivery date is Olist's estimate shown to the customer, not a contractual SLA.",
        "- Olist has no carrier IDs; customer state is the grouping, and sellers are not carriers.",
    ]
    sellers = r["sellers"]
    queue = sellers[sellers.meets_min_n].head(10)[["seller_label", "seller_state", "eligible_orders", "L", "U",
                "otd_rate", "otd_wilson_low", "otd_wilson_high", "stage_n", "handling_median_h", "transit_median_h"]].copy()
    for c in ["otd_rate", "otd_wilson_low", "otd_wilson_high"]:
        queue[c] = queue[c].map(pct)
    for c in ["handling_median_h", "transit_median_h"]:
        queue[c] = queue[c].round(1)
    L += ["", "## 9. Seller-associated orders to inspect", "",
          "Single-seller orders only, across the entire 74-week window. Minimum 30 OTD-eligible orders; "
          "all sellers remain in the exported queue with a threshold flag. These are investigation candidates, not causal responsibility rankings. "
          "95% Wilson intervals capture binomial sampling uncertainty only; routes, categories, promises, clustering and censoring are not adjusted.",
          "", md_table(queue), "", "Full identifiers and counts: `outputs/stage2/seller_review_queue.csv`. "
          "The page uses stable aliases; no review of these candidates has yet been recorded."]
    path.write_text("\n".join(L) + "\n", encoding="utf-8")


# ------------------------------------------------------------------ shared page styles (used by dashboard.py / site.py)
CSS = """
:root{--page:#f9f9f7;--surface:#fcfcfb;--ink:#0b0b0b;--ink2:#52514e;--muted:#898781;--grid:#e1e0d9;--axis:#c3c2b7;
--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--s4:#eda100;--ring:rgba(11,11,11,.10);--banner:#fff4d6}
@media (prefers-color-scheme:dark){:root:not([data-theme="light"]){--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;
--grid:#2c2c2a;--axis:#383835;--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--ring:rgba(255,255,255,.10);--banner:#2e2610}}
:root[data-theme="dark"]{--page:#0d0d0d;--surface:#1a1a19;--ink:#f0efec;--ink2:#c3c2b7;--grid:#2c2c2a;--axis:#383835;
--s1:#3987e5;--s2:#d95926;--s3:#199e70;--s4:#c98500;--ring:rgba(255,255,255,.10);--banner:#2e2610}
*{box-sizing:border-box}body{margin:0;background:var(--page);color:var(--ink);font:14px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}
main{max-width:1080px;margin:0 auto;padding:20px 16px 48px}h1{font-size:22px;margin:0 0 4px}h2{font-size:15px;margin:0 0 4px}
.sub{color:var(--ink2);margin:0 0 14px}.banner{background:var(--banner);border:1px solid var(--ring);border-radius:8px;padding:8px 12px;margin-bottom:16px;font-size:13px}
.card{background:var(--surface);border:1px solid var(--ring);border-radius:10px;padding:14px;margin-bottom:16px}
.cap{color:var(--muted);font-size:12px;margin-top:8px}svg{width:100%;height:auto;display:block}
.legend{display:flex;flex-wrap:wrap;gap:14px;font-size:12px;color:var(--ink2);margin:6px 0}.sw{display:inline-block;width:10px;height:10px;border-radius:2px;margin-right:4px;vertical-align:-1px}
.grid{stroke:var(--grid)}.axis{stroke:var(--axis)}.tick{fill:var(--muted);font-size:12px;font-variant-numeric:tabular-nums}
.lab{fill:var(--ink);font-size:13px}.val{fill:var(--ink2);font-size:12px;font-variant-numeric:tabular-nums}
.line{fill:none;stroke:var(--s1);stroke-width:2}.dot{fill:var(--s1);stroke:var(--surface);stroke-width:2}
.hit{fill:transparent}.hit:hover{fill:var(--ink);fill-opacity:.04}
#tip{position:fixed;pointer-events:none;background:var(--ink);color:var(--surface);font-size:12px;padding:6px 8px;border-radius:6px;max-width:340px;display:none;z-index:9}
"""
def svg_trend(wk: pd.DataFrame) -> str:
    W, H, L, R, T, B = 1000, 280, 44, 24, 14, 30
    v = wk.otd_rate.values
    lo, hi = np.floor(v.min() * 20) / 20, 1.0
    n = len(wk)
    xs = [L + i * (W - L - R) / (n - 1) for i in range(n)]
    yv = lambda x: T + (hi - x) / (hi - lo) * (H - T - B)
    g = []
    t = lo
    while t <= hi + 1e-9:
        g.append(f'<line x1="{L}" x2="{W - R}" y1="{yv(t):.1f}" y2="{yv(t):.1f}" class="grid"/>'
                 f'<text x="{L - 6}" y="{yv(t) + 4:.1f}" class="tick" text-anchor="end">{t * 100:.0f}%</text>')
        t += 0.05
    g.append(f'<polyline class="line" points="{" ".join(f"{x:.1f},{yv(y):.1f}" for x, y in zip(xs, v))}"/>')
    for i, r in enumerate(wk.itertuples()):
        if i % 8 == 0 and i < n - 4 or i == n - 1:
            g.append(f'<text x="{xs[i]:.1f}" y="{H - 10}" class="tick" text-anchor="middle">{r.estimated_week:%b %y}</text>')
        tip = (f"Week of {r.estimated_week.date()}: {r.otd_rate * 100:.1f}% on time ({r.A:,}/{r.eligible_orders:,}) · "
               f"U {r.U} · coverage {r.outcome_coverage * 100:.1f}% · median cycle {r.cycle_hours_median:.0f} h")
        g.append(f'<rect x="{xs[i] - 4:.1f}" y="{T}" width="8" height="{H - T - B}" class="hit" data-tip="{html.escape(tip)}"/>')
    g.append(f'<circle cx="{xs[-1]:.1f}" cy="{yv(v[-1]):.1f}" r="4" class="dot"/>')
    return f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Weekly on-time rate">{"".join(g)}</svg>'
