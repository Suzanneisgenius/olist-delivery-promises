"""Stage 3 model report (numbers only from this run)."""
from __future__ import annotations

import json

import numpy as np
import pandas as pd

from .features import CFG, FEATURES
from .report import md_table

pct = lambda x, d=1: "n/a" if x is None or pd.isna(x) else f"{x * 100:.{d}f}%"
f3 = lambda x: "n/a" if pd.isna(x) else f"{x:.3f}"


def write(r: dict, path) -> None:
    res = r["res"].set_index("model")
    ci = r["ci"].set_index("quantity")
    sens = r["sens"]
    best_lr, best_gb = r["best"]["logistic"], r["best"]["gbm"]
    lr, gb, bl = res.loc["logistic"], res.loc["gbm"], res.loc["baseline"]
    winner = r["headline"]                      # chosen by dev AP, never by test
    cal = r["calib"]
    mean_pred = {m: float((g.mean_predicted * g.n).sum() / g.n.sum()) for m, g in cal.groupby("model")}
    s_wo = sens[sens.variant == "without estimated_days"].set_index("model")
    s_mo = sens[sens.variant == "test seller features refreshed monthly"].set_index("model")
    ex = r["excl"]
    imp = r["imp"]
    top_imp = lambda m: ", ".join(f"{x.feature} ({x.ap_drop_mean:+.3f})" for x in imp[imp.model == m].head(4).itertuples())

    def table_res():
        t = r["res"][["model", "n", "late", "prevalence", "average_precision", "roc_auc", "brier",
                      "brier_skill_vs_baseline", "precision_at_top", "recall_at_top"]].copy()
        for c in ["prevalence", "precision_at_top", "recall_at_top"]:
            t[c] = t[c].map(pct)
        for c in ["average_precision", "roc_auc", "brier", "brier_skill_vs_baseline"]:
            t[c] = t[c].map(f3)
        return t

    tune = r["tune"][["family", "params", "average_precision", "roc_auc", "brier", "precision_at_top"]].copy()
    for c in ["average_precision", "roc_auc", "brier"]:
        tune[c] = tune[c].map(f3)
    tune["precision_at_top"] = tune.precision_at_top.map(pct)
    splits = r["splits"].copy()
    splits["late_rate"] = splits.late_rate.map(pct)
    for c in ["first_purchase", "last_purchase"]:
        splits[c] = pd.to_datetime(splits[c]).dt.date
    exv = ex.copy()
    exv["late_share_excluded"] = exv.late_share_excluded.map(pct)
    sv = sens[["variant", "model", "average_precision", "roc_auc", "precision_at_top", "recall_at_top"]].copy()
    for c in ["average_precision", "roc_auc"]:
        sv[c] = sv[c].map(f3)
    for c in ["precision_at_top", "recall_at_top"]:
        sv[c] = sv[c].map(pct)
    seg = r["seg"][["segment", "value", "n", "prevalence", "average_precision", "precision_at_top", "recall_at_top"]].copy()
    for c in ["prevalence", "precision_at_top", "recall_at_top"]:
        seg[c] = seg[c].map(pct)
    seg["average_precision"] = seg.average_precision.map(f3)
    calv = cal.copy()
    for c in ["mean_predicted", "observed_rate"]:
        calv[c] = calv[c].map(lambda v: pct(v, 2))
    chk = r["checks"].copy()
    chk["expected"] = chk.expected.astype(str)
    chk["actual"] = chk.actual.astype(str)
    share = CFG["evaluation"]["top_share"]
    contrast = ci.loc['gbm_minus_logistic']
    ci_reading = ('The paired interval favours logistic.' if contrast['p97.5'] < 0 else
                  'The paired interval favours gradient boosting.' if contrast['p2.5'] > 0 else
                  'The paired interval includes zero; it does not distinguish the models.')
    over_bins = {m: int((g.mean_predicted > g.observed_rate).sum()) for m, g in cal.groupby('model')}

    L = [
        "# Stage 3 — Purchase-time Late-Delivery Risk Model",
        "",
        "Public Olist data, **offline simulation** of scoring an order at checkout. Every number comes from "
        "`python -m olist_analytics.run_stage3`, which runs only on a READY stage-1 release and writes this file only "
        "after every check in §9 passes. Design decisions are in `config/model.yaml`.",
        "",
        "## 1. Question and boundary",
        "- At purchase time, can we rank orders by risk of being delivered after the estimated day?",
        "- Label: late (L) = 1, on time (A) = 0. Only orders with a final A/L outcome and a single seller are "
        "modelled; the model says nothing about orders that are canceled, never confirmed, or multi-seller.",
        "- Features come only from checkout-time fields plus seller history known at a snapshot time. "
        f"Whitelist ({len(FEATURES)}): " + ", ".join(f"`{c}`" for c in FEATURES) + ".",
        "- **Assumption (unverified):** `estimated_days` uses the stored estimated date as if it were the one shown "
        "at checkout; there is no version history. §6 shows how much the model depends on it.",
        "- Other stored checkout/profile fields are also assumed available as recorded: the dataset has no "
        "historical versions of product weights or geolocation reference tables.",
        "",
        "## 2. Population and splits",
        md_table(r["steps"]),
        "",
        md_table(splits),
        "",
        f"Late rate shifts strongly: {pct(r['splits'].late_rate[0])} train → {pct(r['splits'].late_rate[1])} dev "
        f"(Feb–Mar 2018 spike) → {pct(r['splits'].late_rate[2])} test. The model is trained and judged under drift.",
        "",
        "## 3. Label availability (no future labels)",
        "A training or model-selection label is used only if the delivery happened before the relevant cut-off. Seller-history features use "
        "the same rule at their snapshot time (`outputs/stage3/seller_snapshots.csv`).",
        "",
        md_table(exv),
        "",
        "- **Cost of the rule:** excluded rows are much more often late (they took longer). Training therefore "
        "under-represents slow orders near each cut-off under this delivered-label convention. "
        "Using older purchase cohorts with a maturity buffer could reduce this selection at the cost of data and recency; "
        "that alternative was not tested in this revision.",
        "- Snapshots: training rows use the start of their purchase month; dev and test rows use a snapshot frozen at "
        "the start of their block (no labels from inside the block).",
        "- Historical handling medians exclude orders with invalid stage timestamps; these orders can still contribute "
        "known A/L labels to the seller's delay rate.",
        "",
        "## 4. Model choice on dev (test not used for model choice)",
        f"Model selection at {r['selection']['cutoff']} uses {r['selection']['n']:,} development orders "
        f"whose labels were already known, including {r['selection']['late']:,} late orders "
        f"({pct(r['selection']['prevalence'])}). Pending development labels are excluded from parameter and family choice.",
        md_table(tune),
        "",
        f"Chosen: logistic `{json.dumps(best_lr)}`, gradient boosting `{json.dumps(best_gb)}`. Both were then refit "
        "on train + dev (labels known before 2018-04-01), frozen, and evaluated on test. "
        "This protocol correction re-evaluates a test set already inspected in v0.3.0; it is not a fresh confirmatory holdout. "
        "No parameters or headline family were chosen from the test results.",
        "",
        "## 5. Test results (2018-04-01 → 2018-07-19)",
        md_table(table_res()),
        "",
        f"- **Finding.** Both models rank late orders far better than the constant baseline. Logistic regression: AP "
        f"{f3(lr.average_precision)} vs baseline {f3(bl.average_precision)} (= prevalence); ROC AUC {f3(lr.roc_auc)}.",
        f"- **Top {share:.0%} per purchase week** (hypothetical review capacity, not a real team resource): logistic "
        f"precision {pct(lr.precision_at_top)} vs {pct(bl.precision_at_top)} for one seeded random draw "
        f"(expected random precision {pct(bl.prevalence)}), catching "
        f"{pct(lr.recall_at_top)} of all late orders.",
        f"- **Uncertainty** (purchase-week bootstrap, {CFG['evaluation']['bootstrap']['reps']} reps): AP logistic "
        f"{f3(ci.loc['logistic', 'p2.5'])}–{f3(ci.loc['logistic', 'p97.5'])}, gbm "
        f"{f3(ci.loc['gbm', 'p2.5'])}–{f3(ci.loc['gbm', 'p97.5'])}; gbm − logistic "
        f"{ci.loc['gbm_minus_logistic', 'p50']:+.3f} ({ci.loc['gbm_minus_logistic', 'p2.5']:+.3f} to "
        f"{ci.loc['gbm_minus_logistic', 'p97.5']:+.3f}). {ci_reading} These intervals are conditional on the fitted models "
        "and sampled purchase weeks, not model-refitting uncertainty or protection against serial dependence across weeks.",
        f"- **Reading:** {winner} was selected using available development labels. Any explanation of cross-period "
        "performance, including overfitting or drift, remains an interpretation rather than a causal diagnosis.",
        "",
        "### Calibration",
        f"Mean predicted risk on test: logistic {pct(mean_pred['logistic'], 2)}, gbm {pct(mean_pred['gbm'], 2)}; "
        f"observed {pct(lr.prevalence, 2)}. Predicted risk exceeds observed frequency in "
        f"{over_bins['logistic']}/10 logistic bins and {over_bins['gbm']}/10 gradient-boosting bins. "
        "The mismatch is consistent with prevalence drift; these results do not establish its cause. "
        "Use ranking metrics for this benchmark; raw probabilities need validation before operational use. "
        "No recalibration was fitted. It can use an independent earlier calibration set with labels available before scoring; "
        "it does not require fitting on the final test labels.",
        "",
        md_table(calv),
        "",
        "## 6. Sensitivity",
        md_table(sv),
        "",
        f"- **Without `estimated_days`** AP falls to {f3(s_wo.loc['logistic', 'average_precision'])} (logistic) / "
        f"{f3(s_wo.loc['gbm', 'average_precision'])} (gbm). Much of the skill rests on the estimate assumption in §1.",
        f"- **Monthly seller refresh at test time** (instead of one frozen snapshot): logistic AP "
        f"{f3(s_mo.loc['logistic', 'average_precision'])}. Fresher history helps a little; the frozen result in §5 is the "
        "headline because it needs no online-update assumption.",
        "",
        f"## 7. Where it works and where it does not ({winner} scores, test; headline model chosen on dev)",
        md_table(seg),
        "",
        "Segments with < 300 orders or < 10 late orders are not shown. AP depends on prevalence, so compare each row "
        "with its own prevalence, not with other rows. Each row reselects its top fraction within that segment and week; "
        "these subgroup precision/recall values do not measure the composition of the global review queue.",
        "",
        "## 8. What the models use (permutation importance on test, AP drop)",
        f"- logistic: {top_imp('logistic')}",
        f"- gbm: {top_imp('gbm')}",
        "- Predictive use only. A feature with high importance is not a cause of lateness.",
        "",
        "## 9. Blocking checks",
        md_table(chk),
        "",
        "## 10. Limits",
        "- Offline simulation on a public snapshot; not a deployed model, no business outcome measured.",
        "- Population excludes U, X and multi-seller orders (selection; see §2).",
        "- Probabilities are mis-calibrated under drift (§5); use ranks, or recalibrate on recent labelled data.",
        "- Distance is a zip-prefix straight-line proxy; seller history uses single-seller orders only.",
        "- The review-score association (optional module 3b) is not part of this stage.",
        "",
        "## 11. Decisions for the owner",
        f"1. Accept {winner} (best dev AP) as the stage-3 headline model, with the other family reported as the comparison.",
        "2. Accept the `estimated_days` assumption with the sensitivity result shown next to it.",
        "3. Keep probabilities out of any portfolio claim until recalibrated; report AP, top-10% precision/recall.",
    ]
    path.write_text("\n".join(L) + "\n", encoding="utf-8")
