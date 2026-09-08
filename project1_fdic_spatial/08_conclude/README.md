# 08_conclude · ⑧ 结论（扩展阶段 · conclusion）

> 规范：`datakit/PROJECT_STRUCTURE.md` §8.5。入口：`08_conclude.py`。
> `blocking: false`。

## 做什么

把 ⑥ 的估计结果收敛成可读的结论产物：短论（给非技术阅读）、技术报告（distill 风格）、
**conclusion.md（结论 + 已知限制 / 止损条件）**，以及 replication 包元数据。

## 输入（**只读**上游）

- `../06_estimate/output/estimate.json`
- `../07_visualize/output/manifest.json`（图清单，技术报告直接引用，不手写第二份）

## 输出

| 文件 | 说明 |
| --- | --- |
| `output/conclusion.md` | 一句话结论 + 关键数字 + **已知限制** + **止损条件** |
| `output/conclusion_report.json` | 机读结论（供 `SUMMARY.md` 汇总） |
| `output/technical_report.md` | 技术报告：模型总览、TWFE/事件研究、空间计量、敏感性、图表 |
| `output/short_essay.md` | M0 短论（≈ A4 一页） |
| `output/replication_manifest.json` | 复现前置条件 / 命令 / 阶段产物清单 / 期望输出 |

## 必须随结论一起交付的约束

1. 事件前 τ<0 轻微为负 + 区域共同冲击 → **关联证据，非严格因果**；
2. 存款转移 ≠ 区域净增 → 不据此报区域增长红利或 ROI；
3. SAR 在稀疏 KNN 上 ρ 不稳 → 不以 SAR 报溢出量级；
4. 不承诺 ROI、不承诺干预阈值（成本参数缺失）；
5. 坐标最高精度 < 100%（2023–2025 EXACT 85.98% / 1994–2022 屋顶级 16.37%）→ <1 km 环只作参考，主表用 5 km 中等环；
6. 事件研究未加 bootstrap CI。

出现「把结论当因果断言 / 换算 ROI / 用 SAR 报量级 / τ<0 显著」任一用法时，按
`conclusion.md` 的**止损条件**停止。

## 怎么跑

```powershell
python main.py --stage 08
```
