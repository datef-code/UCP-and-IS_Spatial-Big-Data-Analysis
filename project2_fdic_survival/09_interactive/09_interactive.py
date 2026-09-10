# -*- coding: utf-8 -*-
"""09_interactive —— ⑨ 交互展示（扩展阶段，规范 §8.2 / §8.5 / §8.8）。

产品定位（`datakit/suggestions_for_projects_0908.md` §三）
--------------------------------------------------------
产品 2 是「**预测模型 / 可解释性产品型**」，受众 = 分析师 + 风控 / 决策者，
核心诉求是 **相信模型准（性能）、理解为什么（可解释）、能上手试（demo）**，
并且**必须标注边界**（风险预测 ≠ 因果 ≠ ROI）。

所以本阶段按「决策驾驶舱」组织，而不是教材（那是产品 6 的形态）：

| 产物 | 角色 |
| --- | --- |
| ``index.html`` | 决策驾驶舱：KPI + 王牌 demo 内嵌 + 年份效应 + 产品矩阵 + 护栏 + 复现 |
| ``predict_demo.html`` | 风险打分台（王牌）：拖滑块 → 风险 + 贡献分解 + 单因素敏感性 |
| ``shap_force.html`` | 可解释性：全局 SHAP 重要性 + 三个真实样本分解 |
| ``model_report.html`` | 模型体检：年份效应 + 因子森林（含 95% CI）+ 指标 + Moran's I |
| ``guardrails.html`` | 边界与止损：8 条限制 + 5 条止损 + 正确/错误用法对照 |
| ``km_roc.html`` | 生存与区分度（CSV 在时出交互版，不在时降级为上游静态图） |
| ``risk_evolution.html`` | 风险演化动图（需 CSV + ffmpeg，缺则保留既有产物） |

代码为什么拆成 3 个模块
----------------------
* ``studio_data.py`` —— 数据层 + 降级策略（**本阶段原本缺 CSV 会直接崩溃，这是要修的头号问题**）；
* ``studio_ui.py``   —— 设计令牌 + 组件（风控看板风格：KPI / 护栏 / 风险条）；
* ``studio_figs.py`` —— 交互件；
* 本文件              —— 编排入口（规范要求与目录同名）+ logit 主模型路径 + 动图。

硬约束：本阶段**只读**上游 output/，不重训模型、不回写上游。
"""
from __future__ import annotations

import datetime as _dt
import json
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

sys.path.insert(0, str(Path(__file__).resolve().parent))      # 阶段由 importlib 按文件路径加载

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import datakit as dk
import studio_data as sd
import studio_figs as sfg
import studio_ui as ui

STAGE = "09_interactive"
ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "output"

FONT = ui.FONT
GRID = "#e2e8f0"
OK_ITO = ["#1d4ed8", "#ea580c", "#0f766e", "#6d28d9", "#a16207"]

NUMERIC = ["age", "log_depsumbr", "neighbor_count", "lat", "lng", "bank_closed_rate"]
CATEG = ["year", "BKCLASS", "fragility_tier"]
LABEL = {"age": ("网点年龄", "年"), "log_depsumbr": ("存款规模（对数）", "log"),
         "neighbor_count": ("同格网点数（竞争强度）", "个"), "lat": ("纬度", "°"),
         "lng": ("经度", "°"), "bank_closed_rate": ("所属银行历史关闭率", "")}


def _sigmoid(z):
    return 1.0 / (1.0 + np.exp(-z))


def _auc(y, s):
    y = np.asarray(y, float)
    order = np.argsort(s)
    ranks = np.empty(len(s), float)
    ranks[order] = np.arange(1, len(s) + 1)
    df = pd.DataFrame({"s": s, "r": ranks})
    ranks = df.groupby("s")["r"].transform("mean").to_numpy()
    n1, n0 = y.sum(), (1 - y).sum()
    return float((ranks[y == 1].sum() - n1 * (n1 + 1) / 2) / (n1 * n0))


