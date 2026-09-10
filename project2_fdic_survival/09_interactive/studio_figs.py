# -*- coding: utf-8 -*-
"""09_interactive · 交互件（产品 2 = 预测模型 / 可解释性产品型）。

产物与各自回答的问题
--------------------
| 产物 | 回答什么 | 关键交互 |
| --- | --- | --- |
| ``index.html`` | 这模型值不值得信、能怎么用、边界在哪？ | 决策驾驶舱：KPI + 王牌 demo 内嵌 + 年份效应 + 产品矩阵 + 护栏 + 复现 |
| ``predict_demo.html`` | 给定特征，这个网点明年关闭风险多少？ | 拖滑块 / 选档位 → 实时风险 + 贡献分解 + **单因素敏感性 tornado** |
| ``shap_force.html`` | 单个预测为什么这样判？ | SHAP 重要性（对数轴）+ 三个真实样本分解，可切「只看推高 / 只看压低」 |
| ``model_report.html`` | 模型准不准、残差有没有漏东西？ | 年份效应（含 95% CI）+ 非年份因子森林 + 指标 + Moran's I |
| ``guardrails.html`` | 什么情况下**不能**用？ | 8 条已知限制 + 5 条止损条件 + 正确/错误用法对照 |
| ``km_roc.html`` | 谁先死、模型分得开吗？ | CSV 在时出真 KM/ROC；不在时降级为上游静态图 + 说明 |

为什么把「年份效应」单独拎出来做一张图
--------------------------------------
本课题最反直觉的发现是「**什么时候**比**多老**更重要」。旧版把年份虚变量和其它
因子混在一张 top-18 森林图里，这个结论被淹没了。这里把年份做成一张带 CI 的
时间序列图，危机后整合窗口（2009–2014）的抬升一眼可见。
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import plotly.graph_objects as go
from plotly.subplots import make_subplots

import studio_data as sd
import studio_ui as ui

GRID = "#e2e8f0"
FONT = ui.FONT
TICK = "#64748b"
POS = "#ea580c"        # 推高风险（缩短寿命）
NEG = "#1d4ed8"        # 压低风险（延长寿命）
CRISIS_COLOR = "#b91c1c"


# --------------------------------------------------------------------------- #
# plotly 小工具
# --------------------------------------------------------------------------- #
def _div(fig: go.Figure, height: int = 480) -> str:
    return fig.to_html(include_plotlyjs=False, full_html=False,
                       config={"displaylogo": False, "responsive": True},
                       default_height=height)


def _base(title: str = "", height: int = 480, **kw) -> dict:
    lay = dict(font=dict(family=FONT, size=12.5, color=TICK),
               paper_bgcolor="#ffffff", plot_bgcolor="#ffffff",
               margin=dict(l=80, r=30, t=100 if title else 40, b=70),
               height=height, hovermode="closest", showlegend=False)
    if title:
        lay["title"] = dict(text=title, x=0.01, xanchor="left",
                            font=dict(size=15, color="#0f172a"))
    lay.update(kw)
    return lay


def _style_axes(fig: go.Figure, grid: str = GRID) -> go.Figure:
    """用 ``title_font=`` 而不是 ``title=dict(font=...)`` —— 后者会把轴标题整个替换掉。"""
    fig.update_xaxes(gridcolor=grid, zerolinecolor=grid, linecolor=grid,
                     tickfont=dict(size=11.5, color=TICK),
                     title_font=dict(size=12.5, color=TICK))
    fig.update_yaxes(gridcolor=grid, zerolinecolor=grid, linecolor=grid,
                     tickfont=dict(size=11.5, color=TICK),
                     title_font=dict(size=12.5, color=TICK))
    return fig


def _year_coefs(facts: dict) -> list[dict]:
    """年份虚变量（1995–2015 有真实估计；2016+ 因完美分离已剔除）。"""
    out = []
    for c in facts["coefs"]:
        lab = sd.coef_label(c["name"])
        if c["name"].startswith("C(year)"):
            try:
                out.append({"year": int(lab), **c, "label": lab})
            except ValueError:
                continue
    return sorted(out, key=lambda r: r["year"])


def _factor_coefs(facts: dict) -> list[dict]:
    """非年份、非截距的因子（森林图用）。"""
    out = []
    for c in facts["coefs"]:
        if c["name"] == "Intercept" or c["name"].startswith("C(year)"):
            continue
        out.append({"label": sd.coef_label(c["name"]),
                    "kind": sd.coef_kind(c["name"]), **c})
    return out


# --------------------------------------------------------------------------- #
# ① 年份效应（本课题的结论主图）
# --------------------------------------------------------------------------- #
def fig_year_effect(facts: dict) -> go.Figure:
    ys = _year_coefs(facts)
    if not ys:
        return go.Figure()
    x = [r["year"] for r in ys]
    coef = np.array([r["coef"] for r in ys])
    lo = np.array([r["lo"] for r in ys])
    hi = np.array([r["hi"] for r in ys])
    c0, c1 = facts["crisis"]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=x + x[::-1], y=np.concatenate([hi, lo[::-1]]), fill="toself",
        fillcolor="rgba(234,88,12,.14)", line=dict(width=0),
        hoverinfo="skip", name="95% CI"))
    fig.add_trace(go.Scatter(
        x=x, y=coef, mode="lines+markers",
        line=dict(color=POS, width=2.8),
        marker=dict(size=7, color=[CRISIS_COLOR if c0 <= y <= c1 else POS for y in x]),
        customdata=np.stack([lo, hi], axis=-1),
        hovertemplate="%{x} 年<br>系数 %{y:.3f}<br>95% CI [%{customdata[0]:.3f}, "
                      "%{customdata[1]:.3f}]<extra></extra>", name="年份效应"))
    fig.add_hline(y=0, line=dict(color="#64748b", width=1, dash="dot"))

    fig.update_layout(**_base(
        "<b>网点不是「老死」而是「被关」：危机后整合窗口，年份效应翻倍</b><br>"
        f"<sub>cloglog 年份虚变量（参照 1994，系数 = 0）；y 越大 = 当年关闭风险越高；"
        f"朱红点 = {c0}–{c1} 整合窗口</sub>", height=430))
    fig.update_xaxes(title="日历年", dtick=5)
    fig.update_yaxes(title="年份效应系数（cloglog，95% CI）")
    fig.add_vrect(x0=c0 - 0.5, x1=c1 + 0.5, fillcolor=CRISIS_COLOR, opacity=0.07,
                  line_width=0, layer="below")
    fig.add_annotation(x=(c0 + c1) / 2, y=float(coef.max()), text="危机后整合窗口",
                       showarrow=False, yshift=16, font=dict(size=12, color=CRISIS_COLOR))
    return _style_axes(fig)


# --------------------------------------------------------------------------- #
# ② 非年份因子森林
# --------------------------------------------------------------------------- #
BANK_RATE_KEY = "bank_closed_rate"


def fig_factor_forest(facts: dict) -> go.Figure:
    """非年份因子的系数森林。**刻意剔除 bank_closed_rate**：

    它的系数 3.82 比其余因子（|coef| ≤ 0.87）大一个量级，混在一张图里会把其余
    全部压成一条线 —— 所以单独做成一张「主导因子」卡（见 model_report）。
    """
    rows = [r for r in _factor_coefs(facts) if sd.coef_label(r["name"]) != BANK_RATE_KEY]
    if not rows:
        return go.Figure()
    rows = sorted(rows, key=lambda r: r["coef"])
    y = [r["label"] for r in rows]
    coef = np.array([r["coef"] for r in rows])
    lo = np.array([r["lo"] for r in rows])
    hi = np.array([r["hi"] for r in rows])

    fig = go.Figure(go.Scatter(
        x=coef, y=y, mode="markers",
        error_x=dict(type="data", symmetric=False,
                     array=hi - coef, arrayminus=coef - lo,
                     color="#94a3b8", thickness=1.4, width=4),
        marker=dict(size=8, color=np.where(coef > 0, POS, NEG),
                    line=dict(color="#ffffff", width=1)),
        customdata=np.stack([lo, hi, [r["p"] for r in rows]], axis=-1),
        hovertemplate="%{y}<br>系数 %{x:.4f}<br>95% CI [%{customdata[0]:.4f}, "
                      "%{customdata[1]:.4f}]<br>p=%{customdata[2]:.2g}<extra></extra>"))
    fig.add_vline(x=0, line=dict(color="#64748b", width=1))
    fig.update_layout(**_base(
        "<b>非年份因子：规模是护城河，地理分散更易被整合</b><br>"
        "<sub>cloglog 系数（点）+ 95% CI；<span style='color:#ea580c'>橙 = 缩短寿命</span>，"
        "<span style='color:#1d4ed8'>蓝 = 延长寿命</span>；"
        f"bank_closed_rate（系数 3.82）量级远超其余，单独列出</sub>", height=460))
    fig.update_xaxes(title="系数（cloglog 线性预测器尺度）")
    return _style_axes(fig)


# --------------------------------------------------------------------------- #
# ③ SHAP 重要性
# --------------------------------------------------------------------------- #
def fig_shap_importance(facts: dict) -> go.Figure:
    rows = facts["shap_imp"]
    if not rows:
        return go.Figure()
    rows = list(reversed(rows))          # plotly 从下往上画
    fig = go.Figure(go.Bar(
        x=[r["mean_abs_shap"] for r in rows], y=[r["label"] for r in rows],
        orientation="h",
        marker=dict(color=[POS if r["mean_abs_shap"] > 0.1 else "#94a3b8" for r in rows],
                    line=dict(color="#ffffff", width=0.6)),
        text=[f"{r['mean_abs_shap']:.4f}" for r in rows], textposition="outside",
        textfont=dict(size=11, color=TICK),
        customdata=[[r["feature"], r["note"]] for r in rows],
        hovertemplate="<b>%{customdata[0]}</b><br>mean |SHAP| = %{x:.4f}"
                      "<br>%{customdata[1]}<extra></extra>"))
    fig.update_layout(**_base(
        "<b>谁在驱动风险：年份之后，银行层因素最强</b><br>"
        "<sub>mean |SHAP|（对数轴：量级跨 3 个数量级）；"
        "来源 06_train/output/train_report.md</sub>", height=430))
    fig.update_xaxes(type="log", title="mean |SHAP|（对数）")
    return _style_axes(fig)


def fig_shap_examples(facts: dict, mode: str = "all") -> go.Figure | None:
    """三个真实样本（``shap_force.json``）的 SHAP 分解。

    ``mode``: all / pos（只看推高）/ neg（只看压低）—— 用 updatemenus 在前端切，
    这里只出默认态。数据全部来自上游产物，不是重算的。
    """
    sf = facts.get("shap_force")
    if not sf or not sf.get("examples"):
        return None
    examples = sf["examples"]
    fig = make_subplots(rows=len(examples), cols=1,
                        subplot_titles=[f"{e['label']}　→　年度关闭风险 {e['predicted_risk']}"
                                        for e in examples],
                        vertical_spacing=0.14)
    for i, e in enumerate(examples, start=1):
        items = sorted(e["shap"].items(), key=lambda kv: -abs(kv[1]))
        fig.add_trace(go.Bar(
            x=[v for _, v in items], y=[k for k, _ in items], orientation="h",
            marker=dict(color=[POS if v > 0 else NEG for _, v in items],
                        line=dict(color="#ffffff", width=0.5)),
            hovertemplate="特征=%{y}<br>SHAP=%{x:+.3f}（logit 贡献）<extra></extra>",
            showlegend=False), row=i, col=1)
        fig.add_vline(x=0, line=dict(color="#64748b", width=0.8), row=i, col=1)
        fig.update_xaxes(title_text="SHAP 值（logit 贡献）", zeroline=False,
                         gridcolor=GRID, row=i, col=1)
        fig.update_yaxes(autorange="reversed", row=i, col=1)
    fig.update_layout(**_base(
        "<b>三个真实网点：谁把它推向关闭</b><br>"
        f"<sub>红色＝推高风险，蓝色＝压低风险；按 |SHAP| 降序　|　"
        f"基线 logit = {sf.get('base_value', 0):.3f}　|　"
        f"来源 06_train/output/test_predictions.csv（已固化为 shap_force.json）</sub>",
        height=300 * len(examples) + 60, margin=dict(l=170, r=40, t=110, b=60),
        bargap=0.28))
    return _style_axes(fig)


# --------------------------------------------------------------------------- #
# ④ 风险打分台（predict_demo）
# --------------------------------------------------------------------------- #
NUMERIC_INPUTS = [
    # key,                 中文名,              单位,      来源字段（取区间）
    ("bank_closed_rate", "所属银行历史关闭率", "", None),
    ("log_depsumbr", "存款规模", "美元（对数滑块）", "DEPSUMBR_last"),
    ("neighbor_count", "同格网点数（竞争强度）", "个", "neighbor_count"),
    ("age", "网点年龄", "年", "age"),
    ("lat", "纬度", "°", "SIMS_LATITUDE"),
    ("lng", "经度", "°", "SIMS_LONGITUDE"),
]


def build_cloglog_spec(facts: dict) -> dict:
    """从 ``cloglog_summary.txt`` 的真实系数构造一个**可运行**的风险计算器规格。

    为什么不用 logit：logit 的系数在 ``logit_coefficients.csv`` 里，而 CSV **不入库**。
    cloglog 的完整系数表（含 95% CI）在入库的 ``cloglog_summary.txt`` 里，
    所以它才是缺数据环境下唯一诚实可用的「真模型」。

    滑块区间一律来自上游产物（``05_map/output/map.md`` 的 mean/median/max，
    ``02_profile/output/profile.yaml`` 的 min/std），**不猜、不写死**。
    """
    fields, profile = facts["fields"], facts["profile"]
    coef_by = {sd.coef_label(c["name"]): c for c in facts["coefs"]}
    intercept = next((c["coef"] for c in facts["coefs"]
                      if c["name"] == "Intercept"), -4.6055)

    def rng(field_key: str, lo: float, hi: float, default: float):
        st = fields.get(field_key, {})
        return {"min": float(lo),
                "max": float(st.get("max", hi)),
                "default": float(st.get("median", default))}

    def sigma3(name: str, fallback: tuple[float, float]):
        st = profile.get(name, {})
        if {"mean", "std"} <= set(st):
            m, s = st["mean"], st["std"]
            return m - 3 * s, m + 3 * s, m
        return fallback[0], fallback[1], (fallback[0] + fallback[1]) / 2

    la0, la1, la_d = sigma3("SIMS_LATITUDE", (24.0, 50.0))
    ln0, ln1, ln_d = sigma3("SIMS_LONGITUDE", (-125.0, -66.0))

    num = {}
    for key, label, unit, src in NUMERIC_INPUTS:
        c = coef_by.get(key)
        if not c:
            continue
        if key == "log_depsumbr":
            st = fields.get("DEPSUMBR_last", {})
            num[key] = {"label": label, "unit": unit, "coef": c["coef"],
                        "ci": [c["lo"], c["hi"]], "p": c["p"],
                        "min": 0.0, "max": float(np.log1p(st.get("max", 7.272e8))),
                        "default": float(np.log1p(st.get("median", 39360.0))),
                        "log_amount": True,
                        "note": "log_depsumbr = log1p(存款额)；滑块按金额对数刻度"}
        elif key == "lat":
            num[key] = {"label": label, "unit": unit, "coef": c["coef"],
                        "ci": [c["lo"], c["hi"]], "p": c["p"],
                        "min": la0, "max": la1, "default": la_d,
                        "note": "区间取 mean ± 3σ（02_profile），仅作地理基线"}
        elif key == "lng":
            num[key] = {"label": label, "unit": unit, "coef": c["coef"],
                        "ci": [c["lo"], c["hi"]], "p": c["p"],
                        "min": ln0, "max": ln1, "default": ln_d,
                        "note": "区间取 mean ± 3σ（02_profile），仅作地理基线"}
        elif key == "bank_closed_rate":
            num[key] = {"label": label, "unit": unit, "coef": c["coef"],
                        "ci": [c["lo"], c["hi"]], "p": c["p"],
                        "min": 0.0, "max": 1.0,
                        "default": float(facts["key"].get("closed_rate", 0.529)),
                        "note": "银行历史关闭率（0–1）；默认取全样本网点关闭率"}
        else:
            r = rng(src or key, 0.0, 1.0, 0.0)
            num[key] = {"label": label, "unit": unit, "coef": c["coef"],
                        "ci": [c["lo"], c["hi"]], "p": c["p"],
                        "min": max(0.0, r["min"]), "max": r["max"],
                        "default": r["default"],
                        "note": f"区间来自 05_map/output/map.md（{src}）"}

    # 类别：从系数还原档位（参照档 = 系数表里没有的那一档，系数记 0）
    cat_defs = {
        "year": ("日历年", "1994", "2010"),
        "BKCLASS": ("银行监管类别", "N", "NM"),
        "fragility_tier": ("银行脆弱性分层", "L0_单网点", "L0_单网点"),
    }
    cat = {}
    for key, (label, reference, default) in cat_defs.items():
        opts = {sd.coef_label(c["name"]): c["coef"]
                for c in facts["coefs"] if c["name"].startswith(f"C({key})")}
        if not opts:
            continue
        # 参照档在系数表里没有行（系数 = 0），但必须能选 —— 否则用户选不到基线档
        opts.setdefault(reference, 0.0)
        if default not in opts:
            default = sorted(opts)[0]
        cat[key] = {"label": label, "reference": reference,
                    "options": opts, "default": default}

    return {"model": "cloglog（离散时间，带 95% CI）",
            "link": "cloglog",
            "source": "06_train/output/cloglog_summary.txt（完整系数表）",
            "intercept": intercept, "numeric": num, "categorical": cat,
            "note": ("概率绝对值受训练期分层下采样影响（面板事件率 4.13%，"
                     "建模样本事件率 33.3%）：只看<b>方向与相对量级</b>，"
                     "不要把绝对概率当业务概率。")}


def build_predict_demo(spec: dict, facts: dict | None = None, out: Path | None = None) -> Path:
    """风险打分台：cloglog 真模型（纯前端，离线可算）。"""
    payload = json.dumps(spec, ensure_ascii=False)
    model = spec.get("model", "")
    note = spec.get("note", "")
    is_logit = spec.get("link") == "logit"
    fid = spec.get("fidelity")

    fidelity_html = ""
    if fid:
        fidelity_html = (f'<div class="note"><b>保真度自检</b>：本页复现的测试集 AUC = '
                         f'<code>{fid["auc_reproduced"]}</code>，与 '
                         f'<code>06_train/output/metrics.json</code> 的 '
                         f'<code>{fid["auc_reference"]}</code> 相差 '
                         f'<code>{fid["abs_diff"]}</code>（n={fid["n_test"]:,}，'
                         f'事件率 {fid["event_rate"]:.2%}）。</div>')

    js = """
    var SPEC = __PAYLOAD__;
    var IS_LOGIT = __IS_LOGIT__;
    var N = SPEC.numeric, C = SPEC.categorical;
    var box = document.getElementById('inputs');
    var state = {};

    function riskOf(eta){
      if (IS_LOGIT) { return 1/(1+Math.exp(-eta)); }
      return 1 - Math.exp(-Math.exp(eta));          // cloglog link
    }
    function fmt(v, d){ return Number(v).toFixed(d === undefined ? 2 : d); }
    function display(key, v){
      var s = N[key];
      if (s.log_amount) { return Math.expm1(v); }   // 对数刻度 → 金额
      return v;
    }
    function fmtDisplay(key, v){
      var x = display(key, v);
      if (Math.abs(x) >= 1e6) return (x/1e6).toFixed(2) + 'M';
      if (Math.abs(x) >= 1e3) return (x/1e3).toFixed(1) + 'k';
      return fmt(x, Math.abs(x) < 10 ? 2 : 0);
    }

    function addRange(key){
      var s = N[key];
      var step = Math.max((s.max - s.min)/300, 1e-6);
      var w = document.createElement('div'); w.className = 'f';
      w.innerHTML = '<label><span>' + s.label +
        (s.unit ? '<i>（' + s.unit + '）</i>' : '') +
        '</span><b id="v_' + key + '"></b></label>' +
        '<input type="range" id="i_' + key + '" min="' + s.min + '" max="' + s.max +
        '" step="' + step + '" value="' + s.default + '">' +
        '<div class="sub"><span>系数 ' + s.coef.toPrecision(4) +
        ' · 95% CI [' + s.ci[0] + ', ' + s.ci[1] + ']</span>' +
        '<span class="rk" id="r_' + key + '"></span></div>';
      box.appendChild(w);
      state[key] = s.default;
      w.querySelector('input').addEventListener('input', function(e){
        state[key] = parseFloat(e.target.value); paint();
      });
    }
    function addSelect(key){
      var c = C[key];
      var opts = Object.keys(c.options).sort();
      var w = document.createElement('div'); w.className = 'f';
      w.innerHTML = '<label><span>' + c.label + '</span><b id="v_' + key + '"></b></label>' +
        '<select id="i_' + key + '">' + opts.map(function(v){
          return '<option value="' + v + '"' + (v === c.default ? ' selected' : '') +
                 '>' + v + '　(' + (c.options[v] >= 0 ? '+' : '') +
                 c.options[v].toFixed(3) + ')</option>';
        }).join('') + '</select>' +
        '<div class="sub"><span>参照档：' + c.reference + '（系数 = 0）</span></div>';
      box.appendChild(w);
      state[key] = c.default;
      w.querySelector('select').addEventListener('change', function(e){
        state[key] = e.target.value; paint();
      });
    }

    Object.keys(N).forEach(addRange);
    Object.keys(C).forEach(addSelect);

    function etaOf(over){
      var e = SPEC.intercept, i;
      for (var k in N){
        var v = (over && over[k] !== undefined) ? over[k] : state[k];
        e += N[k].coef * v;
      }
      for (var c in C){
        var lv = (over && over[c] !== undefined) ? over[c] : state[c];
        e += (C[c].options[lv] || 0);
      }
      return e;
    }
    function parts(){
      var out = [{name: '截距（基线）', v: SPEC.intercept, kind: 'base'}];
      for (var k in N) out.push({name: N[k].label, v: N[k].coef * state[k], kind: 'num', key: k});
      for (var c in C) out.push({name: C[c].label + ' = ' + state[c],
                                 v: (C[c].options[state[c]] || 0), kind: 'cat'});
      return out;
    }

    var BASE = null;      // 默认档位下的风险，作为“基准”
    function paint(){
      var k, c;
      for (k in N){
        document.getElementById('v_' + k).textContent = fmtDisplay(k, state[k]);
      }
      for (c in C) document.getElementById('v_' + c).textContent = state[c];

      var eta = etaOf(), p = riskOf(eta);
      if (BASE === null) BASE = riskOf(etaOf({}));
      document.getElementById('p').textContent = (p * 100).toFixed(2) + '%';
      document.getElementById('eta').textContent = eta.toFixed(3);
      var bar = document.getElementById('bar');
      bar.style.width = Math.min(100, Math.pow(p, 0.45) * 100).toFixed(1) + '%';
      bar.style.background = p > BASE ? '#ea580c' : '#1d4ed8';
      document.getElementById('cmp').textContent =
        '基准网点（全部取默认档）风险 ' + (BASE * 100).toFixed(2) + '%　→　当前为基准的 ' +
        (p / BASE).toFixed(2) + ' 倍';
      document.getElementById('tag').textContent =
        p >= 0.3 ? '高危' : (p >= 0.1 ? '偏高' : (p >= 0.03 ? '中等' : '低危'));
      document.getElementById('tag').className = 'tagbd ' +
        (p >= 0.3 ? 'hi' : (p >= 0.1 ? 'md' : 'lo'));

      // 贡献分解
      var ps = parts().slice(1).sort(function(a,b){ return Math.abs(b.v) - Math.abs(a.v); });
      var wf = document.getElementById('wf');
      var maxAbs = Math.max.apply(null, ps.map(function(a){ return Math.abs(a.v); }).concat([0.3]));
      wf.innerHTML = ps.map(function(a){
        var w = Math.max(Math.abs(a.v) / maxAbs * 48, 0.5);
        var pos = a.v >= 0;
        return '<div class="row"><div class="nm" title="' + a.name + '">' + a.name + '</div>' +
          '<div class="trk"><i class="' + (pos ? 'pos' : 'neg') + '" style="' +
          (pos ? 'left:50%;width:' : 'right:50%;width:') + w.toFixed(2) + '%"></i></div>' +
          '<div class="val">' + (pos ? '+' : '') + fmt(a.v, 3) + '</div></div>';
      }).join('');

      // 单因素敏感性（tornado）：每个数值特征从 min → max，其余保持当前
      var tor = [];
      for (k in N){
        var s = N[k];
        var o1 = {}, o2 = {}; o1[k] = s.min; o2[k] = s.max;
        var p1 = riskOf(etaOf(o1)), p2 = riskOf(etaOf(o2));
        tor.push({name: s.label, lo: Math.min(p1, p2), hi: Math.max(p1, p2),
                  cur: p, up: p2 >= p1});
        document.getElementById('r_' + k).textContent =
          (p2 >= p1 ? '↑ ' : '↓ ') + (Math.abs(p2 - p1) * 100).toFixed(1) + 'pp';
      }
      tor.sort(function(a,b){ return (b.hi - b.lo) - (a.hi - a.lo); });
      var tmax = Math.max.apply(null, tor.map(function(t){ return t.hi; }).concat([0.01]));
      var scale = function(v){ return (v / tmax * 100).toFixed(2); };
      document.getElementById('tor').innerHTML = tor.map(function(t){
        var l = scale(t.lo), w = Math.max(scale(t.hi) - scale(t.lo), 0.6);
        return '<div class="row"><div class="nm">' + t.name + '</div>' +
          '<div class="trk"><i class="pos" style="left:' + l + '%;width:' + w.toFixed(2) +
          '%;opacity:.45"></i><i class="cur" style="left:0;width:' + scale(t.cur).toFixed(2) +
          '%"></i></div><div class="val">' + (t.lo*100).toFixed(1) + '→' +
          (t.hi*100).toFixed(1) + '%</div></div>';
      }).join('');
    }
    paint();
    """
    js = js.replace("__PAYLOAD__", payload).replace("__IS_LOGIT__", "true" if is_logit else "false")

    body = f"""
    <p>拖动下面的特征，右侧<b>实时</b>算出该网点下一年的关闭风险，并拆出每个特征
    贡献了多少。所有计算在浏览器里完成，<b>不联网、不上传</b>。</p>
    <div class="badges">
      <span class="badge b">模型：{model}</span>
      <span class="badge">来源：{spec.get('source', '—')}</span>
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
          　|　cloglog 连接：P = 1 − exp(−exp(η))</div>
        </div>
        <div class="panel" style="margin-top:16px">
          <h3>这个分数是怎么来的（线性预测器贡献分解）</h3>
          <div class="wf" id="wf"></div>
          <div class="hint">线性模型的贡献分解即 SHAP 值：
          <span style="color:{POS}">橙＝推高风险</span>、
          <span style="color:{NEG}">蓝＝压低风险</span>，按 |贡献| 降序。</div>
        </div>
        <div class="panel" style="margin-top:16px">
          <h3>单因素敏感性：动一个变量，风险能摆动多少</h3>
          <div class="wf" id="tor"></div>
          <div class="hint">每个特征单独从最小值扫到最大值（其余保持当前），
          条 = 风险可达区间，深色 = 当前风险。条越长 = 这个变量越「有话语权」。</div>
        </div>
      </div>
    </div>
    <div class="danger"><b>边界：这是风险预测，不是因果，也不是 ROI 工具。</b>
      <ul>
        <li>拖动滑块<b>不会</b>改变网点真实命运 —— 它只展示模型「看过数据后」怎么打分。</li>
        <li>{note}</li>
        <li>不承诺干预阈值、不承诺 ROI（成本参数缺失）。</li>
      </ul></div>
    {fidelity_html}
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
    .f .sub{display:flex;justify-content:space-between;font-size:10.5px;color:var(--faint);
      margin-top:2px;gap:8px}
    .f .sub .rk{color:var(--risk);font-variant-numeric:tabular-nums}
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
    .trk i.cur{background:#0f172a;height:15px;top:0;opacity:.85}
    .val{text-align:right;font-variant-numeric:tabular-nums;color:var(--sub);font-size:11.5px}
    """
    html = ui.page("风险打分台 · 这个网点明年会关闭吗", body,
                   subtitle="拖动特征 → 实时得到年度关闭风险、逐特征贡献分解与单因素敏感性。"
                            "纯前端计算，离线可开。",
                   extra_css=css, extra_js=js, active_nav="王牌 demo")
    p = out / "predict_demo.html"
    p.write_text(html, encoding="utf-8")
    return p


# --------------------------------------------------------------------------- #
# ⑤ SHAP 解释器
# --------------------------------------------------------------------------- #
def build_shap_force(facts: dict, static_figs: dict, out: Path) -> Path:
    imp = _div(fig_shap_importance(facts), 430)
    ex = fig_shap_examples(facts)
    ex_html = _div(ex, 300 * len(facts["shap_force"]["examples"]) + 60) if ex else (
        ui.callout("warn", "缺单样本 SHAP 分解",
                   "<code>09_interactive/output/shap_force.json</code> 不存在 —— "
                   "它由 <code>test_predictions.csv</code> 生成（不入库）。"
                   "在有完整数据的环境里重跑 ⑨ 会自动补齐。"))
    png = static_figs.get("03-shap-importance")
    shot = ui.fig_img(f"assets/fig/{png}", "上游 ⑦ 阶段产出的静态 SHAP 重要性图（同一口径）",
                      alt="SHAP importance") if png else ""

    body = f"""
    <p>模型说一个网点风险高，凭什么？这一页把它拆开：<b>全局</b>看哪些特征在驱动，
    <b>局部</b>看单个网点被谁推向关闭。</p>
    {imp}
    {ui.formula("线性模型的 SHAP（精确值，非近似）",
                "数值特征：SHAP = coef × (x − mean) / std<br>"
                "类别特征：SHAP = 该档位的 one-hot 系数（参照档 = 0）<br>"
                "Σ SHAP + 截距 = logit　⇒　各项之和<b>恰好</b>等于模型输出")}
    <h2>三个真实网点：谁把它推向关闭</h2>
    {ex_html}
    <h2>上游静态产物（同一口径）</h2>
    {shot}
    {ui.callout("note", "怎么读这两张图",
                "<ul><li><b>year 排第一</b>：危机后整合窗口把风险整体抬高 —— "
                "这是「什么时候比多老更重要」的量化版本。</li>"
                "<li><b>bank_closed_rate 排第二</b>：银行自身的历史裁撤倾向，"
                "是最强的单点因子（量级与 year 相当）。</li>"
                "<li><b>age（网点年龄）排在最后</b>（mean|SHAP| 0.003）—— "
                "「老网点更容易死」在本模型里几乎不成立；年龄效应还被左截断污染。</li></ul>")}
    """
    html = ui.page("可解释性 · 模型凭什么说它风险高", body,
                   subtitle="全局 SHAP 重要性（对数轴）+ 三个真实网点的逐特征分解。",
                   with_plotly=True, active_nav="可解释性")
    p = out / "shap_force.html"
    p.write_text(html, encoding="utf-8")
    return p


# --------------------------------------------------------------------------- #
# ⑥ 模型体检报告
# --------------------------------------------------------------------------- #
def build_model_report(facts: dict, static_figs: dict, out: Path) -> Path:
    t = facts["test"]
    moran = facts["moran"]
    bcr = next((c for c in facts["coefs"]
                if sd.coef_label(c["name"]) == BANK_RATE_KEY), None)

    bcr_card = ""
    if bcr:
        bcr_card = (
            '<div class="card" style="border-left:4px solid var(--risk)">'
            '<div class="t">主导因子 · bank_closed_rate</div>'
            f'<p class="d">系数 <b style="color:var(--risk);font-size:19px">'
            f'{bcr["coef"]:.4f}</b>　95% CI [{bcr["lo"]:.3f}, {bcr["hi"]:.3f}]'
            f'<br><span class="muted">量级是其余因子的 4–100 倍，'
            f'因此在下方森林图里单独列出，避免把其它因子压平。</span></p></div>')

    kpi = ui.kpi_strip([
        ("测试 AUC", ui.fmt_num(t.get("auc"), 4), "区分度（仅同口径可比）", "brand"),
        ("C-index", ui.fmt_num(t.get("c_index"), 4), "排序一致性", "brand"),
        ("Brier", ui.fmt_num(t.get("brier"), 4), "越低越好", "good"),
        ("事件率", ui.fmt_pct(t.get("event_rate")), f"测试 n={ui.fmt_int(t.get('n'))}", "warn"),
    ])

    png_roc = static_figs.get("04-roc-calibration")
    png_for = static_figs.get("05-cloglog-forest")
    shots = "".join([
        ui.fig_img(f"assets/fig/{png_roc}", "上游 ⑦：ROC 与校准曲线（区分度良好，高危段概率略低估）",
                   alt="ROC calibration") if png_roc else "",
        ui.fig_img(f"assets/fig/{png_for}", "上游 ⑦：cloglog 系数森林（同一口径的静态版）",
                   alt="cloglog forest") if png_for else "",
    ])

    body = f"""
    <p>这一页回答「模型够不够用」。结论是：<b>区分度很好，但残差里还有东西没解释</b>。</p>
    {kpi}

    <h2>① 什么时候最危险：年份效应</h2>
    {_div(fig_year_effect(facts), 430)}

    <h2>② 非年份因子：谁延长、谁缩短寿命</h2>
    {bcr_card}
    {_div(fig_factor_forest(facts), 460)}

    <h2>③ 残差诊断：还有空间结构没进模型</h2>
    {ui.callout("warn", f"残差 Moran's I = {ui.fmt_num(moran.get('moran_i'))}"
                        f"（p = {moran.get('p_value')}，k = {moran.get('k_neighbors')}，"
                        f"置换 {moran.get('permutations')} 次，n = {ui.fmt_int(moran.get('n'))}）",
                "显著为正 → 控制银行与年份之后，<b>本地市场条件仍然聚集</b>"
                "（县域经济、竞争密度变化等未进入模型）。"
                "因此点估计不可解释为「网点自身属性的完整效应」。")}

    <h2>④ 上游静态产物（同一口径）</h2>
    {shots}

    <h2>⑤ 已知限制（摘要，完整版见「边界与止损」）</h2>
    {"".join(ui.guard(f"限制 {i}", lim) for i, lim in enumerate(facts["limits"][:5], start=1))}
    """
    html = ui.page("模型体检报告 · 准，但没那么准", body,
                   subtitle="年份效应 + 因子森林（均带 95% CI）+ 性能指标 + 残差空间自相关。",
                   with_plotly=True, active_nav="模型体检")
    p = out / "model_report.html"
    p.write_text(html, encoding="utf-8")
    return p


# --------------------------------------------------------------------------- #
# ⑦ 边界与止损（产品 2 的差异化重点）
# --------------------------------------------------------------------------- #
def build_guardrails(facts: dict, out: Path) -> Path:
    limits = "".join(ui.guard(f"限制 {i}", lim)
                     for i, lim in enumerate(facts["limits"], start=1))
    stops = "".join(ui.guard(f"止损条件 {i}", s)
                    for i, s in enumerate(facts["stops"], start=1))

    dos = [
        ("✅ 可以这样用",
         ["把风险分当作<b>排序 / 分层</b>依据：先查分高的那批网点",
          "把它作为<b>进一步尽调的线索</b>，配合本地市场信息一起判断",
          "在同一口径内（同一次运行、同抽样）比较不同网点 / 群体的相对风险",
          "结合银行层脆弱性做<b>组合层面</b>的敞口观察"]),
        ("❌ 不能这样用",
         ["把系数读成<b>因果效应</b>：「把存款做大一倍就能降低 X% 风险」",
          "换算<b>干预阈值 / ROI</b>：「风险 > p 就该撤并」（缺成本参数）",
          "跨数据集、跨抽样方案比较 <b>AUC / C-index</b> 的绝对值",
          "对 <b>2010 年之前</b>的年份效应做业务解读（登记口径不完整）",
          "用 <b>KM 曲线尾部（> 25 年）</b> 下结论（风险集太小）"]),
    ]
    pair = '<div class="grid g2">' + "".join(
        f'<div class="card"><div class="t">{t}</div><ul style="margin:8px 0 0;padding-left:20px">'
        + "".join(f'<li style="font-size:13.5px;color:var(--sub);margin:6px 0">{x}</li>'
                  for x in items) + "</ul></div>" for t, items in dos) + "</div>"

    body = f"""
    <p class="kicker">产品 2 的要点：标注边界</p>
    <p>预测模型最容易被误读为因果 / ROI 工具。这一页把「什么情况下<b>不能</b>用」
    写在明面上 —— <b>能被质疑的模型才可信</b>。</p>
    {ui.callout("danger", "一句话边界",
                "本模型是<b>风险预测</b>（离散时间 hazard），<b>不是因果识别</b>；"
                "不承诺干预阈值，不承诺 ROI（成本参数缺失）。")}

    <h2>① 已知限制（{len(facts['limits'])} 条）</h2>
    {limits}

    <h2>② 止损条件（{len(facts['stops'])} 条 · 触发即停止）</h2>
    <p class="muted">来自 <code>08_conclude/output/conclusion_report.json</code>。
    任何一条被触发，就不该继续往下解读模型输出。</p>
    {stops}

    <h2>③ 正确用法 vs 错误用法</h2>
    {pair}
    """
    html = ui.page("边界与止损 · 什么情况下不能用这个模型", body,
                   subtitle="8 条已知限制 + 5 条止损条件 + 正确/错误用法对照。",
                   active_nav="边界")
    p = out / "guardrails.html"
    p.write_text(html, encoding="utf-8")
    return p


# --------------------------------------------------------------------------- #
# ⑧ KM / ROC（CSV 在时用真数据；否则降级）
# --------------------------------------------------------------------------- #
def build_km_roc(facts: dict, static_figs: dict, out: Path) -> Path:
    png_km = static_figs.get("02-km-by-group")
    png_hz = static_figs.get("01-baseline-hazard-by-year")
    shots = "".join([
        ui.fig_img(f"assets/fig/{png_km}",
                   "上游 ⑦：KM 按银行脆弱性分层 —— 银行越脆弱，网点存活率越低",
                   alt="KM by group") if png_km else "",
        ui.fig_img(f"assets/fig/{png_hz}",
                   "上游 ⑦：年度基准风险 —— 危机后整合窗口关闭率翻倍",
                   alt="baseline hazard") if png_hz else "",
    ])
    t = facts["test"]
    body = f"""
    <div class="warn"><b>当前环境没有样本级 CSV，本页为降级版。</b>
    可 hover 的交互式 KM / ROC 需要 <code>05_map/output/data/branch_panel.csv</code> 与
    <code>06_train/output/test_predictions.csv</code>；二者受仓库根 <code>.gitignore</code>
    约束不入库，重跑 ⑤⑥ 后本页会<b>自动升级</b>为交互版。
    <b>下面是上游 ⑦ 阶段真实产出的静态图，不是示意图。</b></div>

    {shots}

    <h2>区分度（测试集）</h2>
    {ui.kpi_strip([
        ("AUC", ui.fmt_num(t.get("auc"), 4), "仅同口径可比", "brand"),
        ("C-index", ui.fmt_num(t.get("c_index"), 4), "排序一致性", "brand"),
        ("Brier", ui.fmt_num(t.get("brier"), 4), "越低越好", "good"),
        ("事件率", ui.fmt_pct(t.get("event_rate")), f"n={ui.fmt_int(t.get('n'))}", "warn"),
    ])}
    {ui.callout("note", "读图要点",
                "<ul><li>KM 曲线<b>尾部（> 25 年）</b>风险集已很小，置信带很宽 —— 不要在那里下结论。</li>"
                "<li>AUC / C-index 依赖事件率与抽样口径，<b>跨数据集比较无效</b>。</li>"
                "<li>右删失 47%：近半数网点 2025 年仍存活，长寿命区间样本有限。</li></ul>")}
    """
    html = ui.page("生存与区分度 · 谁先死，模型分得开吗", body,
                   subtitle="Kaplan–Meier（按银行脆弱性分层）+ 年度基准风险 + 测试集区分度。",
                   active_nav="生存分析")
    p = out / "km_roc.html"
    p.write_text(html, encoding="utf-8")
    return p


# --------------------------------------------------------------------------- #
# ⑨ 决策驾驶舱（入口）
# --------------------------------------------------------------------------- #
def build_deck(facts: dict, out: Path, *, evolution: bool, demo_model: str) -> Path:
    t = facts["test"]
    moran = facts["moran"]
    key = facts["key"]
    repl = facts["repl"]

    products = [
        ("predict_demo.html", "🎛", "风险打分台", "王牌 demo",
         "拖滑块 → 实时风险 + 逐特征贡献分解 + 单因素敏感性 tornado。纯前端，离线可算。",
         "先玩这个", "b"),
        ("shap_force.html", "🔍", "可解释性", "为什么",
         "全局 SHAP 重要性（对数轴）+ 三个真实网点的逐特征分解，红推高蓝压低。",
         "看模型凭什么", "r"),
        ("model_report.html", "🩺", "模型体检报告", "准不准",
         "年份效应（带 95% CI）+ 非年份因子森林 + 性能指标 + 残差 Moran's I。",
         "看模型够不够用", "g"),
        ("guardrails.html", "🛑", "边界与止损", "什么时候不能用",
         "8 条已知限制 + 5 条止损条件 + 正确/错误用法对照。",
         "用之前必读", "d"),
        ("km_roc.html", "📉", "生存与区分度", "谁先死",
         "KM 分层存活曲线 + 年度基准风险 + 测试集 AUC/C-index/Brier。",
         "看分离度", ""),
    ]
    if evolution:
        products.append(("risk_evolution.html", "🎬", "风险演化动图", "时间维度",
                         "年度关闭数 + 模型风险分布逐年推进（mp4 内嵌，可下载放汇报）。",
                         "适合放汇报", "p"))

    cards = "".join(
        f'''<a class="pcard c-{cls}" href="{href}">
          <span class="ico">{ico}</span>
          <span class="pt">{title}</span>
          <span class="pb">{badge}</span>
          <span class="pd">{desc}</span>
          <span class="pq">→ {cta}</span>
        </a>''' for href, ico, title, badge, desc, cta, cls in products)

    env = repl.get("environment", {})
    params = repl.get("params", {})
    panel = repl.get("panel", {})
    env_html = "".join(f"<tr><td><code>{k}</code></td><td>{v}</td></tr>"
                       for k, v in list(env.items())[:6])
    param_html = "".join(f"<tr><td><code>{k}</code></td><td>{v}</td></tr>"
                         for k, v in params.items())

    body = f"""
    <div class="hero">
      <div class="hero-l">
        <div class="tag">FDIC 网点寿命 · 离散时间生存模型</div>
        <h1 class="hero-h">网点不是「老死」<br>而是「被关」</h1>
        <p class="hero-p"><b>谁家的网点</b>（银行层脆弱性）与<b>什么时候</b>
        （危机后 2009–2014 整合窗口，关闭率翻倍）比网点自身年龄更能解释生死；
        规模是护城河，多网点且地理分散的银行其网点是行业重组的首选裁撤对象。</p>
        <div class="hero-btns">
          <a class="btn primary" href="predict_demo.html">直接上手打分 →</a>
          <a class="btn" href="guardrails.html">先看边界</a>
          <a class="btn" href="model_report.html">模型体检</a>
        </div>
      </div>
      <div class="hero-r">
        {ui.kpi_strip([
            ("测试 AUC", ui.fmt_num(t.get("auc"), 4), "区分度（仅同口径可比）", "brand"),
            ("C-index", ui.fmt_num(t.get("c_index"), 4), "排序一致性", "brand"),
            ("Brier", ui.fmt_num(t.get("brier"), 4), "越低越好", "good"),
            ("残差 Moran's I", ui.fmt_num(moran.get("moran_i"), 3),
             f"p={moran.get('p_value')} · 本地因素未建模", "warn"),
        ])}
      </div>
    </div>

    <h2>① 上手试：这个网点明年会关闭吗</h2>
    <p class="muted">王牌 demo。当前使用的是 <b>{demo_model}</b>。</p>
    {ui.fig_iframe("predict_demo.html", "拖动特征 → 实时风险 + 贡献分解 + 单因素敏感性。"
                                        "纯前端离线计算，不联网不上传。", 760)}

    <h2>② 三问三答</h2>
    <div class="grid g3">
      <div class="card"><div class="t">准吗？</div>
        <p class="d">测试 AUC <b>{ui.fmt_num(t.get('auc'), 4)}</b>、
        C-index <b>{ui.fmt_num(t.get('c_index'), 4)}</b>、Brier
        <b>{ui.fmt_num(t.get('brier'), 4)}</b>。区分度良好。
        但<b>只在同一口径内可比</b>（事件率低，训练做了分层下采样）。</p></div>
      <div class="card"><div class="t">凭什么？</div>
        <p class="d">前两大因子是 <b>year</b>（mean|SHAP| 2.02）与
        <b>bank_closed_rate</b>（1.88），远超其余；
        <b>age（网点年龄）只有 0.003</b> —— 「老网点更容易死」几乎不成立。</p></div>
      <div class="card"><div class="t">有什么没解释？</div>
        <p class="d">残差 Moran's I = <b>{ui.fmt_num(moran.get('moran_i'), 3)}
        （p={moran.get('p_value')}）</b>：控制银行与年份后，本地市场条件仍显著聚集。
        点估计不是「网点自身属性的完整效应」。</p></div>
    </div>

    <h2>③ 结论主图：什么时候最危险</h2>
    {_div(fig_year_effect(facts), 430)}

    <h2>④ 产品矩阵：{len(products)} 个交互件</h2>
    <div class="pgrid">{cards}</div>

    <h2>⑤ 边界速览（完整版见「边界与止损」）</h2>
    {"".join(ui.guard(f"限制 {i}", lim) for i, lim in enumerate(facts["limits"][:4], start=1))}
    {ui.callout("danger", "一句话边界",
                "这是<b>风险预测</b>，不是因果、不是 ROI 工具；"
                "不承诺干预阈值，不承诺 ROI（成本参数缺失）。")}

    <h2>⑥ 可复现</h2>
    <div class="grid g2">
      <div>
        <h3>运行环境（冻结）</h3>
        <table><tbody>{env_html}</tbody></table>
      </div>
      <div>
        <h3>关键参数（冻结）</h3>
        <table><tbody>{param_html}</tbody></table>
      </div>
    </div>
    {ui.callout("note", "面板与命令",
                f"面板 <b>{ui.fmt_int(panel.get('rows'))}</b> 网点-年观测 / "
                f"<b>{ui.fmt_int(panel.get('branches'))}</b> 网点，事件率 "
                f"<b>{ui.fmt_pct(panel.get('event_rate'))}</b>，年份 "
                f"{panel.get('year_range', ['—', '—'])[0]}–{panel.get('year_range', ['—', '—'])[1]}。"
                f"<br>重跑：<code>{repl.get('commands', {}).get('end_to_end', 'python main.py')}</code>"
                f"（单阶段 <code>{repl.get('commands', {}).get('stage_06', 'python main.py --stage 06')}</code>）。"
                f"<br>来源：<code>06_train/output/replication_manifest.json</code>。"
                f"数据：FDIC Summary of Deposits 1994–2025（公共领域，只读）。")}
    """
    css = """
    .hero{display:grid;grid-template-columns:1.1fr .9fr;gap:28px;align-items:center;
      padding:6px 0 10px}
    .hero .tag{display:inline-block;font-size:11.5px;letter-spacing:.16em;color:var(--risk);
      font-weight:800;margin-bottom:12px}
    .hero-h{font-size:38px;line-height:1.16;margin:0 0 14px;letter-spacing:-.02em}
    .hero-p{font-size:15px;color:var(--sub);line-height:1.85;margin:0 0 20px}
    .hero-btns{display:flex;flex-wrap:wrap;gap:10px}
    .pgrid{display:grid;grid-template-columns:repeat(auto-fit,minmax(265px,1fr));gap:14px}
    .pcard{display:flex;flex-direction:column;border:1px solid var(--line);
      border-radius:var(--radius);padding:16px 18px;background:var(--bg);
      box-shadow:var(--shadow);text-decoration:none;color:inherit;transition:.2s}
    .pcard:hover{transform:translateY(-3px);border-color:var(--brand);text-decoration:none}
    .pcard .ico{font-size:21px;margin-bottom:8px}
    .pcard .pt{font-weight:700;font-size:15.5px;color:var(--ink)}
    .pcard .pb{display:inline-block;font-size:11px;padding:2px 8px;border-radius:999px;
      background:var(--soft-2);color:var(--sub);margin:6px 0 8px;align-self:flex-start}
    .pcard .pd{font-size:13.5px;color:var(--sub);line-height:1.7;flex:1}
    .pcard .pq{font-size:13px;color:var(--brand);font-weight:650;margin-top:10px}
    .pcard.c-b{border-top:3px solid var(--brand)}
    .pcard.c-r{border-top:3px solid var(--risk)}
    .pcard.c-g{border-top:3px solid var(--ok)}
    .pcard.c-d{border-top:3px solid var(--danger)}
    .pcard.c-p{border-top:3px solid var(--purple)}
    @media(max-width:900px){ .hero{grid-template-columns:1fr} .hero-h{font-size:28px} }
    """
    html = ui.page("什么样的网点会先死 · 决策驾驶舱", body,
                   subtitle="离散时间生存模型（logit / cloglog + SHAP + 空间残差）｜"
                            "风险预测，非因果｜FDIC SOD 1994–2025",
                   extra_css=css, with_plotly=True, active_nav="入口", home="")
    p = out / "index.html"
    p.write_text(html, encoding="utf-8")
    return p
