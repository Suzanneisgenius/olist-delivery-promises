"""Extend the supplied review layout using the same reviewed Stage 2 rows."""
import json
import posixpath
import re
from pathlib import Path

import pandas as pd

from .report2 import CSS, svg_trend


def records(df):
    return json.loads(df.to_json(orient="records", date_format="iso"))


def write_dashboard(r, path: Path):
    data = {"window": r["sel"], "weekly": records(r["wk"]), "pairs": records(r["pairs"]),
            "states": records(r["detail"]), "stages": records(r["dist"]), "limits": records(r["lim"]),
            "sellers": records(r["sellers"].drop(columns="single_seller_id")), "checks": records(r["checks"])}
    (path.parent / "review_data.json").write_text(json.dumps(data, indent=2, allow_nan=False))
    path.write_text(render_dashboard(data, r["wk"]))


def weekly_frame(data: dict) -> pd.DataFrame:
    """Rebuild the weekly table from review_data.json (used by stage 4)."""
    wk = pd.DataFrame(data["weekly"])
    wk["estimated_week"] = pd.to_datetime(wk.estimated_week).dt.tz_localize(None)
    return wk


def rebase_links(page: str, base: str) -> str:
    """Prefix relative href targets with `base` (e.g. 'stage2/') so the page works from another folder."""
    if not base:
        return page
    def fix(m):
        target = m.group(2)
        if re.match(r"^(https?:|mailto:|#|data:)", target):
            return m.group(0)
        return m.group(1) + posixpath.normpath(base + target) + '"'
    return re.sub(r'(href=")([^"]+)"', fix, page)