# --------------------------------------------------------------------------- #
# logit 主模型路径（需要 logit_coefficients.csv + test_predictions.csv）
# --------------------------------------------------------------------------- #
def build_logit_spec(proj_root: Path) -> tuple[dict, dict]:
    """从样本级 CSV 还原 logit 主模型，并做**保真度自检**。

    截距为什么是校准出来的：模型产物未保存截距（只导出了 feature/coef），
    因此用测试集事件率反解（二分求解使平均预测概率 = 观测事件率）。
    这个方法自洽，因为 AUC 与排序无关，校准只影响概率绝对值 —— 页面已显式标注。
    """
    coef = pd.read_csv(proj_root / "06_train" / "output" / "logit_coefficients.csv")
    test = pd.read_csv(proj_root / "06_train" / "output" / "test_predictions.csv")
    beta = dict(zip(coef.feature, coef.coef))

    stats = {}
    for c in NUMERIC:
        v = pd.to_numeric(test[c], errors="coerce")
        stats[c] = {"mean": float(v.mean()), "std": float(v.std(ddof=0)) or 1.0,
                    "min": float(v.min()), "max": float(v.max()), "p50": float(v.median())}

    levels = {}
    for c in CATEG:
        vals = sorted(str(v) for v in test[c].dropna().unique())
        present = {f.split("_", 1)[1] for f in beta if f.startswith(f"{c}_")}
        levels[c] = {"values": vals, "reference": sorted(set(vals) - present)}

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
    metrics = json.loads(
        (proj_root / "06_train" / "output" / "metrics.json").read_text(encoding="utf-8"))
    auc_ref = metrics["test"]["auc"]

    spec = {
        "model": "logit_discrete_time（sklearn，主模型）",
        "link": "logit",
        "source": "06_train/output/logit_coefficients.csv + test_predictions.csv",
        "intercept": intercept,
        "numeric": {c: {**stats[c], "coef": float(beta.get(c, 0.0))} for c in NUMERIC},
        "categorical": {c: {**levels[c], "coef": {v: float(beta.get(f"{c}_{v}", 0.0))
                                                  for v in levels[c]["values"]}}
                        for c in CATEG},
        "label": {c: list(LABEL.get(c, (c, ""))) for c in NUMERIC},
        "fidelity": {
            "auc_reproduced": round(auc_repro, 4),
            "auc_reference": round(auc_ref, 4),
            "abs_diff": round(abs(auc_repro - auc_ref), 4),
            "n_test": int(len(test)), "event_rate": round(float(y.mean()), 6),
            "note": ("截距由测试集事件率校准（产物未保存截距）；"
                     "AUC 复现度用于证明本 demo 与主模型一致"),
        },
    }
    return spec, metrics


