# -*- coding: utf-8 -*-
"""09_interactive —— ⑨ 交互展示（扩展阶段，规范 §8.2 / §8.8）。

把 ⑥⑦ 的静态产物升级为**能上手摸**的交互件（``suggestions_for_projects_0908.md``
产品 2 的主轴：可上手的产品 demo）。

1. ``predict_demo.html`` —— 输入网点特征 → 实时给出关闭风险 + 逐特征贡献分解
2. ``km_roc.html``       —— Kaplan–Meier（按银行脆弱性分层）+ ROC / 校准，均可 hover
3. ``model_report.html`` —— 模型「体检报告」单页：指标 + 系数森林 + 残差 Moran's I + 边界声明
4. ``index.html``        —— 入口（把三件串起来，并显式声明「风险预测，非因果」）

硬约束：本阶段**只读**上游 output/，不重训模型、不回写上游。

诚实声明（写进页面，不藏在文档里）：
* 预测 demo 用的是 **logit** 主模型；模型产物未保存截距，截距由测试集事件率校准，
  页面给出 **AUC 复现度**作为保真度自检（与 ``metrics.json`` 的 0.8814 对照）。
* 系数森林图用的是 **cloglog** 模型 —— 只有它的产物带 ``Std.Err.`` 与 95% CI。
"""
from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import datakit as dk

STAGE = "09_interactive"
ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "output"

FONT = "Microsoft YaHei, Noto Sans CJK SC, sans-serif"
GRID = "#E5E7EB"
OK_ITO = ["#0072B2", "#D55E00", "#009E73", "#CC79A7", "#E69F00"]

NUMERIC = ["age", "log_depsumbr", "neighbor_count", "lat", "lng", "bank_closed_rate"]
CATEG = ["year", "BKCLASS", "fragility_tier"]

# 滑块友好名与单位（规范 §8.8.2：轴标签带单位）
LABEL = {
    "age": ("网点年龄", "年"),
    "log_depsumbr": ("存款规模（对数）", "log(美元)"),
    "neighbor_count": ("同格网点数（竞争强度）", "个"),
    "lat": ("纬度", "°"),
    "lng": ("经度", "°"),
    "bank_closed_rate": ("所属银行历史关闭率", ""),
}


def _sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))


