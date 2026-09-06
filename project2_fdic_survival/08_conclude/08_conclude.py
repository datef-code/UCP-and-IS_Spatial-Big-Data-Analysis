# -*- coding: utf-8 -*-
"""08_conclude —— ⑧ 结论（扩展阶段，规范 §8 / §8.5）。

入口文件与目录同名（``08_conclude.py``），必须暴露 ``run(project) -> dict``。
**只读**上游 ``05_map/output/``、``06_train/output/``、``07_visualize/output/``，
产物只进本阶段 ``output/``。

必交（规范 §8.5）：``conclusion.md``（结论 + **已知限制 / 止损条件**）+
``conclusion_report.json``（机读）。结论必须带约束：不承诺因果、不承诺 ROI。
"""
from __future__ import annotations

import datetime as _dt
import json
from pathlib import Path

import pandas as pd

import datakit as dk

STAGE = "08_conclude"
TITLE = "⑧ 结论（一句话交付 + 已知限制 + 止损条件）"

ROOT = Path(__file__).resolve().parent.parent
OUT = Path(__file__).resolve().parent / "output"
IN_MAP = ROOT / "05_map" / "output"
IN_TRAIN = ROOT / "06_train" / "output"
IN_VIZ = ROOT / "07_visualize" / "output"
OUT.mkdir(parents=True, exist_ok=True)

KNOWN_LIMITS = [
    "**左截断**：面板自 1994 起，出生早于 1994（或出生年缺失）的网点按左截断处理，"
    "已剔除事件早于首次观测的 11,787 个网点；网点年龄分布因此左偏，不宜直接读「年龄效应」。",
    "**死亡年口径**：SIMS_ACQUIRED_DATE 只在并购当年（及之后若干年）出现，"
    "按「该网点出现过的最晚年份」判定死亡；若某年补录口径变化会改变关闭率。",
    "**CERT 归属**：银行层脆弱性按**首次观测所属银行**聚合（并购后不追溯重标），"
    "因此并购后关闭的网点仍计入原银行，银行层指标是基线属性而非时变属性。",
    "**右删失 47%**：近半数网点在 2025 年仍存活，长寿命区间的 KM 曲线受样本量限制，尾部不确定。",
    "**事件率低（4.13%）**：logit 训练做了保留全部事件行的分层下采样（50 万 / 20 万），"
    "AUC/C-index 的绝对值随抽样比例变化，跨口径比较需固定抽样。",
    "**残差仍有空间自相关**（Moran's I 显著为正）：说明本地市场条件（县域经济、竞争密度变化）"
    "未进入模型，点估计不可解释为「网点自身属性的完整效应」。",
    "**相关不等于因果**：本模型是风险预测（离散时间 hazard），不是因果识别；"
    "不承诺干预阈值、不承诺 ROI（成本参数缺失）。",
    "**坐标缺失 4.19%**：无坐标网点不进入 H3 网格，空间特征（竞争强度）与 Moran's I 只覆盖有坐标子样本。",
]

STOP_CONDITIONS = [
    "若把系数读成**因果效应**（如「把网点规模提高 1% 可降低关闭风险 X%」）→ 停止："
    "本模型是预测性风险模型，无识别设计。",
    "若用模型输出换算**干预阈值 / ROI**（如「关闭概率 > p 就该撤并」）→ 停止："
    "缺成本参数（网点重置、客户迁移、CAC），量纲不成立。",
    "若把 **C-index / AUC** 当作跨数据集可比指标 → 停止：两者依赖事件率与抽样口径，"
    "只能在同一次运行的训练 / 测试口径下比较。",
    "若对 **2010 年之前**的年份效应做业务解读 → 停止：早年的出生/死亡日期登记不完整，"
    "左截断比例高，年份效应混入了登记口径变化。",
    "若用 **KM 曲线尾部**（> 25 年）下结论 → 停止：风险集在该区间已很小，置信带很宽。",
]


def _read_json(p: Path) -> dict:
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def _fmt_p(p: float | None) -> str:
    if p is None:
        return "n/a"
    return "p<0.001" if p < 0.001 else f"p={p:.3g}"


