# 06_estimate · ⑥ 估计（扩展阶段 · modeling）

> 规范：`datakit/PROJECT_STRUCTURE.md` §8。入口：`06_estimate.py`，`run(project) -> dict`。
> `blocking: false` —— 失败不阻断五阶段，但必须写进 `SUMMARY.md`。

## 做什么

在 exposure 数据底座上做因果与空间计量：

1. 构造网点-年 DID 面板（处理 = 生命周期内首次被 10 km 内**同业**关闭事件辐射；
   处理组只取存续网点，关闭网点自身不做 outcome）；
2. TWFE 双向固定效应 + 网点级事件研究（event-time dummies，基线 τ=-1）；
3. H3 R8 截面空间计量：OLS → LM 检验 → SAR / SEM / SLX → 残差 Moran's I；
4. 效应分解（direct / spillover / total）与环宽敏感性。

## 输入（**只读**上游，禁止回写）

- `../05_map/output/data/branch_year_panel.parquet`
- `../05_map/output/data/branch_dim.csv`
- `../05_map/output/data/closure_exposure.csv`

## 输出（只进本阶段 `output/`）

| 文件 | 说明 |
| --- | --- |
| `output/estimate.json` | 全部模型系数 + LM 检验 + 残差 Moran's I + 敏感性 |
| `output/metrics.json` | 扁平化关键指标（规范 §8.5） |
| `output/replication_manifest.json` | 版本 / 参数 / 随机种子 / 输入指纹（**没有 manifest = 不可复现**） |
| `output/data/did_panel.parquet` | 网点-年 DID 面板 |
| `output/data/did_event_long.parquet` | 事件-长表（τ ∈ [-3, +4]） |
| `output/data/spatial_cross_section.parquet` | H3 R8 截面（2010→2014） |

## 依赖与已知限制

- 可选依赖组：`modeling`（linearmodels / statsmodels / libpysal / esda / spreg / scipy）。
- SAR 在大稀疏 KNN 上 ρ 数值不稳 → **不以 SAR 报溢出量级**，仅以 SLX 的 `W_treat` 作邻 cell 溢出代理。
- 事件研究未加 bootstrap CI；显著性部分来自大样本。

## 怎么跑

```powershell
python main.py --stage 06
```