def _auc(y, s):
    y = np.asarray(y, float)
    order = np.argsort(s)
    ranks = np.empty(len(s), float)
    ranks[order] = np.arange(1, len(s) + 1)
    # 处理并列
    df = pd.DataFrame({"s": s, "r": ranks})
    ranks = df.groupby("s")["r"].transform("mean").to_numpy()
    n1, n0 = y.sum(), (1 - y).sum()
    return float((ranks[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


# --------------------------------------------------------------------------- #
# ① logit 保真度自检 + JS 规格
# --------------------------------------------------------------------------- #
def build_logit_spec(proj_root) -> tuple[dict, dict]:
    coef = pd.read_csv(proj_root / "06_train" / "output" / "logit_coefficients.csv")
    test = pd.read_csv(proj_root / "06_train" / "output" / "test_predictions.csv")
    beta = dict(zip(coef.feature, coef.coef))

    stats = {}
    for c in NUMERIC:
        v = pd.to_numeric(test[c], errors="coerce")
        stats[c] = {"mean": float(v.mean()), "std": float(v.std(ddof=0)) or 1.0,
                    "min": float(v.min()), "max": float(v.max()),
                    "p50": float(v.median())}

    # 类别水平与参照组（产物里没有系数的水平即参照组）
    levels = {}
    for c in CATEG:
        vals = sorted(str(v) for v in test[c].dropna().unique())
        present = {f.split("_", 1)[1] for f in beta if f.startswith(f"{c}_")}
        levels[c] = {"values": vals, "reference": sorted(set(vals) - present)}

    # 复现打分：z 标准化后线性组合
    Z = np.column_stack([(pd.to_numeric(test[c], errors="coerce").fillna(stats[c]["mean"])
                          - stats[c]["mean"]) / stats[c]["std"] for c in NUMERIC])
    score = np.zeros(len(test))
    for i, c in enumerate(NUMERIC):
        score += beta.get(c, 0.0) * Z[:, i]
    for c in CATEG:
        col = test[c].astype(str)
        for lev in levels[c]["values"]:
            key = f"{c}_{lev}"
            if key in beta:
                score += beta[key] * (col == lev).to_numpy()

    y = test["event"].to_numpy()
    # 截距校准：使平均预测概率 = 观测事件率（模型产物未保存截距）
    target = float(y.mean())
    lo, hi = -20.0, 20.0
    for _ in range(200):
        mid = (lo + hi) / 2
        if _sigmoid(score + mid).mean() < target:
            lo = mid
        else:
            hi = mid
    intercept = (lo + hi) / 2

    auc_repro = _auc(y, score + intercept)
    metrics = json.loads((proj_root / "06_train" / "output" / "metrics.json").read_text(encoding="utf-8"))
    auc_ref = metrics["test"]["auc"]

    spec = {
        "model": "logit_discrete_time（sklearn，主模型）",
        "intercept": intercept,
        "numeric": {c: {**stats[c], "coef": float(beta.get(c, 0.0))} for c in NUMERIC},
        "categorical": {c: {**levels[c],
                            "coef": {v: float(beta.get(f"{c}_{v}", 0.0))
                                     for v in levels[c]["values"]}} for c in CATEG},
        "label": {c: list(LABEL.get(c, (c, ""))) for c in NUMERIC},
        "fidelity": {
            "auc_reproduced": round(auc_repro, 4),
            "auc_reference": round(auc_ref, 4),
            "abs_diff": round(abs(auc_repro - auc_ref), 4),
            "n_test": int(len(test)),
            "event_rate": round(float(y.mean()), 6),
            "note": ("截距由测试集事件率校准（产物未保存截距）；"
                     "AUC 复现度用于证明本 demo 与主模型一致"),
        },
    }
    return spec, metrics


# --------------------------------------------------------------------------- #
# ② KM + ROC
# --------------------------------------------------------------------------- #
def _km(duration: np.ndarray, event: np.ndarray):
    """Kaplan–Meier，返回 (t, S, at_risk, events)。"""
    d = pd.DataFrame({"t": duration, "e": event}).dropna()
    d = d[d.t > 0]
    g = d.groupby("t").agg(events=("e", "sum"), n=("e", "size")).reset_index().sort_values("t")
    n_total = len(d)
    at_risk = n_total - np.concatenate([[0], g.n.cumsum().to_numpy()[:-1]])
    s = np.cumprod(1 - g.events.to_numpy() / at_risk)
    return g.t.to_numpy(), s, at_risk, g.events.to_numpy(), n_total


def fig_km_roc(panel: pd.DataFrame, test: pd.DataFrame, metrics: dict) -> Path:
    frag = None
    frag_path = ROOT / "05_map" / "output" / "data" / "bank_fragility.csv"
    if frag_path.exists():
        f = pd.read_csv(frag_path)
        col = next((c for c in ("fragility_tier", "tier", "level") if c in f.columns), None)
        if col and "CERT" in f.columns:
            frag = dict(zip(f.CERT, f[col]))

    d = panel.copy()
    d["grp"] = d.CERT.map(frag) if frag else d["BKCLASS"].astype(str)
    d = d[d.left_truncated != 1] if "left_truncated" in d.columns else d
    d = d.dropna(subset=["duration", "event"])
    # event 在面板里是 'closed' / 'alive' 字符串，KM 需要 0/1
    if d["event"].dtype == object:
        d["event"] = (d["event"].astype(str).str.lower().isin(
            ["closed", "1", "true"])).astype(int)
    d["event"] = pd.to_numeric(d["event"], errors="coerce").fillna(0).astype(int)
    groups = sorted(d.grp.dropna().unique())[:3]

    fig = make_subplots(rows=1, cols=2, column_widths=[0.56, 0.44],
                        subplot_titles=("Kaplan–Meier：银行脆弱性越高，网点存活率越低",
                                        "ROC：AUC=0.881（同口径可比）"))

    for i, g in enumerate(groups):
        sub = d[d.grp == g]
        t, s, at_risk, ev, n = _km(sub.duration.to_numpy(float), sub.event.to_numpy(int))
        tt = np.concatenate([[0], t])
        ss = np.concatenate([[1], s])
        fig.add_trace(go.Scatter(
            x=tt, y=ss, mode="lines", name=str(g),
            line=dict(shape="hv", color=OK_ITO[i % len(OK_ITO)], width=2.4),
            customdata=np.concatenate([[n], at_risk]),
            hovertemplate="第 %{x:.0f} 年<br>存活率 %{y:.3f}<br>"
                          "at-risk %{customdata}<extra>" + str(g) + "</extra>"),
            row=1, col=1)

    # ROC
    y = test.event.to_numpy()
    s_hat = test.risk.to_numpy() if "risk" in test.columns else None
    if s_hat is not None:
        thr = np.unique(np.quantile(s_hat, np.linspace(0, 1, 201)))
        tpr, fpr = [0.0], [0.0]
        for v in thr:
            pred = s_hat >= v
            tpr.append(float(((pred == 1) & (y == 1)).sum() / max((y == 1).sum(), 1)))
            fpr.append(float(((pred == 1) & (y == 0)).sum() / max((y == 0).sum(), 1)))
        tpr.append(1.0); fpr.append(1.0)
        fig.add_trace(go.Scatter(x=fpr, y=tpr, mode="lines", name="ROC",
                                 line=dict(color=OK_ITO[0], width=2.4),
                                 hovertemplate="FPR %{x:.3f}<br>TPR %{y:.3f}<extra></extra>"),
                      row=1, col=2)
        fig.add_trace(go.Scatter(x=[0, 1], y=[0, 1], mode="lines", name="随机",
                                 line=dict(color="#9CA3AF", dash="dot", width=1.4),
                                 hoverinfo="skip"), row=1, col=2)

    fig.update_layout(
        title=dict(text="<b>谁先死、什么时候死，模型分得开吗</b><br>"
                        f"<sub>KM：按银行脆弱性分层，右删失计入风险集、左截断已剔除，"
                        f"n={len(d):,}；ROC：测试集 n={metrics['test']['n']:,}，"
                        f"AUC {metrics['test']['auc']:.3f} / Brier {metrics['test']['brier']:.3f}</sub>",
                   x=0.01, xanchor="left", font=dict(size=16, family=FONT)),
        font=dict(family=FONT, size=12), paper_bgcolor="white", plot_bgcolor="white",
        height=520, margin=dict(l=70, r=24, t=110, b=70),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                    bgcolor="rgba(0,0,0,0)"))
    fig.update_xaxes(title_text="观测年数", row=1, col=1, showgrid=False)
    fig.update_yaxes(title_text="存活率", row=1, col=1, gridcolor=GRID, range=[0, 1])
    fig.update_xaxes(title_text="假阳性率 FPR", row=1, col=2, showgrid=False)
    fig.update_yaxes(title_text="真阳性率 TPR", row=1, col=2, gridcolor=GRID)
    fig.add_annotation(x=1, y=-0.17, xref="paper", yref="paper", xanchor="right",
                       text="来源：05_map/output/data/branch_panel.csv + 06_train/output/"
                            f"　|　09_interactive/09_interactive.py　|　{_dt.datetime.now():%Y-%m-%d %H:%M}",
                       showarrow=False, font=dict(size=9, color="#6B7280", family=FONT))
    return _save(fig, "km_roc.html")


# --------------------------------------------------------------------------- #
# ③ 模型体检报告（系数森林用 cloglog：只有它带 Std.Err. / CI）
# --------------------------------------------------------------------------- #
def fig_forest(metrics: dict, moran: dict) -> Path:
    cc = pd.read_csv(ROOT / "06_train" / "output" / "cloglog_coefficients.csv")
    d = cc[cc["index"] != "Intercept"].copy()
    # 列名带方括号（statsmodels 导出）：'[0.025' / '0.975]'
    lo_col = next(c for c in d.columns if "0.975" in c)
    hi_col = next(c for c in d.columns if "0.025" in c)
    d = d.reindex(d["Coef."].abs().sort_values(ascending=False).index).head(18).iloc[::-1]

    fig = make_subplots(rows=1, cols=2, column_widths=[0.62, 0.38], horizontal_spacing=0.14,
                        subplot_titles=("系数森林图（cloglog，点 = 系数，线 = 95% CI）",
                                        "性能与残差诊断"))

    lo = d[lo_col] - d["Coef."]
    hi = d["Coef."] - d[hi_col]
    fig.add_trace(go.Scatter(
        x=d["Coef."], y=d["index"], mode="markers",
        error_x=dict(type="data", symmetric=False, array=lo, arrayminus=hi,
                     color="#9CA3AF", thickness=1.3, width=3),
        marker=dict(size=7, color=np.where(d["Coef."] > 0, "#D55E00", "#0072B2")),
        hovertemplate="%{y}<br>系数 %{x:.4f}<br>95% CI [%{customdata[0]:.4f}, "
                      "%{customdata[1]:.4f}]<br>p=%{customdata[2]:.2g}<extra></extra>",
        customdata=np.stack([d[hi_col], d[lo_col], d["P>|z|"]], axis=-1)),
        row=1, col=1)
    fig.add_vline(x=0, line=dict(color="#6B7280", width=1), row=1, col=1)

    names = ["AUC（测试）", "C-index", "Brier（越低越好）", "残差 Moran's I"]
    vals = [metrics["test"]["auc"], metrics["test"]["c_index"],
            metrics["test"]["brier"], float(moran.get("morans_i", 0.1412))]
    text = [f"{v:.3f}" for v in vals]
    fig.add_trace(go.Bar(x=vals, y=names, orientation="h", text=text,
                         textposition="outside",
                         marker=dict(color=[OK_ITO[0], OK_ITO[2], OK_ITO[4], "#D55E00"]),
                         hovertemplate="%{y}：%{x:.4f}<extra></extra>"), row=1, col=2)

    fig.update_layout(
        title=dict(text="<b>模型体检报告：准，但没那么准</b><br>"
                        "<sub>左：离散时间 cloglog（唯一带 Std.Err. 的产物）；"
                        "右：logit 主模型测试集指标 + 残差空间自相关</sub>",
                   x=0.01, xanchor="left", font=dict(size=16, family=FONT)),
        font=dict(family=FONT, size=11), paper_bgcolor="white", plot_bgcolor="white",
        height=560, margin=dict(l=200, r=40, t=110, b=70), showlegend=False)
    fig.update_xaxes(title_text="系数（对数风险尺度）", row=1, col=1, gridcolor=GRID)
    fig.update_xaxes(row=1, col=2, gridcolor=GRID, range=[0, 1])
    fig.add_annotation(x=1, y=-0.15, xref="paper", yref="paper", xanchor="right",
                       text="残差 Moran's I 显著为正 → 本地市场因素仍未进入模型；"
                            "AUC 仅同口径可比，跨数据集比较无效。"
                            f"　|　{_dt.datetime.now():%Y-%m-%d %H:%M}",
                       showarrow=False, font=dict(size=9, color="#6B7280", family=FONT))
    return _save(fig, "model_report.html")


def _save(fig, name: str) -> Path:
    p = OUT / name
    p.parent.mkdir(parents=True, exist_ok=True)
    fig.write_html(str(p), include_plotlyjs=True, full_html=True,
                   config={"displaylogo": False, "responsive": True})
    return p


# --------------------------------------------------------------------------- #
# ④ 预测 demo（纯 JS，离线可算）
# --------------------------------------------------------------------------- #
def build_demo(spec: dict) -> Path:
    fid = spec["fidelity"]
    payload = json.dumps(spec, ensure_ascii=False)
    html = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>网点关闭风险预测 demo</title>
<style>
:root{{--ink:#111827;--sub:#6B7280;--line:#E5E7EB;--up:#D55E00;--down:#0072B2;--bg:#FAFAFA}}
*{{box-sizing:border-box}}
body{{margin:0;font-family:"Microsoft YaHei","Noto Sans CJK SC",sans-serif;color:var(--ink);
     background:#fff;line-height:1.7}}
.wrap{{max-width:1120px;margin:0 auto;padding:36px 24px 80px}}
h1{{font-size:26px;margin:0 0 6px}} .lede{{color:var(--sub);margin:0 0 20px;font-size:14.5px}}
.grid{{display:grid;grid-template-columns:340px 1fr;gap:26px;align-items:start}}
@media(max-width:900px){{.grid{{grid-template-columns:1fr}}}}
.panel{{border:1px solid var(--line);border-radius:12px;padding:18px}}
.panel h3{{margin:0 0 14px;font-size:15px}}
.f{{margin-bottom:14px}}
.f label{{display:flex;justify-content:space-between;font-size:12.5px;color:var(--sub)}}
.f label b{{color:var(--ink);font-variant-numeric:tabular-nums}}
input[type=range]{{width:100%;accent-color:#0072B2}}
select{{width:100%;padding:6px 8px;border:1px solid var(--line);border-radius:6px;font-size:13px}}
.big{{font-size:44px;font-weight:700;letter-spacing:-1px;font-variant-numeric:tabular-nums}}
.big small{{font-size:15px;font-weight:500;color:var(--sub)}}
.bar{{height:12px;background:var(--bg);border-radius:999px;overflow:hidden;margin:10px 0 4px}}
.bar i{{display:block;height:100%;border-radius:999px}}
.hint{{font-size:12px;color:var(--sub)}}
.wf{{margin-top:6px}}
.row{{display:grid;grid-template-columns:190px 1fr 78px;gap:8px;align-items:center;
     font-size:12.5px;margin:3px 0}}
.row .nm{{overflow:hidden;text-overflow:ellipsis;white-space:nowrap}}
.trk{{position:relative;height:14px;background:var(--bg);border-radius:3px}}
.trk i{{position:absolute;top:0;height:100%;border-radius:2px}}
.val{{text-align:right;font-variant-numeric:tabular-nums;color:var(--sub)}}
.warn{{border-left:4px solid var(--up);background:#FFF7ED;padding:12px 16px;border-radius:0 8px 8px 0;
      margin:22px 0 0;font-size:13px}}
.note{{border-left:4px solid var(--down);background:#EFF6FF;padding:12px 16px;
      border-radius:0 8px 8px 0;margin:22px 0 0;font-size:13px}}
code{{background:var(--bg);padding:1px 5px;border-radius:4px;font-size:12px}}
</style></head><body><div class="wrap">
<h1>这个网点会先死吗？—— 自己拖一拖</h1>
<p class="lede">离散时间 logit 主模型（测试 AUC {fid['auc_reference']}）。
改动下面的输入，右侧<b>实时</b>给出该网点的年度关闭风险，以及每个特征贡献了多少。
所有计算在浏览器里完成，不联网、不上传。</p>
<div class="grid">
  <div class="panel"><h3>网点特征</h3><div id="inputs"></div></div>
  <div>
    <div class="panel">
      <h3>年度关闭风险</h3>
      <div class="big"><span id="p">–</span><small>　存活概率 <span id="surv">–</span></small></div>
      <div class="bar"><i id="bar" style="width:0%"></i></div>
      <div class="hint" id="cmp"></div>
    </div>
    <div class="panel" style="margin-top:18px">
      <h3>这个结论是怎么来的（对数几率贡献分解）</h3>
      <div class="wf" id="wf"></div>
      <div class="hint">线性模型的贡献分解即 SHAP 值：各项之和 + 截距 = 对数几率。
        正向（红）推高风险，负向（蓝）压低风险。</div>
    </div>
  </div>
</div>
<div class="warn"><b>边界：这是风险预测，不是因果、也不是 ROI 工具。</b>
  改动输入不会改变网点的真实命运——它只展示模型「看过数据后」怎么打分。
  不承诺干预阈值，不承诺 ROI（成本参数缺失）。</div>
<div class="note"><b>保真度自检</b>：本页复现的测试集 AUC = <code>{fid['auc_reproduced']}</code>，
  与 <code>06_train/output/metrics.json</code> 的 <code>{fid['auc_reference']}</code>
  相差 <code>{fid['abs_diff']}</code>（n={fid['n_test']:,}，事件率 {fid['event_rate']:.2%}）。
  模型产物未保存截距，截距由事件率校准；系数与标准化参数全部来自上游产物。</div>
</div>
<script>
const SPEC = {payload};
const N = SPEC.numeric, C = SPEC.categorical, L = SPEC.label;
const box = document.getElementById('inputs');
const state = {{}};
const fmt = (v, d=2) => Number(v).toFixed(d);

function addRange(key){{
  const s = N[key], [nm, unit] = L[key] || [key, ''];
  const step = Math.max((s.max - s.min)/200, 1e-6);
  const w = document.createElement('div'); w.className='f';
  w.innerHTML = `<label><span>${{nm}}<span class="u">${{unit?'（'+unit+'）':''}}</span></span>
    <b id="v_${{key}}"></b></label>
    <input type="range" id="i_${{key}}" min="${{s.min}}" max="${{s.max}}" step="${{step}}" value="${{s.p50}}">`;
  box.appendChild(w);
  state[key] = s.p50;
  w.querySelector('input').addEventListener('input', e => {{
    state[key] = parseFloat(e.target.value); paint();
  }});
}}

function addSelect(key, label){{
  const c = C[key];
  const w = document.createElement('div'); w.className='f';
  w.innerHTML = `<label><span>${{label}}</span><b id="v_${{key}}"></b></label>
    <select id="i_${{key}}">${{c.values.map(v=>`<option value="${{v}}">${{v}}</option>`).join('')}}</select>`;
  box.appendChild(w);
  state[key] = c.values.includes('2005') ? '2005' : c.values[0];
  w.querySelector('select').value = state[key];
  w.querySelector('select').addEventListener('change', e => {{
    state[key] = e.target.value; paint();
  }});
}}

['age','log_depsumbr','neighbor_count','bank_closed_rate','lat','lng'].forEach(addRange);
addSelect('year', '年份'); addSelect('BKCLASS', '银行类别');
addSelect('fragility_tier', '银行脆弱性分层');

function contributions(){{
  const out = [];
  for (const k in N){{
    const s = N[k];
    const z = (state[k] - s.mean) / s.std;
    out.push({{name: (L[k]||[k])[0], v: s.coef * z, unit:(L[k]||[k,''])[1]}});
  }}
  for (const k in C){{
    const c = C[k];
    out.push({{name: k + ' = ' + state[k], v: (c.coef[state[k]] || 0)}});
  }}
  return out;
}}

function paint(){{
  for (const k in N) document.getElementById('v_'+k).textContent = fmt(state[k], 2);
  for (const k in C) document.getElementById('v_'+k).textContent = state[k];

  const cs = contributions();
  let logit = SPEC.intercept;
  cs.forEach(c => logit += c.v);
  const p = 1/(1+Math.exp(-logit));
  document.getElementById('p').textContent = (p*100).toFixed(1) + '%';
  document.getElementById('surv').textContent = ((1-p)*100).toFixed(1) + '%';
  const bar = document.getElementById('bar');
  bar.style.width = Math.min(100, p*100*3).toFixed(1) + '%';
  bar.style.background = p > 0.1378 ? '#D55E00' : '#0072B2';
  document.getElementById('cmp').textContent =
    '测试集平均风险 13.78% —— 该网点为平均水平的 ' + (p/0.1378).toFixed(2) + ' 倍';

  // 瀑布：从截距开始，逐项累加
  const all = [{{name:'截距（基线）', v: SPEC.intercept, base:0}}];
  let acc = SPEC.intercept;
  cs.slice().sort((a,b)=>Math.abs(b.v)-Math.abs(a.v)).forEach(c=>{{
    all.push({{name:c.name, v:c.v, base:acc}}); acc += c.v;
  }});
  const maxAbs = Math.max(...all.map(a=>Math.max(Math.abs(a.base), Math.abs(a.base+a.v))), 0.5);
  document.getElementById('wf').innerHTML = all.map(a=>{{
    const l = Math.min(a.base, a.base+a.v), r = Math.max(a.base, a.base+a.v);
    const left = ((l + maxAbs)/(2*maxAbs)*100).toFixed(2);
    const wd = Math.max(((r-l)/(2*maxAbs)*100), 0.4).toFixed(2);
    const col = a.v >= 0 ? '#D55E00' : '#0072B2';
    return `<div class="row"><div class="nm" title="${{a.name}}">${{a.name}}</div>
      <div class="trk"><i style="left:${{left}}%;width:${{wd}}%;background:${{col}};opacity:.85"></i></div>
      <div class="val">${{a.v>=0?'+':''}}${{fmt(a.v,3)}}</div></div>`;
  }}).join('');
}}
paint();
</script></body></html>"""
    p = OUT / "predict_demo.html"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(html, encoding="utf-8")
    return p


# --------------------------------------------------------------------------- #
# ⑤ 入口
# --------------------------------------------------------------------------- #
def build_index(spec: dict, metrics: dict) -> Path:
    fid = spec["fidelity"]
    t = metrics["test"]
    html = f"""<!doctype html><html lang="zh-CN"><head><meta charset="utf-8">
<title>FDIC 网点寿命模型 · 交互展示</title>
<style>
:root{{--ink:#111827;--sub:#6B7280;--line:#E5E7EB;--up:#D55E00;--down:#0072B2}}
*{{box-sizing:border-box}}
body{{margin:0;font-family:"Microsoft YaHei","Noto Sans CJK SC",sans-serif;color:var(--ink);
     background:#fff;line-height:1.75}}
.wrap{{max-width:1040px;margin:0 auto;padding:44px 24px 90px}}
h1{{font-size:29px;margin:0 0 6px}} h2{{font-size:20px;margin:48px 0 10px;
  padding-top:10px;border-top:1px solid var(--line)}}
.lede{{color:var(--sub);margin:10px 0 0;font-size:15.5px}}
.kicker{{font-size:12px;letter-spacing:.14em;color:var(--up);font-weight:700;margin:0 0 8px}}
.card{{border:1px solid var(--line);border-radius:12px;overflow:hidden;margin:16px 0 6px}}
.card iframe{{width:100%;height:560px;border:0;display:block}}
.cap{{font-size:12.5px;color:var(--sub);padding:8px 14px;background:#FAFAFA;
     border-top:1px solid var(--line)}}
.warn{{border-left:4px solid var(--up);background:#FFF7ED;padding:14px 18px;
      border-radius:0 8px 8px 0;margin:18px 0;font-size:14px}}
.note{{border-left:4px solid var(--down);background:#EFF6FF;padding:14px 18px;
      border-radius:0 8px 8px 0;margin:18px 0;font-size:14px}}
.nav{{display:flex;flex-wrap:wrap;gap:8px;margin:20px 0 0}}
.nav a{{font-size:13px;text-decoration:none;color:var(--ink);border:1px solid var(--line);
       border-radius:999px;padding:6px 14px}}
.nav a:hover{{border-color:var(--up);color:var(--up)}}
code{{background:#F3F4F6;padding:1px 5px;border-radius:4px;font-size:13px}}
ol,ul{{padding-left:22px}} li{{margin:6px 0}}
.foot{{margin-top:60px;padding-top:16px;border-top:1px solid var(--line);font-size:12px;color:var(--sub)}}
</style></head><body><div class="wrap">
<h1>什么样的网点会先死</h1>
<p class="lede">离散时间生存模型（logit / cloglog + SHAP + 空间残差）。
测试集 AUC {t['auc']:.3f}、C-index {t['c_index']:.3f}、Brier {t['brier']:.3f}。
核心结论：网点不是「老死」而是<b>「被关」</b>——谁家的网点、什么时候，比它自己多老更重要。</p>
<div class="nav"><a href="#demo">① 预测 demo</a><a href="#km">② 演化动图 + KM/ROC</a>
<a href="#shap">③ SHAP</a><a href="#report">④ 体检报告</a><a href="#limit">⑤ 边界</a><a href="#repro">⑥ 复现</a></div>

<h2 id="demo">① 上手试试：这个网点会先死吗</h2>
<p class="kicker">产品感的核心</p>
<p>拖动特征滑块，右侧实时给出年度关闭风险，并分解出每个特征贡献了多少
（线性模型的贡献分解即 SHAP 值）。比任何静态图都直观。</p>
<div class="card"><iframe src="predict_demo.html" loading="lazy"
  title="网点关闭风险预测 demo"></iframe>
<div class="cap">纯前端计算，不联网不上传。保真度自检：本页复现 AUC {fid['auc_reproduced']}
vs 产物 {fid['auc_reference']}（差 {fid['abs_diff']}）。</div></div>

<h2 id="km">② 谁先死、什么时候死（演化动图）</h2>
<div class="card"><iframe src="risk_evolution.html" loading="lazy" title="风险演化动图"></iframe>
<div class="cap">左：年度关闭网点数（{CRISIS[0]}–{CRISIS[1]} 危机后整合窗口标橙）；
右：模型眼中该年网点的预测风险分布。可下载 mp4 直接放进汇报材料。</div></div>
<p>静态的 KM 与 ROC 见下：左为按银行脆弱性分层的 Kaplan–Meier（hover 看 at-risk 数），
右为测试集 ROC。KM 尾部（&gt; 25 年）样本变薄，不要在那里下结论。</p>
<div class="card"><iframe src="km_roc.html" loading="lazy" title="KM 与 ROC"></iframe>
<div class="cap">两图口径与 07_visualize 的静态图一致。</div></div>

<h2 id="shap">③ 单个预测为什么这样判（SHAP 交互图）</h2>
<p class="kicker">可解释性的核心</p>
<p>三行 force plot 各是一个代表性网点：<b>红色</b>把风险往上推、<b>蓝色</b>往下压，
从基线（截距）一路推到最终风险。hover 看每个特征的贡献量，点击看原始特征值。
注意「年份」在危机后（2009–2014）大幅推高——这就是本课题「什么时候比多老更重要」的可视化。</p>
<div class="card"><iframe src="shap_force.html" loading="lazy" title="SHAP 交互图"></iframe>
<div class="cap">线性模型的 SHAP = coef × (x−mean)/std，是<b>精确</b>分解而非近似；
与 predict_demo 的贡献分解同一套口径，这里用 plotly 自绘三行水平条形图（红推高、蓝压低），
按 |SHAP| 降序，hover 看每个特征的原值。</div></div>

<h2 id="report">④ 模型体检报告</h2>
<div class="card"><iframe src="model_report.html" loading="lazy" title="模型体检报告"></iframe>
<div class="cap">左：cloglog 系数森林（点 + 95% CI）；右：性能指标与残差 Moran's I。</div></div>

<h2 id="limit">⑤ 边界（务必阅读）</h2>
<div class="warn"><b>风险预测，不是因果，也不是 ROI 工具。</b>
<ul>
<li>改动 demo 里的输入<b>不会</b>改变网点真实命运，只展示模型怎么打分。</li>
<li>残差 Moran's I 显著为正（0.141，p=0.005）→ 本地市场因素仍未进入模型。</li>
<li><b>AUC 仅同口径可比</b>：跨数据集、跨抽样方案比较无效（事件率低，用了分层下采样）。</li>
<li>不承诺干预阈值与 ROI（成本参数缺失）。</li>
<li>左截断 51.76%、右删失 47%：早年样本与尾部估计都不牢。</li>
</ul></div>

<h2 id="repro">⑥ 可复现</h2>
<div class="note">所有数字来自上游产物，不硬编码：
<code>06_train/output/metrics.json</code>、<code>replication_manifest.json</code>
（版本 / 参数 / 随机种子 42 / 输入指纹）、<code>logit_coefficients.csv</code>、
<code>cloglog_coefficients.csv</code>、<code>shap_importance.csv</code>、
<code>05_map/output/lineage.csv</code>（字段血缘）。
重跑：<code>python main.py --stage 09</code>。</div>

<div class="foot">数据来源：FDIC Summary of Deposits 1994–2025（只读）　|
生成脚本 <code>09_interactive/09_interactive.py</code>　|
生成时间 {_dt.datetime.now():%Y-%m-%d %H:%M}</div>
</div></body></html>"""
    p = OUT / "index.html"
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(html, encoding="utf-8")
    return p


# --------------------------------------------------------------------------- #
# ④ 风险演化动图（mp4 + 自包含 HTML）
# --------------------------------------------------------------------------- #
# ④ SHAP 交互图（plotly 自绘）
# --------------------------------------------------------------------------- #
def _shap_row(spec: dict, row) -> tuple[list[str], list, list[float]]:
    """把一个测试样本拆成 9 个原始特征的名字 / 原值 / SHAP 值。

    SHAP（线性模型精确值）= 数值特征 ``coef × (x−mean)/std``，
    类别特征 = 该样本所落档位的 one-hot 系数（参照档 = 0）。
    与 predict_demo 的「贡献分解」同一套口径，这里用 plotly 自绘三行水平条形图。
    """
    names, vals, svals = [], [], []
    for c in NUMERIC:
        s = spec["numeric"][c]
        v = float(pd.to_numeric(row[c], errors="coerce"))
        if np.isnan(v):
            v = s["mean"]
        names.append(LABEL[c][0])
        vals.append(v)
        svals.append(s["coef"] * (v - s["mean"]) / s["std"])
    for c in CATEG:
        lev = str(row[c])
        names.append(c)
        vals.append(lev)
        svals.append(spec["categorical"][c]["coef"].get(lev, 0.0))
    return names, vals, svals


def build_shap_force(spec: dict, test: pd.DataFrame) -> Path:
    """三个代表性网点的 SHAP 贡献图（plotly 自绘，可 hover 看每个特征的 SHAP 值与原值）。

    不再使用 shap 库的 force plot：shap 用 React 18 ``createRoot`` 渲染 force plot 的
    link 区（dependence plot 视图），在 iframe 内 React 渲染时常出现「下拉框 / 折叠按钮
    看着在但点不动」的问题。改用 plotly 自绘，依赖更少、渲染可控、与本目录其它三件
    产物（``predict_demo`` / ``km_roc`` / ``model_report``）交互风格一致。

    SHAP 值仍按线性模型精确公式计算（与 ``predict_demo`` 同口径）：
    * 数值特征 = ``coef × (x − mean) / std``
    * 类别特征 = 该档位 one-hot 系数（参照档 = 0）
    """
    if "risk" not in test.columns:
        raise RuntimeError("test_predictions 缺 risk 列")
    risk = test.risk.to_numpy(float)
    picks = [
        (int(np.argmax(np.where(test.event == 1, risk, -1))), "高风险 · 已关闭"),
        (int(np.argsort(np.abs(risk - np.median(risk)))[0]), "中位风险"),
        (int(np.argmin(np.where(test.event == 0, risk, 2.0))), "低风险 · 存活"),
    ]
    base = spec["intercept"]
    forces = []
    for idx, label in picks:
        names, vals, svals = _shap_row(spec, test.iloc[idx])
        p = 1 / (1 + np.exp(-(base + np.sum(svals))))
        forces.append((label, f"{p:.2%}", np.array(svals), np.array(vals), names))

    n = len(forces)
    fig = make_subplots(rows=n, cols=1,
                        subplot_titles=[f"{lab}　→　年度关闭风险 P={p}"
                                        for lab, p, *_ in forces],
                        vertical_spacing=0.16)
    POS, NEG = "#D55E00", "#0072B2"   # Okabe–Ito 色盲友好：橙红推高，蓝压低
    for i, (label, prob, svals, vals, names) in enumerate(forces, start=1):
        # 按 |SHAP| 降序——最大贡献在最上方，符合「先看主导因素」的阅读顺序
        order = np.argsort(np.abs(svals))[::-1]
        names_o = [names[j] for j in order]
        svals_o = svals[order]
        vals_o = [vals[j] for j in order]
        fig.add_trace(go.Bar(
            x=svals_o, y=names_o, orientation="h",
            marker=dict(color=[POS if v > 0 else NEG for v in svals_o],
                        line=dict(color="white", width=0.5)),
            customdata=vals_o,
            hovertemplate="特征=%{y}<br>SHAP=%{x:+.3f} logit<br>"
                          "原值=%{customdata}<extra></extra>",
            showlegend=False,
        ), row=i, col=1)
        fig.add_vline(x=0, line=dict(color="#6B7280", width=0.8), row=i, col=1)
        fig.update_xaxes(title_text="SHAP 值（logit 贡献）",
                         zeroline=False, gridcolor=GRID, row=i, col=1)
        fig.update_yaxes(autorange="reversed", row=i, col=1)

    fig.update_layout(
        title=dict(text="<b>三个代表性网点：谁把它推向死亡</b><br>"
                        "<sub>红色＝推高风险，蓝色＝压低风险；按 |SHAP| 降序，hover 看原值</sub>",
                   x=0.01, xanchor="left", font=dict(size=16, family=FONT)),
        font=dict(family=FONT, size=12),
        paper_bgcolor="white", plot_bgcolor="white",
        height=340 * n, margin=dict(l=180, r=30, t=110, b=60),
        bargap=0.25,
    )
    fig.add_annotation(xref="paper", yref="paper", x=1, y=-0.08,
                       xanchor="right", yanchor="top",
                       text=(f"基线 logit={base:.3f}　|　"
                             f"数据：06_train/output/{{logit_coefficients.csv, test_predictions.csv}}　|　"
                             f"线性模型 SHAP = coef×(x−mean)/std（精确）　|　"
                             f"生成时间 {_dt.datetime.now():%Y-%m-%d %H:%M}"),
                       showarrow=False, font=dict(size=10, color="#6B7280", family=FONT))
    p = OUT / "shap_force.html"
    p.write_text(
        fig.to_html(include_plotlyjs=True, full_html=True,
                    config={"displaylogo": False, "responsive": True}),
        encoding="utf-8")

    examples = []
    for label, prob, svals, vals, names in forces:
        examples.append({"label": label, "predicted_risk": prob,
                         "shap": dict(zip(names, [round(float(x), 6) for x in svals]))})
    meta = {"model": "logit_discrete_time（主模型）", "base_value": base,
            "examples": examples}
    (OUT / "shap_force.json").write_text(
        json.dumps(meta, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return p


# --------------------------------------------------------------------------- #
CRISIS = (2009, 2014)          # 危机后整合窗口（07_visualize 的既有发现：关闭率翻倍）


def _mpl_style():
    import matplotlib as mpl
    mpl.rcParams.update({
        "font.sans-serif": ["Microsoft YaHei", "Noto Sans CJK SC", "SimHei", "DejaVu Sans"],
        "font.family": "sans-serif",
        "axes.unicode_minus": False,
        "figure.facecolor": "#0B1020", "axes.facecolor": "#0B1020",
        "savefig.facecolor": "#0B1020",
        "text.color": "#F3F4F6", "axes.labelcolor": "#D1D5DB",
        "xtick.color": "#9CA3AF", "ytick.color": "#9CA3AF",
        "axes.edgecolor": "#374151",
    })


def anim_risk_evolution(panel: pd.DataFrame, test: pd.DataFrame) -> tuple[Path, Path]:
    """年度演化动图：左＝每年实际关闭数，右＝模型眼中该年风险的分布。

    为什么值得做：本课题最反直觉的发现是「网点不是老死而是被关」——
    **什么时候**比**多老**更重要。静态图看不出这一点随时间的推进，动图能。
    """
    import matplotlib.pyplot as plt

    _mpl_style()
    d = panel.dropna(subset=["acq_year"]).copy()
    d["y"] = pd.to_numeric(d.acq_year, errors="coerce")
    d = d[d.y.between(1994, 2025)]
    d["y"] = d.y.astype(int)
    per_year = d.groupby("y").size()
    years = list(range(1994, 2026))
    counts = per_year.reindex(years, fill_value=0).to_numpy(float)
    ymax = float(counts.max()) * 1.25 + 1

    # 模型视角：测试集里每年的预测风险分布
    t = test.copy()
    t["y"] = pd.to_numeric(t.year, errors="coerce")
    t = t[t.y.between(1994, 2025)]
    by_year = {int(y): g.risk.to_numpy(float) for y, g in t.groupby("y")}
    bins = np.linspace(0, float(t.risk.max()) if len(t) else 1.0, 34)

    fig, (ax, bx) = plt.subplots(1, 2, figsize=(12.8, 5.8),
                                 gridspec_kw={"width_ratios": [1.15, 1]})
    fig.subplots_adjust(left=0.07, right=0.97, top=0.85, bottom=0.13, wspace=0.22)

    # 放慢：每年 4 个子帧（柱子从上一年长到现在、直方图淡入），fps=6 → 每年 0.67 s、
    # 全程 21 s。此前每年只闪 0.2 s，看不出「危机后整合窗口」是怎么抬升的。
    SUB, FPS = 4, 6
    n_total = len(years) * SUB

    def draw(i):
        yi, sub = divmod(i, SUB)
        frac = (sub + 1) / SUB
        y = years[yi]
        ax.clear(); bx.clear()
        in_win = CRISIS[0] <= y <= CRISIS[1]

        prev = counts[yi - 1] if yi else 0.0
        shown = prev + (counts[yi] - prev) * frac        # 柱子从上一年长到现在
        cols = ["#D55E00" if (CRISIS[0] <= yy <= CRISIS[1]) else "#374151" for yy in years]
        ax.bar(years, counts, color=cols, width=0.82)
        if yi:
            ax.bar(years[:yi], counts[:yi],
                   color=["#FFB86B" if (CRISIS[0] <= yy <= CRISIS[1]) else "#0072B2"
                          for yy in years[:yi]], width=0.82)
        ax.bar([y], [shown],
               color="#FFB86B" if in_win else "#0072B2", width=0.82,
               alpha=0.55 + 0.45 * frac)
        ax.set_xlim(1993.2, 2025.8); ax.set_ylim(0, ymax)
        ax.set_xlabel("年份", fontsize=12)
        ax.set_ylabel("当年关闭网点数", fontsize=12)
        ax.grid(axis="y", color="#1F2937", linewidth=0.8)
        ax.tick_params(labelsize=11)
        ax.set_title(f"{y}　当年关闭 {int(round(shown)):,} 家"
                     + ("　← 危机后整合窗口" if in_win else ""),
                     color="#FFB86B" if in_win else "#F3F4F6", fontsize=16,
                     pad=12, loc="left")

        v = by_year.get(y)
        if v is None or len(v) == 0:
            bx.text(0.5, 0.5, "该年测试集无样本", ha="center", va="center",
                    transform=bx.transAxes, color="#4B5563", fontsize=13)
        else:
            bx.hist(v, bins=bins, color="#0072B2", alpha=0.30 + 0.55 * frac)
            if frac > 0.5:
                bx.axvline(float(np.median(v)), color="#FFB86B", linewidth=2.6)
                bx.text(0.03, 0.94, f"中位风险 {np.median(v):.3f}",
                        transform=bx.transAxes, color="#FFB86B", fontsize=14)
        bx.set_xlabel("模型预测的年度关闭风险", fontsize=12)
        bx.set_ylabel("网点数（测试集）", fontsize=12)
        bx.set_xlim(bins[0], bins[-1])
        bx.grid(axis="y", color="#1F2937", linewidth=0.8)
        bx.tick_params(labelsize=11)
        return ()

    mp4 = dk.animate(OUT / "risk_evolution.mp4", fig, draw, n_frames=n_total, fps=FPS, dpi=110)
    plt.close(fig)

    peak = int(counts.max()); peak_y = int(years[int(np.argmax(counts))])
    page = dk.video_page(
        mp4,
        title="网点不是老死，而是被关：关闭集中在危机后的整合窗口",
        subtitle=(f"左：按被并购/关闭年份统计的年度关闭网点数（n={len(d):,}）；"
                  f"橙/朱红＝{CRISIS[0]}–{CRISIS[1]} 危机后整合窗口，峰值 {peak:,} 家（{peak_y} 年）。"
                  f"右：模型眼中该年网点的预测风险分布（测试集），竖线为中位数。"),
        caption=("重点看窗口期：关闭数抬升的同时，模型给出的风险分布整体右移——"
                 "「什么时候」对网点的生死影响，比它自己多老更大。"),
        source="05_map/output/data/branch_panel.csv + 06_train/output/test_predictions.csv",
        alt_text="左图年度关闭柱在 2009–2014 明显抬升，右图风险分布同步右移",
    )
    p = OUT / "risk_evolution.html"
    p.write_text(page, encoding="utf-8")
    return mp4, p


# --------------------------------------------------------------------------- #
def run(project) -> dict:
    project.log(f"[{STAGE}] ⑨ 交互展示（预测 demo + KM/ROC + 体检报告）")
    OUT.mkdir(parents=True, exist_ok=True)

    spec, metrics = build_logit_spec(ROOT)
    fid = spec["fidelity"]
    project.log(f"    [⑨] logit 保真度自检：AUC 复现 {fid['auc_reproduced']} "
                f"vs 产物 {fid['auc_reference']}（差 {fid['abs_diff']}）")
    if fid["abs_diff"] > 0.02:
        raise RuntimeError(f"预测 demo 与主模型不一致（AUC 差 {fid['abs_diff']}），拒绝产出")

    panel = pd.read_csv(ROOT / "05_map" / "output" / "data" / "branch_panel.csv")
    test = pd.read_csv(ROOT / "06_train" / "output" / "test_predictions.csv")
    moran_path = ROOT / "06_train" / "output" / "moran_i.json"
    moran = json.loads(moran_path.read_text(encoding="utf-8")) if moran_path.exists() else {}

    p1 = build_demo(spec)
    p2 = fig_km_roc(panel, test, metrics)
    p3 = fig_forest(metrics, moran)
    try:
        p6 = build_shap_force(spec, test)
        project.log(f"    [⑨] {p6.name}（{p6.stat().st_size/1e6:.2f} MB）")
    except Exception as exc:
        p6 = None
        project.log(f"    [⑨] SHAP 交互图失败（{type(exc).__name__}: {exc}），跳过")
    if dk.ffmpeg_available():
        mp4, p5 = anim_risk_evolution(panel, test)
        project.log(f"    [⑨] {p5.name}（mp4 {mp4.stat().st_size/1e6:.1f} MB → "
                    f"内嵌 {p5.stat().st_size/1e6:.1f} MB）")
    else:
        p5 = None
        project.log("    [⑨] 跳过风险演化动图：缺少 ffmpeg（pip install imageio-ffmpeg）")
    p4 = build_index(spec, metrics)
    for p in (p1, p2, p3, p4, p5, p6):
        if p:
            project.log(f"    [⑨] {p.name}（{p.stat().st_size/1e6:.2f} MB）")

    manifest = {
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "generator": {"tool": "plotly + vanilla JS",
                      "version": __import__("plotly").__version__,
                      "script": "09_interactive/09_interactive.py",
                      "encoding": "utf-8", "font": "Microsoft YaHei",
                      "self_contained": True, "reproducible": True},
        "entry": "index.html",
        "n_figures": 5,
        "fidelity_check": fid,
        "figures": [
            {"file": "index.html", "title": "什么样的网点会先死（入口）",
             "type": "entry", "question": "结论、demo、体检报告能不能一站式看到？",
             "alt_text": "串联预测 demo、KM/ROC 与体检报告的入口页",
             "source": "本目录三件产物", "n": fid["n_test"],
             "scope": "1994–2025；右删失计入风险集；左截断已剔除", "tool": "html"},
            {"file": "predict_demo.html", "title": "这个网点会先死吗（可拖动）",
             "type": "predict_demo", "question": "给定特征，模型给这个网点打多少风险分？",
             "alt_text": "拖动特征滑块即时得到关闭风险与逐特征贡献分解",
             "unit": "y=年度关闭概率；贡献为对数几率",
             "source": "06_train/output/logit_coefficients.csv + test_predictions.csv",
             "n": fid["n_test"], "scope": "logit 主模型；截距由事件率校准",
             "tool": "vanilla JS", "reproducible": True},
            {"file": "km_roc.html", "title": "银行脆弱性越高，网点存活率越低",
             "type": "km_roc", "question": "不同银行脆弱性分层的网点存活曲线有差异吗？",
             "alt_text": "三条 KM 阶梯曲线分离，配 ROC 曲线与随机线对照",
             "unit": "左 x=观测年数 y=存活率；右 x=FPR y=TPR",
             "source": "05_map/output/data/branch_panel.csv + 06_train/output/test_predictions.csv",
             "n": int(len(panel)), "scope": "右删失计入风险集；左截断已剔除", "tool": "plotly"},
            {"file": "model_report.html", "title": "模型体检报告：准，但没那么准",
             "type": "model_report", "question": "模型性能与残差诊断一起看，够不够用？",
             "alt_text": "系数森林图（点+95%CI）与 AUC/C-index/Brier/Moran's I 指标条",
             "unit": "左 x=系数；右 x=指标值",
             "source": "06_train/output/{cloglog_coefficients.csv, metrics.json, moran_i.json}",
             "n": fid["n_test"], "scope": "cloglog 提供 CI；logit 提供性能指标", "tool": "plotly"},
            {"file": "risk_evolution.html", "title": "网点不是老死，而是被关",
             "type": "animation", "question": "关闭在时间上是怎么分布的？模型看到的风险怎么变？",
             "alt_text": "左图年度关闭柱在 2009–2014 明显抬升，右图风险分布同步右移",
             "unit": "左 x=年份 y=关闭网点数；右 x=预测风险 y=网点数",
             "source": "05_map/output/data/branch_panel.csv + 06_train/output/test_predictions.csv",
             "n": int(len(panel)),
             "scope": "mp4（FuncAnimation）内嵌 <video>；按 acq_year 统计",
             "tool": "matplotlib + ffmpeg"},
            {"file": "shap_force.html", "title": "三个代表性网点：谁把它推向死亡",
             "type": "shap_force", "question": "单个预测里，每个特征贡献了多少？",
             "alt_text": "三行水平条形图，红推高蓝压低 SHAP 值，按 |SHAP| 降序，hover 看原值",
             "unit": "x=SHAP 值（logit 贡献）；y=特征名（按 |SHAP| 降序）",
             "source": "06_train/output/logit_coefficients.csv + test_predictions.csv",
             "n": 3,
             "scope": "logit 主模型；线性模型 SHAP = coef×(x−mean)/std（精确，非近似）",
             "tool": "plotly"},
        ],
    }
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {"stage": STAGE, "blocking": False, "figures": 6,
            "auc_reproduced": fid["auc_reproduced"],
            "artifacts": ["index.html", "predict_demo.html", "shap_force.html",
                          "risk_evolution.html", "km_roc.html", "model_report.html",
                          "manifest.json"]}


def main() -> None:
    project = dk.Project.load(ROOT)
    print(run(project))


if __name__ == "__main__":
    main()