def write_conclusion(project) -> tuple[Path, Path, dict, str]:
    metrics = _read_json(IN_TRAIN / "metrics.json")
    moran = _read_json(IN_TRAIN / "moran_i.json")
    repl = _read_json(IN_TRAIN / "replication_manifest.json")
    viz_manifest = _read_json(IN_VIZ / "manifest.json")

    test = metrics.get("test", {})
    shap_imp = pd.read_csv(IN_TRAIN / "shap_importance.csv").sort_values(
        "mean_abs_shap", ascending=False)
    shap_txt = " > ".join(f"{r['feature']}({r['mean_abs_shap']:.2f})"
                          for _, r in shap_imp.head(4).iterrows())

    import yaml
    map_yaml = {}
    if (IN_MAP / "map.yaml").exists():
        map_yaml = yaml.safe_load((IN_MAP / "map.yaml").read_text(encoding="utf-8")) or {}
    shape = map_yaml.get("shape") or {}
    closed_rate = map_yaml.get("closed_rate")
    censored_rate = map_yaml.get("right_censored_rate")
    fragility = map_yaml.get("fragility_dist") or {}

    auc, cidx, brier = test.get("auc"), test.get("c_index"), test.get("brier")
    mi, mi_p = moran.get("moran_i"), moran.get("p_value")

    headline = (
        f"网点不是「老死」而是「被关」——谁家的网点（银行层脆弱性）与什么时候"
        f"（危机后 2009–2014 整合窗口，关闭率翻倍）比网点自身年龄更能解释生死；"
        f"规模是护城河（存款越大越长寿），多网点且地理分散的银行其网点是行业重组的首选裁撤对象。"
        f"模型测试 AUC {auc:.3f} / C-index {cidx:.3f}；残差 Moran's I {mi:.3f}（{_fmt_p(mi_p)}）"
        f"说明本地市场因素仍未进入模型。"
    )

    md = f"""# ⑧ 结论 · project2_fdic_survival

> 生成时间：{_dt.datetime.now().isoformat(timespec="seconds")}
> 上游：`05_map/output/map.yaml`、`06_train/output/{{metrics.json, moran_i.json, shap_importance.csv}}`、
> `07_visualize/output/manifest.json`

## 一句话结论

> {headline}

## 关键数字

| 指标 | 值 |
| --- | --- |
| 网点数（风险集） | {shape.get('branch_panel_rows', 0):,}（关闭率 {closed_rate:.2%}，右删失 {censored_rate:.2%}） |
| 银行数 | {shape.get('bank_rows', 0):,}（{'；'.join(f"{k} {v:,}" for k, v in fragility.items())}） |
| 网点-年观测 | {repl.get('panel', {}).get('rows', 0):,}（事件率 {repl.get('panel', {}).get('event_rate', 0):.2%}） |
| 测试集 AUC | {auc:.4f} |
| 测试集 C-index | {cidx:.4f} |
| 测试集 Brier | {brier:.4f} |
| SHAP 重要性（前四） | {shap_txt} |
| 残差 Moran's I | {mi:.4f}（{_fmt_p(mi_p)}，k={moran.get('k_neighbors')}，置换 {moran.get('permutations')} 次） |

## 三条可操作结论

1. **看银行，不看网点年龄**：`bank_closed_rate`（所属银行历史关闭率）与脆弱性分层
   （L1 高集中 / L2 地理分散）在 cloglog 中显著为正 —— 并购整合期的裁撤决策发生在银行层。
2. **规模是护城河**：`log(存款)` 显著为负，网点越大越不容易被关；
   `neighbor_count`（同网格竞争强度）方向为正，拥挤市场中的网点风险更高。
3. **时间窗口极重要**：年份效应（宏观 + 监管周期）是 SHAP 第一因子，
   2009–2014 年关闭率抬升至两倍量级 —— 任何「网点寿命」结论都必须声明年份口径。

## 已知限制（必须阅读）

"""
    md += "\n".join(f"{i}. {t}" for i, t in enumerate(KNOWN_LIMITS, 1))
    md += "\n\n## 止损条件（出现下列用法即停止）\n\n"
    md += "\n".join(f"- {t}" for t in STOP_CONDITIONS)
    md += f"""

## 完整报告与产物

- 训练报告：`../06_train/output/train_report.md`
- 复现清单：`../06_train/output/replication_manifest.json`
- 可视化清单：`../07_visualize/output/manifest.json`（{viz_manifest.get('n_figures', 0)} 图，PNG + PDF）
- 可复用模型：`../06_train/output/logit_pipeline.pkl`（对新网点-年行直接 `predict_proba`）
"""
    p = OUT / "conclusion.md"
    p.write_text(md, encoding="utf-8")

    report = {
        "stage": STAGE,
        "generated_at": _dt.datetime.now().isoformat(timespec="seconds"),
        "headline": headline,
        "key_numbers": {
            "branches": shape.get("branch_panel_rows"),
            "banks": shape.get("bank_rows"),
            "closed_rate": closed_rate,
            "right_censored_rate": censored_rate,
            "panel_rows": repl.get("panel", {}).get("rows"),
            "test_auc": auc, "test_c_index": cidx, "test_brier": brier,
            "moran_i": mi, "moran_p": mi_p,
            "shap_top": shap_imp.head(5).to_dict("records"),
            "fragility_dist": fragility,
        },
        "known_limits": KNOWN_LIMITS,
        "stop_conditions": STOP_CONDITIONS,
        "artifacts": ["conclusion.md", "conclusion_report.json"],
        "conclusion": headline,
    }
    pj = dk.write_json(OUT, "conclusion_report", report)
    return p, pj, report, headline


def run(project) -> dict:
    """只读上游产物，产出结论 + 已知限制 / 止损条件。"""
    project.log(f"[{STAGE}] {TITLE}")
    p, pj, report, headline = write_conclusion(project)
    project.log(f"    [⑧] {p.name} / {pj.name}")
    return {
        "stage": STAGE, "blocking": False,
        "conclusion": headline,
        "test_auc": round(report["key_numbers"]["test_auc"], 4),
        "moran_i": round(report["key_numbers"]["moran_i"], 4),
        "artifacts": ["conclusion.md", "conclusion_report.json"],
    }


def main() -> None:
    project = dk.Project.load(ROOT)
    print(run(project))


if __name__ == "__main__":
    main()
