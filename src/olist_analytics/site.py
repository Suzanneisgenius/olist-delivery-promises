"""Shared shell and small SVG charts for the stage-4 pages (no external libraries, no network)."""
from __future__ import annotations

import html
import json

import numpy as np
import pandas as pd

from .report2 import CSS as BASE_CSS

PAGES = [("weekly_review.html", "Weekly Review"), ("data_quality.html", "Data Quality"),
         ("model_report.html", "Model Report")]
BANNER = ("Public Olist e-commerce data (2016–2018), independent offline analysis. Not affiliated with Olist. "
          "No carrier identifiers; estimated delivery dates are customer estimates, not SLAs.")

CSS = BASE_CSS + """
nav.site{display:flex;gap:18px;flex-wrap:wrap;margin:0 0 14px;font-size:13px;border-bottom:1px solid var(--grid)}
nav.site a{color:var(--ink2);text-decoration:none;padding:6px 0;border-bottom:2px solid transparent}
nav.site a[aria-current=page]{color:var(--ink);border-bottom-color:var(--s1);font-weight:600}
.summary{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:14px 0}
.metric{padding:12px;border:1px solid var(--ring);border-radius:8px;background:var(--surface)}
.metric strong{display:block;font-size:24px;font-variant-numeric:tabular-nums}.metric small{color:var(--ink2)}
table{border-collapse:collapse;width:100%;font-size:12px;font-variant-numeric:tabular-nums}
th,td{padding:7px 8px;text-align:right;border-bottom:1px solid var(--grid);white-space:nowrap}
th:first-child,td:first-child{text-align:left}th{color:var(--ink2);font-weight:600}td.l,th.l{text-align:left;white-space:normal}
.scroll{overflow:auto}a{color:var(--s1)}details{margin-top:10px}summary{cursor:pointer;color:var(--ink2)}
.notice{margin:10px 0;padding:9px 12px;background:var(--banner);border-radius:6px;font-size:12px}
.two{display:grid;grid-template-columns:1fr 1fr;gap:16px}.two>div,.summary>div{min-width:0}.muted{color:var(--ink2)}
.ok{color:var(--s3);font-weight:600}.bad{color:#d03b3b;font-weight:600}
.downloads{display:flex;gap:14px;flex-wrap:wrap;margin-top:8px}
.ref{stroke:var(--muted);stroke-dasharray:4 4;fill:none}.l1{stroke:var(--s1);stroke-width:2;fill:none}.l2{stroke:var(--s2);stroke-width:2;fill:none}
.d1{fill:var(--s1)}.d2{fill:var(--s2)}.bar1{fill:var(--s1)}
#tip{position:fixed;pointer-events:none;background:var(--ink);color:var(--surface);font-size:12px;padding:6px 8px;border-radius:6px;max-width:min(340px,calc(100vw - 20px));display:none;z-index:9}
@media(max-width:760px){.summary{grid-template-columns:repeat(2,1fr)}.two{grid-template-columns:1fr}main{padding:16px 12px}}
@media print{nav.site,#tip{display:none}.card{break-inside:avoid}.scroll{overflow:visible}}
"""

TIP_JS = """<div id="tip" role="tooltip"></div><script>
const tip=document.getElementById('tip');document.querySelectorAll('[data-tip]').forEach(e=>{e.setAttribute('tabindex','0');
function show(v){tip.textContent=e.dataset.tip;tip.style.display='block';const b=e.getBoundingClientRect(),x=v.clientX??b.left+20,y=v.clientY??b.top+20;
tip.style.left=Math.max(8,Math.min(x+12,innerWidth-tip.offsetWidth-8))+'px';tip.style.top=Math.max(8,Math.min(y+12,innerHeight-tip.offsetHeight-8))+'px'}
e.onmousemove=show;e.onfocus=show;e.onmouseleave=()=>tip.style.display='none';e.onblur=()=>tip.style.display='none'});</script>"""

esc = lambda x: html.escape("" if x is None or (isinstance(x, float) and np.isnan(x)) else str(x))


def nav(current: str) -> str:
    links = "".join(f'<a href="{href}"{" aria-current=page" if href == current else ""}>{name}</a>'
                    for href, name in PAGES)
    return f'<nav class="site" aria-label="Report pages">{links}</nav><div class="banner">{BANNER}</div>'


def page(title: str, current: str, body: str, data: dict) -> str:
    """`data` = exactly the values the page shows; embedded so tests and UAT can compare it with the exports."""
    payload = json.dumps(data, allow_nan=False, default=str).replace("<", "\\u003c")
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8">'
            f'<meta name="viewport" content="width=device-width,initial-scale=1"><title>{esc(title)}</title>'
            f'<style>{CSS}</style></head><body><main>{nav(current)}{body}</main>'
            f'<script id="page-data" type="application/json">{payload}</script>{TIP_JS}</body></html>')