def render_dashboard(data: dict, wk: pd.DataFrame, nav: str = "", base: str = "") -> str:
    payload = json.dumps(data, allow_nan=False).replace("<", "\\u003c")
    trend = svg_trend(wk)
    template = r'''<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>Weekly Delivery Review</title>
<style>__CSS__
.summary{display:grid;grid-template-columns:repeat(4,1fr);gap:12px;margin:14px 0}.metric{padding:12px;border:1px solid var(--ring);border-radius:8px;background:var(--surface)}
.metric strong{display:block;font-size:24px;font-variant-numeric:tabular-nums}.metric small{color:var(--ink2)}
.controls{display:flex;gap:10px;flex-wrap:wrap;align-items:center;margin:12px 0}select,button{font:inherit;background:var(--surface);color:var(--ink);border:1px solid var(--axis);border-radius:6px;padding:7px 10px}
button{cursor:pointer}button:hover{border-color:var(--ink)}:focus-visible{outline:2px solid var(--s1);outline-offset:3px}
table{border-collapse:collapse;width:100%;font-size:12px;font-variant-numeric:tabular-nums}th,td{padding:8px;text-align:right;border-bottom:1px solid var(--grid);white-space:nowrap}th:first-child,td:first-child{text-align:left}th{color:var(--ink2);font-weight:600}
.scroll{overflow:auto}a{color:var(--s1)}details{margin-top:12px}summary{cursor:pointer;color:var(--ink2)}.scroll-chart{overflow:auto}.scroll-chart svg{min-width:660px}
.term{display:flex;flex-wrap:wrap;gap:14px;margin:12px 0}.term strong{font-variant-numeric:tabular-nums}.notice{margin:10px 0;padding:9px 12px;background:var(--banner);border-radius:6px;font-size:12px}
.stage-row{display:grid;grid-template-columns:90px 1fr;gap:8px;margin:14px 0}.stage-row .bars{display:grid;gap:5px}.stage-bar{height:22px;color:var(--ink);font-size:12px;display:flex;align-items:center;position:relative;background:var(--grid)}.stage-bar i{height:100%;display:block}.stage-bar span{position:absolute;left:8px;white-space:nowrap;text-shadow:0 1px 2px var(--surface)}
.downloads{display:flex;gap:14px;flex-wrap:wrap}.muted{color:var(--ink2)}#tip{max-width:min(340px,calc(100vw - 20px))}
@media(max-width:620px){.summary{grid-template-columns:repeat(2,1fr)}main{padding:16px 12px}h1{font-size:20px}.metric strong{font-size:21px}.controls select{max-width:100%}.card{padding:12px}}
@media print{button,select,#tip{display:none}.card{break-inside:avoid}.scroll{overflow:visible}}
</style></head><body><main>__NAV__
<h1>Weekly Delivery Review</h1><p class="sub">Public Olist orders · estimated-delivery weeks 27 Feb 2017 – 23 Jul 2018</p>
<div class="summary" id="window-metrics" aria-label="Whole-window metrics"></div>
<section class="card"><h2>Figure 04A — Which customer states contributed to the weekly change?</h2>
<div class="controls"><label for="week">Current estimated week</label><select id="week"></select><button id="latest">Latest pair</button><button id="decline">Largest decline</button></div>
<div id="pair-summary" aria-live="polite"></div><div class="term" id="terms"></div>
<div class="legend"><span><i class="sw" style="background:var(--s1)"></i>Performance</span><span><i class="sw" style="background:var(--s2)"></i>Mix</span><span><i class="sw" style="background:var(--s3)"></i>Entry</span><span><i class="sw" style="background:var(--s4)"></i>Exit</span></div>
<div id="contribution-chart" class="scroll-chart"></div><div id="pair-caveat" class="notice"></div>
<p class="cap">Performance measures changes in state rates, weighted by average order shares. Mix measures shifts in shares relative to the common overall centre. These are arithmetic contributions; seller, category and route composition can change inside a state.</p>
<details><summary>All states, counts and contribution terms</summary><div class="scroll" id="state-table"></div><button id="download-pair">Download this pair (CSV)</button></details></section>
<section class="card"><h2>On-time rate by estimated week</h2><div class="scroll-chart">__TREND__</div>
<p class="cap">Vertical scale: 70–100%. Hover or focus a week for its eligible orders, U count and coverage. The selected comparison affects Figure 04A only; this trend and the sections below retain the full 74-week window.</p>
<details><summary>Weekly counts, coverage and cycle hours</summary><div class="scroll" id="weekly-table"></div></details></section>
<section class="card"><h2>Where do late orders spend more time?</h2><p class="muted" id="stage-n"></p>
<div class="legend"><span><i class="sw" style="background:var(--s1)"></i>On time</span><span><i class="sw" style="background:var(--s2)"></i>Late</span></div>
<div id="stage-chart"></div><div class="scroll" id="stage-table"></div>
<p class="cap">Median hours share one zero-based scale. Stages have no comparable transit target in this dataset; distributions describe elapsed time, not responsibility. Grouping by the delivery outcome cannot establish a cause. Stage medians do not sum to the median total.</p>
<details><summary>Earliest item deadline check</summary><div id="limit-summary"></div><p class="cap">Order-level carrier handoff is compared with the earliest recorded item shipping deadline. Multi-item and multi-seller orders make this a proxy, not a seller compliance measure.</p></details></section>
<section class="card"><h2>Seller-associated orders to inspect</h2><p class="muted">Single-seller orders across the full window; lowest observed on-time rates first.</p>
<div class="controls"><label for="seller-n">Minimum eligible orders</label><select id="seller-n"><option value="30">30</option><option value="100">100</option><option value="300">300</option></select><span id="seller-count"></span></div>
<div class="scroll" id="seller-table"></div><p class="cap">Showing the first 10 qualifying sellers. Rates reflect seller-associated orders, including customer locations and delivery estimates. 95% Wilson intervals show binomial sampling uncertainty only; clustering, route mix and censoring are not adjusted.</p></section>
<section class="card"><h2>Evidence and definitions</h2><p>The main KPI is <b>on-time rate among delivered orders with valid dates</b>: A/(A+L). U is unconfirmed, X is canceled or unavailable; neither enters that denominator. Coverage = (A+L)/(A+L+U). Estimated delivery dates are customer estimates.</p>
<p class="notice">The last cohorts may be right-censored. The 31-day default horizon admits 74 weeks; 45 and 60 days admit 72 and 70. These are different windows, not confidence intervals. Olist provides no carrier identifiers.</p>
<details><summary>Calculation checks and source files</summary><div class="scroll" id="checks-table"></div><p>Calculations use one row per order and independent DuckDB queries from the raw files. Source hashes and the current mart fingerprint are in the lineage receipt.</p>
<div class="downloads"><a href="lineage.json">Lineage</a><a href="sql_state_week_crosscheck.csv">SQL state check</a><a href="sql_stage_timing_crosscheck.csv">SQL stage check</a><a href="../qa/source_manifest.csv">Raw file hashes</a><a href="../stage2_analysis.md">Analysis</a></div></details>
<div class="downloads"><a href="weekly_kpis.csv" download>Weekly KPIs</a><a href="decomposition_by_state_all_pairs.csv" download>All contributions</a><a href="stage_timing_by_outcome.csv" download>Stage distributions</a><a href="seller_review_queue.csv" download>Seller queue</a><a href="review_data.json" download>Reviewed page data</a></div></section>
</main><div id="tip" role="tooltip"></div><script id="review-data" type="application/json">__DATA__</script><script>
const D=JSON.parse(document.getElementById('review-data').textContent), $=id=>document.getElementById(id);
const date=x=>x.slice(0,10), num=x=>Number(x).toLocaleString('en-US'), pct=x=>x==null?'n/a':(x*100).toFixed(2)+'%', hours=x=>x==null?'n/a':x.toFixed(1), esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const pp=x=>Math.abs(x*100)<.005?'0.00':(x>0?'+':'')+(x*100).toFixed(2), labels={performance:'Performance',mix:'Mix',entry:'Entry',exit:'Exit'};
function table(headers,rows){return '<table><thead><tr>'+headers.map(h=>'<th scope="col">'+esc(h)+'</th>').join('')+'</tr></thead><tbody>'+rows.map(r=>'<tr>'+r.map(v=>'<td>'+esc(v)+'</td>').join('')+'</tr>').join('')+'</tbody></table>'}
const sel=D.window; $('window-metrics').innerHTML=[['Whole-window on-time',pct(sel.otd_rate),'A / (A + L)'],['Eligible orders',num(sel.A+sel.L),'74 estimated-delivery weeks'],['Outcome coverage',pct(sel.outcome_coverage),'Unconfirmed U: '+num(sel.U)],['Excluded outcomes',num(sel.X),'Canceled or unavailable X']].map(x=>'<div class="metric"><small>'+x[0]+'</small><strong>'+x[1]+'</strong><small>'+x[2]+'</small></div>').join('');
const pairs=D.pairs.filter(p=>p.status==='OK'), latest=pairs.at(-1), worst=pairs.reduce((a,b)=>a.change<b.change?a:b);
$('week').innerHTML=pairs.map(p=>'<option value="'+date(p.current_week)+'">'+date(p.current_week)+'</option>').join('');
let currentRows=[];
function renderPair(){const p=pairs.find(x=>date(x.current_week)===$('week').value); currentRows=D.states.filter(x=>date(x.current_week)===date(p.current_week));
$('pair-summary').textContent=date(p.prior_week)+' → '+date(p.current_week)+': '+pct(p.P0)+' → '+pct(p.P1)+' ('+pp(p.change)+' percentage points) · Eligible orders '+num(p.eligible_prior)+' → '+num(p.eligible_current);
$('terms').innerHTML=Object.keys(labels).map(k=>'<span>'+labels[k]+' <strong>'+pp(p['sum_'+k])+' pp</strong></span>').join('');
const ranked=currentRows.filter(x=>!x.small_sample).sort((a,b)=>Math.abs(b.total)-Math.abs(a.total)), shown=ranked.slice(0,8), rest=currentRows.filter(x=>!shown.includes(x));
let rows=[...shown];if(rest.length){const other={customer_state_reported:'Other '+rest.length+' states',eligible_prior:0,eligible_current:0,otd_prior:null,otd_current:null,performance:0,mix:0,entry:0,exit:0,total:0};for(const x of rest)for(const k of ['eligible_prior','eligible_current','performance','mix','entry','exit','total'])other[k]+=x[k];rows.push(other)}
const terms=Object.keys(labels), colors=['var(--s1)','var(--s2)','var(--s3)','var(--s4)']; let bars=[];
for(const r of rows){const ks=terms.filter(k=>Math.abs(r[k])>1e-12);for(let i=0;i<ks.length;i++)bars.push({r,k:ks[i],label:i===0?r.customer_state_reported:''})}
if(!bars.length){$('contribution-chart').textContent='No contribution terms in this pair.'}else{
const vals=bars.map(b=>b.r[b.k]*100), lo=Math.min(0,...vals), hi=Math.max(0,...vals), span=Math.max(hi-lo,.01), left=220,right=910, x=v=>left+(v-lo)/span*(right-left), zero=x(0), height=bars.length*27+42;
let svg='<svg viewBox="0 0 1000 '+height+'" role="img" aria-label="State contributions in percentage points"><line class="axis" x1="'+zero+'" x2="'+zero+'" y1="0" y2="'+(height-35)+'"/>';
bars.forEach((b,i)=>{let v=b.r[b.k]*100, y=i*27, xv=x(v), tip=b.r.customer_state_reported+' · '+labels[b.k]+': '+pp(b.r[b.k])+' pp · Total '+pp(b.r.total)+' pp · n '+b.r.eligible_prior+' → '+b.r.eligible_current;svg+='<text x="8" y="'+(y+17)+'" class="lab">'+esc(b.label)+'</text><rect x="'+Math.min(zero,xv)+'" y="'+(y+4)+'" width="'+Math.abs(xv-zero)+'" height="17" rx="2" fill="'+colors[terms.indexOf(b.k)]+'"/><text x="'+(xv+(v>=0?7:-7))+'" y="'+(y+17)+'" text-anchor="'+(v>=0?'start':'end')+'" class="val">'+pp(b.r[b.k])+'</text><rect class="hit" tabindex="0" role="img" aria-label="'+esc(tip)+'" data-tip="'+esc(tip)+'" x="0" y="'+y+'" width="1000" height="27"><title>'+esc(tip)+'</title></rect>'});
for(const v of [lo,0,hi].filter((v,i,a)=>a.indexOf(v)===i))svg+='<text x="'+x(v)+'" y="'+(height-8)+'" class="tick" text-anchor="middle">'+v.toFixed(2)+' pp</text>';
$('contribution-chart').innerHTML=svg+'</svg>'}
$('pair-caveat').textContent='Top states require ≥30 eligible orders in both weeks; all smaller, entering and exiting states remain in the totals and the full table.'+(date(p.current_week)>'2018-06-25'?' This pair includes weeks excluded by the 60-day maturity sensitivity; interpret its on-time rate cautiously.':'');
$('state-table').innerHTML=table(['State','Prior n','Current n','Prior OTD','Current OTD','Performance pp','Mix pp','Entry pp','Exit pp','Total pp','Sample flag'],currentRows.map(x=>[x.customer_state_reported,num(x.eligible_prior),num(x.eligible_current),pct(x.otd_prior),pct(x.otd_current),...terms.map(k=>pp(x[k])),pp(x.total),x.small_sample?'Below 30 / entry / exit':'≥30 both weeks'])); bindTips();}
$('week').addEventListener('change',renderPair);$('latest').onclick=()=>{$('week').value=date(latest.current_week);renderPair()};$('decline').onclick=()=>{$('week').value=date(worst.current_week);renderPair()};
$('download-pair').onclick=()=>{const cols=['customer_state_reported','eligible_prior','eligible_current','otd_prior','otd_current','performance','mix','entry','exit','total','small_sample'], csv=[cols.join(','),...currentRows.map(r=>cols.map(k=>r[k]??'').join(','))].join('\n');const a=document.createElement('a'),url=URL.createObjectURL(new Blob([csv],{type:'text/csv'}));a.href=url;a.download='state-contributions-'+$('week').value+'.csv';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000)};
$('weekly-table').innerHTML=table(['Estimated week','A','L','U','X','OTD','Coverage','Cycle median h','Cycle P90 h','Stage n'],D.weekly.map(x=>[date(x.estimated_week),num(x.A),num(x.L),num(x.U),num(x.X),pct(x.otd_rate),pct(x.outcome_coverage),hours(x.cycle_hours_median),hours(x.cycle_hours_p90),num(x.stage_eligible_n)]));
const stages=['approval','handling','transit','total'], g=['on time (A)','late (L)'], stage=(s,n)=>D.stages.find(x=>x.stage===s&&x.group===n); $('stage-n').textContent='Whole-window orders with valid stage timestamps: on time '+num(stage('total',g[0]).n)+'; late '+num(stage('total',g[1]).n)+'.';
const max=Math.max(...D.stages.map(x=>x.median_h));$('stage-chart').innerHTML=stages.map(s=>'<div class="stage-row"><span>'+s[0].toUpperCase()+s.slice(1)+'</span><div class="bars">'+g.map((n,i)=>'<div class="stage-bar"><i style="width:'+(stage(s,n).median_h/max*100)+'%;background:var(--s'+(i+1)+')"></i><span>'+hours(stage(s,n).median_h)+' h</span></div>').join('')+'</div></div>').join('');
$('stage-table').innerHTML=table(['Stage','On-time median h','Late median h','On-time P90 h','Late P90 h'],stages.map(s=>[s,hours(stage(s,g[0]).median_h),hours(stage(s,g[1]).median_h),hours(stage(s,g[0]).p90_h),hours(stage(s,g[1]).p90_h)]));
$('limit-summary').innerHTML=table(['Outcome','Deadline-valid orders','Handoff after earliest deadline','Share'],D.limits.map(x=>[x.group,num(x.orders),num(x.handoff_after_limit),pct(x.share_after_limit)]));
function sellers(){const a=D.sellers.filter(x=>x.eligible_orders>=Number($('seller-n').value));$('seller-count').textContent=num(a.length)+' qualifying sellers';$('seller-table').innerHTML=a.length?table(['Seller','State','Eligible n','Late','U','OTD','95% Wilson interval','Stage n','Handling median h','Transit median h'],a.slice(0,10).map(x=>[x.seller_label,x.seller_state,num(x.eligible_orders),num(x.L),num(x.U),pct(x.otd_rate),pct(x.otd_wilson_low)+' – '+pct(x.otd_wilson_high),num(x.stage_n),hours(x.handling_median_h),hours(x.transit_median_h)])):'No sellers meet this sample threshold.'} $('seller-n').onchange=sellers;
$('checks-table').innerHTML=table(['Check','Expected','Observed','Result'],D.checks.map(x=>[x.check,x.expected,x.actual,x.pass?'Pass':'Failed']));
const tip=$('tip');function bindTips(){document.querySelectorAll('[data-tip]').forEach(e=>{e.setAttribute('tabindex','0');e.setAttribute('aria-label',e.dataset.tip);function show(v){tip.textContent=e.dataset.tip;tip.style.display='block';const b=e.getBoundingClientRect(),x=v.clientX??b.left+20,y=v.clientY??b.top+20;tip.style.left=Math.max(8,Math.min(x+12,innerWidth-tip.offsetWidth-8))+'px';tip.style.top=Math.max(8,Math.min(y+12,innerHeight-tip.offsetHeight-8))+'px'}e.onmousemove=show;e.onfocus=show;e.onmouseleave=()=>tip.style.display='none';e.onblur=()=>tip.style.display='none'})}
$('week').value=date(latest.current_week);renderPair();sellers();bindTips();
</script></body></html>'''
    page = template.replace('__CSS__', CSS).replace('__TREND__', trend).replace('__DATA__', payload)
    return rebase_links(page, base).replace('__NAV__', nav)