def build_logit_demo(spec: dict, out: Path) -> Path:
    """logit 主模型的预测 demo（z 标准化 + 校准截距），内含保真度自检。"""
    fid = spec["fidelity"]
    payload = json.dumps(spec, ensure_ascii=False)
    js = """
    var SPEC = __PAYLOAD__;
    var N = SPEC.numeric, C = SPEC.categorical, L = SPEC.label;
    var box = document.getElementById('inputs');
    var state = {};
    function fmt(v,d){return Number(v).toFixed(d===undefined?2:d);}
    function addRange(key){
      var s = N[key], nm = (L[key]||[key])[0], unit = (L[key]||[key,''])[1];
      var step = Math.max((s.max - s.min)/300, 1e-6);
      var w = document.createElement('div'); w.className='f';
      w.innerHTML = '<label><span>' + nm + (unit?'<i>（'+unit+'）</i>':'') +
        '</span><b id="v_'+key+'"></b></label>' +
        '<input type="range" id="i_'+key+'" min="'+s.min+'" max="'+s.max+'" step="'+step+
        '" value="'+s.p50+'"><div class="sub"><span>系数 '+s.coef.toPrecision(4)+
        '　z=(x−mean)/std</span></div>';
      box.appendChild(w); state[key] = s.p50;
      w.querySelector('input').addEventListener('input', function(e){
        state[key] = parseFloat(e.target.value); paint(); });
    }
    function addSelect(key, label){
      var c = C[key];
      var w = document.createElement('div'); w.className='f';
      w.innerHTML = '<label><span>'+label+'</span><b id="v_'+key+'"></b></label>'+
        '<select id="i_'+key+'">' + c.values.map(function(v){
          return '<option value="'+v+'">'+v+'</option>';}).join('') + '</select>'+
        '<div class="sub"><span>参照档：'+(c.reference.join?c.reference.join(', '):c.reference)+
        '（系数 = 0）</span></div>';
      box.appendChild(w);
      state[key] = c.values.indexOf('2005')>=0 ? '2005' : c.values[0];
      w.querySelector('select').value = state[key];
      w.querySelector('select').addEventListener('change', function(e){
        state[key] = e.target.value; paint(); });
    }
    ['age','log_depsumbr','neighbor_count','bank_closed_rate','lat','lng'].forEach(addRange);
    addSelect('year','日历年'); addSelect('BKCLASS','银行类别');
    addSelect('fragility_tier','银行脆弱性分层');
    function parts(){
      var out=[];
      for (var k in N){ var s=N[k];
        out.push({name:(L[k]||[k])[0], v: s.coef*(state[k]-s.mean)/s.std}); }
      for (var c in C) out.push({name:c+' = '+state[c], v:(C[c].coef[state[c]]||0)});
      return out;
    }
    function paint(){
      for (var k in N) document.getElementById('v_'+k).textContent = fmt(state[k],2);
      for (var c in C) document.getElementById('v_'+c).textContent = state[c];
      var cs = parts(), eta = SPEC.intercept;
      cs.forEach(function(a){ eta += a.v; });
      var p = 1/(1+Math.exp(-eta));
      document.getElementById('p').textContent = (p*100).toFixed(2)+'%';
      document.getElementById('eta').textContent = eta.toFixed(3);
      var bar = document.getElementById('bar');
      bar.style.width = Math.min(100, Math.pow(p,0.45)*100).toFixed(1)+'%';
      bar.style.background = p > 0.1378 ? '#ea580c' : '#1d4ed8';
      document.getElementById('cmp').textContent =
        '测试集平均风险 13.78% —— 当前为平均水平的 ' + (p/0.1378).toFixed(2) + ' 倍';
      document.getElementById('tag').textContent =
        p>=0.3?'高危':(p>=0.1?'偏高':(p>=0.03?'中等':'低危'));
      document.getElementById('tag').className = 'tagbd ' +
        (p>=0.3?'hi':(p>=0.1?'md':'lo'));
      var all = [{name:'截距（基线）', v:SPEC.intercept}].concat(
        cs.slice().sort(function(a,b){return Math.abs(b.v)-Math.abs(a.v);}));
      var maxAbs = Math.max.apply(null, all.map(function(a){return Math.abs(a.v);}).concat([0.5]));
      document.getElementById('wf').innerHTML = all.map(function(a){
        var w = Math.max(Math.abs(a.v)/maxAbs*48, 0.5), pos = a.v>=0;
        return '<div class="row"><div class="nm">'+a.name+'</div><div class="trk"><i class="'+
          (pos?'pos':'neg')+'" style="'+(pos?'left:50%;width:':'right:50%;width:')+
          w.toFixed(2)+'%"></i></div><div class="val">'+(pos?'+':'')+fmt(a.v,3)+'</div></div>';
      }).join('');
    }
    paint();
    """.replace("__PAYLOAD__", payload)

    body = f"""
    <p>拖动下面的特征，右侧<b>实时</b>算出该网点下一年的关闭风险，并拆出每个特征
    贡献了多少。所有计算在浏览器里完成，<b>不联网、不上传</b>。</p>
    <div class="badges">
      <span class="badge b">模型：{spec['model']}</span>
      <span class="badge">来源：{spec['source']}</span>
      <span class="badge r">风险预测，非因果</span>
    </div>
    <div class="grid2">
      <div class="panel"><h3>网点特征</h3><div id="inputs"></div></div>
      <div>
        <div class="panel">
          <h3>年度关闭风险</h3>
          <div class="big"><span id="p">–</span><span class="tagbd" id="tag">–</span></div>
          <div class="bar"><i id="bar" style="width:0%"></i></div>
          <div class="hint" id="cmp"></div>
          <div class="hint">线性预测器 η = <code id="eta">–</code>
          　|　logit 连接：P = 1/(1+e^(−η))</div>
        </div>
        <div class="panel" style="margin-top:16px">
          <h3>这个分数是怎么来的（对数几率贡献分解）</h3>
          <div class="wf" id="wf"></div>
          <div class="hint">线性模型的贡献分解即 SHAP 值：
          <span style="color:#ea580c">橙＝推高风险</span>、
          <span style="color:#1d4ed8">蓝＝压低风险</span>，按 |贡献| 降序。</div>
        </div>
      </div>
    </div>
    <div class="danger"><b>边界：这是风险预测，不是因果，也不是 ROI 工具。</b>
      <ul><li>拖动滑块<b>不会</b>改变网点的真实命运 —— 它只展示模型怎么打分。</li>
      <li>不承诺干预阈值、不承诺 ROI（成本参数缺失）。</li></ul></div>
    <div class="note"><b>保真度自检</b>：本页复现的测试集 AUC =
      <code>{fid['auc_reproduced']}</code>，与
      <code>06_train/output/metrics.json</code> 的
      <code>{fid['auc_reference']}</code> 相差 <code>{fid['abs_diff']}</code>
      （n={fid['n_test']:,}，事件率 {fid['event_rate']:.2%}）。
      模型产物未保存截距，截距由事件率校准；系数与标准化参数全部来自上游产物。</div>
    """
    css = """
    .badges{margin:12px 0 18px}
    .grid2{display:grid;grid-template-columns:340px 1fr;gap:22px;align-items:start}
    @media(max-width:960px){.grid2{grid-template-columns:1fr}}
    .panel{border:1px solid var(--line);border-radius:var(--radius);padding:16px 18px;
      background:var(--bg);box-shadow:var(--shadow)}
    .panel h3{margin:0 0 12px;font-size:14.5px}
    .f{margin-bottom:15px}
    .f label{display:flex;justify-content:space-between;align-items:baseline;
      font-size:12.5px;color:var(--sub);gap:8px}
    .f label i{font-style:normal;font-size:11px;color:var(--faint)}
    .f label b{color:var(--ink);font-variant-numeric:tabular-nums;font-size:13px}
    .f .sub{font-size:10.5px;color:var(--faint);margin-top:2px}
    input[type=range]{width:100%;accent-color:#1d4ed8;margin:4px 0 0}
    select{width:100%;padding:6px 8px;border:1px solid var(--line);border-radius:7px;
      font-size:12.5px;background:var(--bg);color:var(--ink);font-family:inherit;margin-top:4px}
    .big{display:flex;align-items:baseline;gap:12px}
    .big #p{font-size:44px;font-weight:750;letter-spacing:-1.5px;
      font-variant-numeric:tabular-nums;line-height:1.1}
    .tagbd{font-size:12px;padding:3px 10px;border-radius:999px;font-weight:700}
    .tagbd.hi{background:var(--danger-soft);color:var(--danger);border:1px solid var(--danger)}
    .tagbd.md{background:var(--risk-soft);color:var(--risk);border:1px solid var(--risk)}
    .tagbd.lo{background:var(--ok-soft);color:var(--ok);border:1px solid var(--ok)}
    .bar{height:11px;background:var(--soft-2);border-radius:999px;overflow:hidden;margin:10px 0 6px}
    .bar i{display:block;height:100%;border-radius:999px;transition:width .18s,background .18s}
    .hint{font-size:12px;color:var(--sub);margin-top:4px}
    .wf{margin-top:8px}
    .row{display:grid;grid-template-columns:170px 1fr 96px;gap:8px;align-items:center;
      font-size:12px;margin:4px 0}
    .row .nm{overflow:hidden;text-overflow:ellipsis;white-space:nowrap;color:var(--ink-2)}
    .trk{position:relative;height:15px;background:var(--soft-2);border-radius:3px}
    .trk i{position:absolute;top:2px;height:11px;border-radius:2px}
    .trk i.pos{background:#ea580c} .trk i.neg{background:#1d4ed8}
    .val{text-align:right;font-variant-numeric:tabular-nums;color:var(--sub);font-size:11.5px}
    """
    html = ui.page("风险打分台 · 这个网点明年会关闭吗", body,
                   subtitle="logit 主模型（含测试集 AUC 保真度自检）。拖动特征 → 实时风险 + 贡献分解。",
                   extra_css=css, extra_js=js, active_nav="王牌 demo")
    p = out / "predict_demo.html"
    p.write_text(html, encoding="utf-8")
    return p