def table(df: pd.DataFrame, left=(), check=None) -> str:
    head = "".join(f'<th scope="col" class="{"l" if c in left else ""}">{esc(c)}</th>' for c in df.columns)
    rows = []
    for _, r in df.iterrows():
        cells = []
        for c, v in r.items():
            cls = "l" if c in left else ""
            txt = esc(v)
            if c == check:
                cls += " ok" if str(v) in ("True", "PASS", "Pass") else " bad"
                txt = "Pass" if str(v) in ("True", "PASS", "Pass") else esc(v)
            cells.append(f'<td class="{cls.strip()}">{txt}</td>')
        rows.append("<tr>" + "".join(cells) + "</tr>")
    return f'<div class="scroll"><table><thead><tr>{head}</tr></thead><tbody>{"".join(rows)}</tbody></table></div>'


def metric(label: str, value: str, note: str, key: str) -> str:
    return f'<div class="metric" data-check="{esc(key)}"><small>{esc(label)}</small><strong>{esc(value)}</strong><small>{esc(note)}</small></div>'


# ------------------------------------------------------------------ charts
def nice_ticks(top: float, max_ticks: int = 6) -> tuple[float, list[float]]:
    """Round axis maximum and evenly spaced 'nice' ticks from 0."""
    for step in (0.01, 0.02, 0.025, 0.05, 0.1, 0.2, 0.25):
        n = int(np.ceil(top / step - 1e-9))
        if n + 1 <= max_ticks:
            return n * step, [i * step for i in range(n + 1)]
    return top, list(np.linspace(0, top, max_ticks))


def _axes(W, H, L, R, T, B, xlo, xhi, ylo, yhi, xticks, yticks, xfmt, yfmt, xlab, ylab):
    X = lambda v: L + (v - xlo) / (xhi - xlo) * (W - L - R)
    Y = lambda v: T + (yhi - v) / (yhi - ylo) * (H - T - B)
    g = []
    for t in yticks:
        g.append(f'<line x1="{L}" x2="{W - R}" y1="{Y(t):.1f}" y2="{Y(t):.1f}" class="grid"/>'
                 f'<text x="{L - 6}" y="{Y(t) + 4:.1f}" class="tick" text-anchor="end">{yfmt(t)}</text>')
    for t in xticks:
        g.append(f'<text x="{X(t):.1f}" y="{H - B + 16}" class="tick" text-anchor="middle">{xfmt(t)}</text>')
    g.append(f'<text x="{(L + W - R) / 2:.1f}" y="{H - 4}" class="tick" text-anchor="middle">{esc(xlab)}</text>')
    g.append(f'<text x="12" y="{T + (H - T - B) / 2:.1f}" class="tick" text-anchor="middle" '
             f'transform="rotate(-90 12 {T + (H - T - B) / 2:.1f})">{esc(ylab)}</text>')
    return X, Y, g


def pr_curve(curves: dict[str, tuple[np.ndarray, np.ndarray]], prevalence: float) -> str:
    """Precision–recall curves; dashed line = prevalence (what a random ranking achieves)."""
    W, H, L, R, T, B = 1000, 360, 60, 20, 12, 44
    ymax, yt = nice_ticks(min(1.0, max(float(np.max(p[r >= 0.02])) for r, p in curves.values()) * 1.05))
    X, Y, g = _axes(W, H, L, R, T, B, 0, 1, 0, ymax, [0, .2, .4, .6, .8, 1], yt,
                    lambda v: f"{v:.0%}", lambda v: f"{v:.0%}", "Recall (share of late orders caught)", "Precision")
    g.append(f'<line x1="{X(0)}" x2="{X(1)}" y1="{Y(prevalence):.1f}" y2="{Y(prevalence):.1f}" class="ref"/>')
    g.append(f'<text x="{X(0.01)}" y="{Y(prevalence) + 16:.1f}" class="tick">random ranking = late rate {prevalence:.1%}</text>')
    for i, (name, (rec, prec)) in enumerate(curves.items()):
        keep = rec >= 0.02
        pts = " ".join(f"{X(r):.1f},{Y(min(p, ymax)):.1f}" for r, p in zip(rec[keep], prec[keep]))
        g.append(f'<polyline class="l{i + 1}" points="{pts}"><title>{esc(name)}</title></polyline>')
    return f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Precision-recall curves">{"".join(g)}</svg>'


