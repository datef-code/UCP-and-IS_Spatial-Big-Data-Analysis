# 09_interactive · ⑨ 交互展示（扩展阶段）

> 项目：[project2_fdic_survival](../README.md)　|　规范：`datakit/PROJECT_STRUCTURE.md` §8.2 / §8.5 / §8.8
> 立项依据：`datakit/suggestions_for_projects_0908.md` —— 产品 2 的主轴是**可上手的产品 demo**。

- **kind**：`visualization`　**depends_on**：`05_map`、`06_train`
- **requires**：`logit_coefficients.csv`、`test_predictions.csv`、`metrics.json`、`branch_panel.csv`
- **extras**：`viz`（plotly）　**blocking**：false

## 本阶段做什么

预测模型最容易被误读为因果 / ROI 工具。让人**亲手拖一次滑块**，比任何静态图都更能
建立「这是打分、不是命运」的正确认知。

| 产物 | 回答什么 | 交互点 |
| --- | --- | --- |
| `output/index.html` | 结论、demo、体检报告能不能一站式看到？ | 入口 + 边界声明 + 复现清单 |
| `output/predict_demo.html` | 给定特征，模型给这个网点打多少风险分？ | 拖滑块 / 选类别 → 实时概率 + 逐特征贡献分解 |
| `output/risk_evolution.mp4/.html` | 关闭在时间上怎么分布？模型看到的风险怎么变？ | mp4 内嵌：年度关闭柱 + 风险分布同步推进 |
| `output/km_roc.html` | 谁先死、什么时候死？模型分得开吗？ | KM 按脆弱性分层（hover 看 at-risk）+ ROC |
| `output/model_report.html` | 模型够不够用？ | 系数森林（点 + 95% CI）+ 指标 + 残差 Moran's I |

## 关键口径与决策理由

1. **保真度自检（页面自带的硬约束）**：`run()` 会用测试集复算 AUC，与
   `metrics.json` 的 0.8814 对照；**差值 > 0.02 直接抛错拒绝产出**。
   实测复现 AUC = **0.8815**（差 0.0000）—— 证明 demo 与主模型一致，不是近似演示。
2. **截距为什么是校准出来的**：模型产物未保存截距（只导出了 feature/coef）。
   因此用**测试集事件率**反解截距（二分求解使平均预测概率 = 观测事件率）。
   这个方法自洽，因为 AUC 与排序无关，校准只影响概率绝对值——页面已显式标注。
3. **动图节奏（按反馈放慢）**：每年 **4 个子帧**（柱子从上一年长到现在、直方图淡入），
   fps=6 → **每年 0.67 s、全程 21.3 s**（图幅 12.8×5.8 in = 1408×638 px）。
   最初每年只闪 0.2 s，看不出「危机后整合窗口」是怎么抬升的。
4. **为什么森林图用 cloglog 而 demo 用 logit**：只有 `cloglog_coefficients.csv`
   带 `Std.Err.` 与 95% CI；`logit_coefficients.csv` 只有系数。
   两者都是本项目真实拟合的产物，页面分别标注模型名，不混用。
5. **贡献分解为什么等于 SHAP**：线性模型的 SHAP 值就是 `coef × (标准化后的特征值)`，
   各项之和 + 截距 = 对数几率。所以这里给的分解是**精确的**，不是近似。
6. **边界必须写在页面上**：「风险预测，不是因果、不是 ROI 工具」放在 demo 正下方，
   不藏在文档里；并列出左截断 / 右删失 / Moran's I / AUC 仅同口径可比四条限制。

## 输入 / 输出

- **输入（只读）**：`06_train/output/{logit_coefficients,cloglog_coefficients,test_predictions,shap_importance,metrics,moran_i}.json|csv`、
  `05_map/output/data/branch_panel.csv`
- **输出**：`output/{index,predict_demo,risk_evolution,km_roc,model_report}.html`
  + `output/risk_evolution.mp4` + `output/manifest.json`
- `predict_demo.html` 是**纯前端**（vanilla JS + 内嵌模型参数）：不联网、不上传、离线可开。

## 运行

```powershell
.\.venv\Scripts\python.exe ..\project2_fdic_survival\main.py --stage 09
```

打开 `output/index.html`；或直接开 `output/predict_demo.html` 上手试。