# --------------------------------------------------------------------------- #
# KM + ROC（需要样本级 CSV）
# --------------------------------------------------------------------------- #
def _km(duration: np.ndarray, event: np.ndarray):
    d = pd.DataFrame({"t": duration, "e": event}).dropna()
    d = d[d.t > 0]
    g = d.groupby("t").agg(events=("e", "sum"), n=("e", "size")).reset_index().sort_values("t")
    n_total = len(d)
    at_risk = n_total - np.concatenate([[0], g.n.cumsum().to_numpy()[:-1]])
    s = np.cumprod(1 - g.events.to_numpy() / at_risk)
    return g.t.to_numpy(), s, at_risk, g.events.to_numpy(), n_total


def fig_km_roc(panel: pd.DataFrame, test: pd.DataFrame, metrics: dict) -> go.Figure:
    frag = None
    frag_path = ROOT / "05_map" / "output" / "data" / "bank_fragility.csv"
    if frag_path.exists():
        f = pd.read_csv(frag_path)
        col = next((c for c in ("fragility_tier", "tier", "level") if c in f.columns), None)
        if col and "CERT" in f.columns:
            frag = dict(zip(f.CERT, f[col]))

    d = panel.copy()
    d["grp"] = d.CERT.map(frag) if frag else d["BKCLASS"].astype(str)
    if "left_truncated" in d.columns:
        d = d[d.left_truncated != 1]
    d = d.dropna(subset=["duration", "event"])
    if d["event"].dtype == object:
        d["event"] = d["event"].astype(str).str.lower().isin(["closed", "1", "true"]).astype(int)
    d["event"] = pd.to_numeric(d["event"], errors="coerce").fillna(0).astype(int)
    groups = sorted(d.grp.dropna().unique())[:3]

    fig = make_subplots(rows=1, cols=2, column_widths=[0.56, 0.44],
                        subplot_titles=("Kaplan–Meier：银行脆弱性越高，网点存活率越低",
                                        f"ROC：AUC={metrics['test']['auc']:.3f}（同口径可比）"))
    for i, g in enumerate(groups):
        sub = d[d.grp == g]
        t, s, at_risk, ev, n = _km(sub.duration.to_numpy(float), sub.event.to_numpy(int))
        fig.add_trace(go.Scatter(
            x=np.concatenate([[0], t]), y=np.concatenate([[1], s]), mode="lines", name=str(g),
            line=dict(shape="hv", color=OK_ITO[i % len(OK_ITO)], width=2.4),
            customdata=np.concatenate([[n], at_risk]),
            hovertemplate="第 %{x:.0f} 年<br>存活率 %{y:.3f}<br>at-risk %{customdata}"
                          "<extra>" + str(g) + "</extra>"), row=1, col=1)

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

    fig.update_layout(**sfg._base(
        f"<b>谁先死、什么时候死，模型分得开吗</b><br>"
        f"<sub>KM：按银行脆弱性分层，右删失计入风险集、左截断已剔除，n={len(d):,}；"
        f"ROC：测试集 n={metrics['test']['n']:,}，AUC {metrics['test']['auc']:.3f} / "
        f"Brier {metrics['test']['brier']:.3f}</sub>", height=520,
        showlegend=True,
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1,
                    bgcolor="rgba(0,0,0,0)")))
    fig.update_xaxes(title_text="观测年数", row=1, col=1, showgrid=False)
    fig.update_yaxes(title_text="存活率", row=1, col=1, gridcolor=GRID, range=[0, 1])
    fig.update_xaxes(title_text="假阳性率 FPR", row=1, col=2, showgrid=False)
    fig.update_yaxes(title_text="真阳性率 TPR", row=1, col=2, gridcolor=GRID)
    return sfg._style_axes(fig)