def calibration_chart(cal: pd.DataFrame) -> str:
    """Mean predicted vs observed late rate per decile; dashed diagonal = perfect calibration."""
    W, H, L, R, T, B = 520, 360, 56, 16, 12, 44
    top, t = nice_ticks(float(max(cal.mean_predicted.max(), cal.observed_rate.max())) * 1.05)
    X, Y, g = _axes(W, H, L, R, T, B, 0, top, 0, top, t, t,
                    lambda v: f"{v:.0%}", lambda v: f"{v:.0%}", "Mean predicted risk (decile)", "Observed late rate")
    g.append(f'<line x1="{X(0)}" y1="{Y(0)}" x2="{X(top)}" y2="{Y(top)}" class="ref"/>')
    for i, (m, d) in enumerate(cal.groupby("model", sort=False)):
        pts = " ".join(f"{X(a):.1f},{Y(b):.1f}" for a, b in zip(d.mean_predicted, d.observed_rate))
        g.append(f'<polyline class="l{i + 1}" points="{pts}"/>')
        for r in d.itertuples():
            tip = f"{m} · decile {int(r.bin) + 1}: predicted {r.mean_predicted:.2%}, observed {r.observed_rate:.2%}, n {int(r.n):,}"
            g.append(f'<circle cx="{X(r.mean_predicted):.1f}" cy="{Y(r.observed_rate):.1f}" r="4" class="d{i + 1}" data-tip="{esc(tip)}"/>')
    return f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="Calibration by decile">{"".join(g)}</svg>'


def hbars(labels, values, fmt, unit_label: str) -> str:
    W, rh, L, R = 520, 24, 200, 60
    H = rh * len(values) + 30
    hi = max(max(values), 1e-9)
    out = [f'<line x1="{L}" x2="{L}" y1="0" y2="{H - 24}" class="axis"/>']
    for i, (lab, v) in enumerate(zip(labels, values)):
        y = i * rh + 2
        w = max(v, 0) / hi * (W - L - R)
        out.append(f'<text x="{L - 8}" y="{y + 15}" class="lab" text-anchor="end">{esc(lab)}</text>'
                   f'<rect x="{L}" y="{y + 3}" width="{max(w, 1):.1f}" height="16" rx="3" class="bar1"/>'
                   f'<text x="{L + w + 6:.1f}" y="{y + 15}" class="val">{fmt(v)}</text>')
    out.append(f'<text x="{L}" y="{H - 6}" class="tick">{esc(unit_label)}</text>')
    return f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{esc(unit_label)}">{"".join(out)}</svg>'


def line_chart(dates, values, threshold, fmt, ylab, tips) -> str:
    W, H, L, R, T, B = 1000, 240, 76, 20, 12, 40
    lo = np.floor((min(min(values), threshold) - 0.002) * 100) / 100
    hi = 1.0
    n = len(values)
    X = lambda i: L + i * (W - L - R) / max(n - 1, 1)
    Y = lambda v: T + (hi - v) / (hi - lo) * (H - T - B)
    g = []
    step = 0.01 if hi - lo <= 0.06 else 0.02
    t = lo
    while t <= hi + 1e-9:
        g.append(f'<line x1="{L}" x2="{W - R}" y1="{Y(t):.1f}" y2="{Y(t):.1f}" class="grid"/>'
                 f'<text x="{L - 6}" y="{Y(t) + 4:.1f}" class="tick" text-anchor="end">{t:.0%}</text>')
        t += step
    g.append(f'<line x1="{L}" x2="{W - R}" y1="{Y(threshold):.1f}" y2="{Y(threshold):.1f}" class="ref"/>'
             f'<text x="{W - R}" y="{Y(threshold) - 5:.1f}" class="tick" text-anchor="end">guard {fmt(threshold)}</text>')
    g.append(f'<polyline class="l1" points="{" ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(values))}"/>')
    for i, (d, tip) in enumerate(zip(dates, tips)):
        if i % 8 == 0 and i < n - 4 or i == n - 1:
            g.append(f'<text x="{X(i):.1f}" y="{H - B + 16}" class="tick" text-anchor="middle">{pd.Timestamp(d):%b %y}</text>')
        g.append(f'<rect x="{X(i) - 5:.1f}" y="{T}" width="10" height="{H - T - B}" class="hit" data-tip="{esc(tip)}"/>')
    g.append(f'<text x="14" y="{T + (H - T - B) / 2:.1f}" class="tick" text-anchor="middle" transform="rotate(-90 14 {T + (H - T - B) / 2:.1f})">{esc(ylab)}</text>')
    return f'<svg viewBox="0 0 {W} {H}" role="img" aria-label="{esc(ylab)}">{"".join(g)}</svg>'