# --------------------------------------------------------------------------- #
# 风险演化动图（需要 CSV + ffmpeg）
# --------------------------------------------------------------------------- #
def _mpl_style():
    import matplotlib as mpl
    mpl.rcParams.update({
        "font.sans-serif": ["Microsoft YaHei", "Noto Sans CJK SC", "SimHei", "DejaVu Sans"],
        "font.family": "sans-serif", "axes.unicode_minus": False,
        "figure.facecolor": "#0B1020", "axes.facecolor": "#0B1020",
        "savefig.facecolor": "#0B1020", "text.color": "#F3F4F6",
        "axes.labelcolor": "#D1D5DB", "xtick.color": "#9CA3AF",
        "ytick.color": "#9CA3AF", "axes.edgecolor": "#374151",
    })


def anim_risk_evolution(panel: pd.DataFrame, test: pd.DataFrame) -> tuple[Path, Path]:
    """年度演化动图：左＝每年实际关闭数，右＝模型眼中该年风险的分布。

    为什么值得做：本课题最反直觉的发现是「网点不是老死而是被关」——
    **什么时候**比**多老**更重要。静态图看不出这一点随时间的推进，动图能。
    """
    import matplotlib.pyplot as plt

    crisis = sd.CRISIS
    _mpl_style()
    d = panel.dropna(subset=["acq_year"]).copy()
    d["y"] = pd.to_numeric(d.acq_year, errors="coerce")
    d = d[d.y.between(1994, 2025)]
    d["y"] = d.y.astype(int)
    years = list(range(1994, 2026))
    counts = d.groupby("y").size().reindex(years, fill_value=0).to_numpy(float)
    ymax = float(counts.max()) * 1.25 + 1

    t = test.copy()
    t["y"] = pd.to_numeric(t.year, errors="coerce")
    t = t[t.y.between(1994, 2025)]
    by_year = {int(y): g.risk.to_numpy(float) for y, g in t.groupby("y")}
    bins = np.linspace(0, float(t.risk.max()) if len(t) else 1.0, 34)

    fig, (ax, bx) = plt.subplots(1, 2, figsize=(12.8, 5.8),
                                 gridspec_kw={"width_ratios": [1.15, 1]})
    fig.subplots_adjust(left=0.07, right=0.97, top=0.85, bottom=0.13, wspace=0.22)

    # 放慢：每年 4 个子帧、fps=6 → 每年 0.67 s、全程 21 s
    SUB, FPS = 4, 6
    n_total = len(years) * SUB

    def draw(i):
        yi, sub = divmod(i, SUB)
        frac = (sub + 1) / SUB
        y = years[yi]
        ax.clear(); bx.clear()
        in_win = crisis[0] <= y <= crisis[1]

        prev = counts[yi - 1] if yi else 0.0
        shown = prev + (counts[yi] - prev) * frac
        ax.bar(years, counts,
               color=["#ea580c" if (crisis[0] <= yy <= crisis[1]) else "#374151" for yy in years],
               width=0.82)
        if yi:
            ax.bar(years[:yi], counts[:yi],
                   color=["#fbbf24" if (crisis[0] <= yy <= crisis[1]) else "#1d4ed8"
                          for yy in years[:yi]], width=0.82)
        ax.bar([y], [shown], color="#fbbf24" if in_win else "#1d4ed8", width=0.82,
               alpha=0.55 + 0.45 * frac)
        ax.set_xlim(1993.2, 2025.8); ax.set_ylim(0, ymax)
        ax.set_xlabel("年份", fontsize=12); ax.set_ylabel("当年关闭网点数", fontsize=12)
        ax.grid(axis="y", color="#1F2937", linewidth=0.8)
        ax.tick_params(labelsize=11)
        ax.set_title(f"{y}　当年关闭 {int(round(shown)):,} 家"
                     + ("　← 危机后整合窗口" if in_win else ""),
                     color="#fbbf24" if in_win else "#F3F4F6", fontsize=16, pad=12, loc="left")

        v = by_year.get(y)
        if v is None or len(v) == 0:
            bx.text(0.5, 0.5, "该年测试集无样本", ha="center", va="center",
                    transform=bx.transAxes, color="#4B5563", fontsize=13)
        else:
            bx.hist(v, bins=bins, color="#1d4ed8", alpha=0.30 + 0.55 * frac)
            if frac > 0.5:
                bx.axvline(float(np.median(v)), color="#fbbf24", linewidth=2.6)
                bx.text(0.03, 0.94, f"中位风险 {np.median(v):.3f}",
                        transform=bx.transAxes, color="#fbbf24", fontsize=14)
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
                  f"橙/琥珀＝{crisis[0]}–{crisis[1]} 危机后整合窗口，"
                  f"峰值 {peak:,} 家（{peak_y} 年）。"
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
    project.log(f"[{STAGE}] ⑨ 交互展示（决策驾驶舱 + 打分台 + 可解释性 + 体检 + 边界）")
    OUT.mkdir(parents=True, exist_ok=True)

    facts = sd.load_facts(ROOT)
    status = sd.csv_status(ROOT)
    static_figs = sd.collect_static_figs(ROOT, OUT / "assets" / "fig")
    ui.write_plotly_vendor(OUT)
    project.log(f"    [⑨] 静态配图 {len(static_figs)} 张（复制自 07_visualize）")

    if status["missing"]:
        project.log(f"    [⑨] 缺样本级 CSV（{len(status['missing'])}/{len(status['missing']) + len(status['present'])}）"
                    f"：{', '.join(status['missing'])} → 依赖它们的面板降级")

    # ---- 打分台：优先 logit 主模型（有保真度自检），否则用 cloglog 真系数 ----
    if status["demo_ready"]:
        spec, metrics = build_logit_spec(ROOT)
        fid = spec["fidelity"]
        project.log(f"    [⑨] logit 保真度自检：AUC 复现 {fid['auc_reproduced']} "
                    f"vs 产物 {fid['auc_reference']}（差 {fid['abs_diff']}）")
        if fid["abs_diff"] > 0.02:
            raise RuntimeError(f"预测 demo 与主模型不一致（AUC 差 {fid['abs_diff']}），拒绝产出")
        facts["metrics"] = metrics
        facts["test"] = metrics.get("test", {})
        p_demo = build_logit_demo(spec, OUT)
        demo_model = "logit 主模型（含 AUC 保真度自检）"
    else:
        spec = sfg.build_cloglog_spec(facts)
        p_demo = sfg.build_predict_demo(spec, facts, OUT)
        demo_model = "cloglog 模型（样本级 CSV 不入库，故用入库的完整系数表）"

    # ---- KM / ROC：有 CSV 出交互版，否则降级 ----
    km_interactive = False
    if (ROOT / "05_map" / "output" / "data" / "branch_panel.csv").exists() \
            and (ROOT / "06_train" / "output" / "test_predictions.csv").exists():
        panel = pd.read_csv(ROOT / "05_map" / "output" / "data" / "branch_panel.csv")
        test = pd.read_csv(ROOT / "06_train" / "output" / "test_predictions.csv")
        fig = fig_km_roc(panel, test, facts["metrics"])
        body = (sfg._div(fig, 520)
                + ui.callout("note", "读图要点",
                             "<ul><li>KM 曲线<b>尾部（> 25 年）</b>风险集已很小，置信带很宽。</li>"
                             "<li>AUC / C-index 依赖事件率与抽样口径，<b>跨数据集比较无效</b>。</li>"
                             "<li>右删失 47%：近半数网点 2025 年仍存活。</li></ul>"))
        p_km = OUT / "km_roc.html"
        p_km.write_text(ui.page("生存与区分度 · 谁先死，模型分得开吗", body,
                                subtitle="Kaplan–Meier（按银行脆弱性分层，hover 看 at-risk）+ 测试集 ROC。",
                                with_plotly=True, active_nav="生存分析"), encoding="utf-8")
        km_interactive = True
    else:
        p_km = sfg.build_km_roc(facts, static_figs, OUT)

    p_shap = sfg.build_shap_force(facts, static_figs, OUT)
    p_rep = sfg.build_model_report(facts, static_figs, OUT)
    p_guard = sfg.build_guardrails(facts, OUT)

    # ---- 演化动图：需 CSV + ffmpeg，缺则保留既有产物 ----
    evo_html = OUT / "risk_evolution.html"
    if (ROOT / "05_map" / "output" / "data" / "branch_panel.csv").exists() \
            and (ROOT / "06_train" / "output" / "test_predictions.csv").exists() \
            and dk.ffmpeg_available():
        panel = pd.read_csv(ROOT / "05_map" / "output" / "data" / "branch_panel.csv")
        test = pd.read_csv(ROOT / "06_train" / "output" / "test_predictions.csv")
        mp4, evo_html = anim_risk_evolution(panel, test)
        project.log(f"    [⑨] {evo_html.name}（mp4 {mp4.stat().st_size / 1e6:.1f} MB → "
                    f"内嵌 {evo_html.stat().st_size / 1e6:.1f} MB）")
    else:
        project.log("    [⑨] 跳过演化动图（需 branch_panel.csv + test_predictions.csv + ffmpeg）；"
                    + ("保留既有产物" if evo_html.exists() else "当前无产物"))
    evolution = evo_html.exists()

    p_deck = sfg.build_deck(facts, OUT, evolution=evolution, demo_model=demo_model)
    project.log(f"    [⑨] index.html（{p_deck.stat().st_size / 1e3:.0f} KB）")
    for p in (p_demo, p_shap, p_rep, p_guard, p_km):
        project.log(f"    [⑨] {p.name}（{p.stat().st_size / 1e3:.0f} KB）")

    t = facts["test"]
    figures = [
        {"file": "index.html", "title": "什么样的网点会先死（决策驾驶舱）", "type": "entry",
         "question": "模型值不值得信、能怎么用、边界在哪？",
         "alt_text": "KPI + 王牌 demo 内嵌 + 年份效应 + 产品矩阵 + 护栏 + 复现",
         "source": "本目录各产物 + 06_train/output + 08_conclude/output",
         "n": int(t.get("n", 0)), "scope": "1994–2025；右删失计入风险集；左截断已剔除",
         "tool": "html + plotly"},
        {"file": "predict_demo.html", "title": "风险打分台（王牌 demo）", "type": "predict_demo",
         "question": "给定特征，这个网点明年关闭风险多少？",
         "alt_text": "拖滑块 → 实时风险 + 逐特征贡献分解 + 单因素敏感性 tornado",
         "unit": "y = 年度关闭概率；贡献为线性预测器尺度",
         "source": spec.get("source", ""), "n": int(t.get("n", 0)),
         "scope": spec.get("model", ""), "tool": "vanilla JS", "reproducible": True},
        {"file": "shap_force.html", "title": "可解释性：模型凭什么说它风险高",
         "type": "shap_explorer",
         "question": "全局哪些特征在驱动？单个预测里每个特征贡献多少？",
         "alt_text": "SHAP 重要性条形（对数轴）+ 三个真实样本的逐特征分解，红推高蓝压低",
         "unit": "x = mean |SHAP| / SHAP 值（logit 贡献）",
         "source": "06_train/output/train_report.md + 09_interactive/output/shap_force.json",
         "n": len(facts["shap_imp"]), "scope": "线性模型 SHAP = coef×(x−mean)/std（精确）",
         "tool": "plotly"},
        {"file": "model_report.html", "title": "模型体检报告：准，但没那么准",
         "type": "model_report",
         "question": "模型准不准、残差里还有没有东西？",
         "alt_text": "年份效应（带 95% CI）+ 非年份因子森林 + 性能指标 + 残差 Moran's I",
         "unit": "左 x = 年份 / 系数；右为指标卡",
         "source": "06_train/output/{cloglog_summary.txt, metrics.json, moran_i.json}",
         "n": int(t.get("n", 0)),
         "scope": "cloglog 提供 95% CI；logit 提供性能指标", "tool": "plotly"},
        {"file": "guardrails.html", "title": "边界与止损：什么情况下不能用",
         "type": "guardrails",
         "question": "这个模型在什么情况下不该被使用？",
         "alt_text": f"{len(facts['limits'])} 条已知限制 + {len(facts['stops'])} 条止损条件 + 正确/错误用法对照",
         "source": "08_conclude/output/conclusion_report.json",
         "n": len(facts["limits"]) + len(facts["stops"]),
         "scope": "风险预测，非因果；不承诺干预阈值与 ROI", "tool": "html"},
        {"file": "km_roc.html", "title": "生存与区分度：谁先死", "type": "km_roc",
         "question": "不同银行脆弱性分层的网点存活曲线有差异吗？",
         "alt_text": "KM 分层曲线（hover 看 at-risk）+ ROC；降级时为上游静态图",
         "unit": "左 x=观测年数 y=存活率；右 x=FPR y=TPR",
         "source": "05_map/output/data/branch_panel.csv + 07_visualize 静态图",
         "n": int(facts["key"].get("branches", 0)),
         "scope": "右删失计入风险集；左截断已剔除", "tool": "plotly",
         "degraded": not km_interactive},
    ]
    if evolution:
        figures.append({
            "file": "risk_evolution.html", "title": "网点不是老死，而是被关", "type": "animation",
            "question": "关闭在时间上怎么分布？模型看到的风险怎么变？",
            "alt_text": "左图年度关闭柱在 2009–2014 明显抬升，右图风险分布同步右移",
            "unit": "左 x=年份 y=关闭网点数；右 x=预测风险 y=网点数",
            "source": "05_map/output/data/branch_panel.csv + 06_train/output/test_predictions.csv",
            "n": int(facts["key"].get("branches", 0)),
            "scope": "mp4（FuncAnimation）内嵌 <video>；按 acq_year 统计",
            "tool": "matplotlib + ffmpeg"})

    manifest = {
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "generator": {"tool": "plotly + vanilla JS",
                      "script": "09_interactive/09_interactive.py",
                      "modules": ["studio_data.py", "studio_ui.py", "studio_figs.py"],
                      "encoding": "utf-8", "font": "Microsoft YaHei",
                      "self_contained": True, "reproducible": True,
                      "note": "plotly.js 与配图集中在 output/assets/；output/ 整体可拷走、离线可开"},
        "entry": "index.html", "n_figures": len(figures),
        "degraded": {"km_roc": not km_interactive, "predict_demo": not status["demo_ready"],
                     "missing_csv": status["missing"],
                     "reason": "样本级 CSV 受仓库根 .gitignore 的 */*/*/*.csv 约束，不入库"},
        "figures": figures,
    }
    if "fidelity" in spec:
        manifest["fidelity_check"] = spec["fidelity"]
    (OUT / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    return {"stage": STAGE, "blocking": False, "figures": len(figures),
            "demo_model": demo_model,
            "artifacts": ["index.html", "predict_demo.html", "shap_force.html",
                          "model_report.html", "guardrails.html", "km_roc.html",
                          "manifest.json"]}


def main() -> None:
    project = dk.Project.load(ROOT)
    print(run(project))


if __name__ == "__main__":
    main()
