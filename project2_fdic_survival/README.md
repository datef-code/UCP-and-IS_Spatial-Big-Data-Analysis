# 方案② FDIC 网点寿命生存模型（project2_fdic_survival）

用 **datakit v2** 规范跑通「① 采集 → ② 画像 → ③ 清洗 → ④ 校验 → ⑤ 映射 →
⑥ 训练 → ⑦ 可视化 → ⑧ 结论」，回答「什么样的网点会先死」。

数据源：FDIC Summary of Deposits 1994–2025（32 个年度文件，81 列，约 1.58 GB，**只读**，
实际位置 `data_raw/fdic`，由 `datakit.yaml` 的 `source_root` 引用）。

## 运行

```powershell
cd E:\workspace\workbuddy\project\data_use\datakit
$env:PYTHONIOENCODING = "utf-8"          # Windows 控制台中文输出
.\.venv\Scripts\python.exe ..\project2_fdic_survival\main.py                 # ①–⑧ 全流程（约 1 分钟）
.\.venv\Scripts\python.exe ..\project2_fdic_survival\main.py --stage 03      # 只跑 03_clean
.\.venv\Scripts\python.exe ..\project2_fdic_survival\main.py --list          # 列出全部阶段
```

> ⑥⑦ 需要 modeling 可选依赖（statsmodels / scikit-learn / shap / matplotlib）：
> `uv sync --extra modeling`；⑤ 的空间网格需要 `h3`（缺失时自动降级 0.01° 网格）。
> 全流程日志：`logs/pipeline.log`；阶段摘要与 `SUMMARY.md` 自动生成。

## 目录结构（datakit v2 规范）

```text
project2_fdic_survival/
├── README.md / SUMMARY.md / datakit.yaml
├── main.py                     # 根编排：importlib 按文件路径加载各阶段（数字前缀不能 import）
├── config/                     # 口径外置：schema / clean_plan / mapping / assertions
├── data_raw/README.md          # 源数据说明（只读；实际数据在仓库根 data_raw/fdic）
├── 01_discover/ … 05_map/      # 内置五阶段：与目录同名入口 .py + README.md + output/
├── 06_train/                   # 扩展阶段（§8）：建模 / 估计
├── 07_visualize/               # 扩展阶段：可视化（figures/ + manifest.json）
├── 08_conclude/                # 扩展阶段：结论 + 已知限制 / 止损条件
└── logs/                       # pipeline.log + stage_summaries.json
```

## 本次运行结果（2026-09-06 重跑）

| 阶段 | 关键结果 |
| --- | --- |
| ① 采集 | 32 个文件 / 1 个分组 / **1.58 GB**；组内列结构一致 |
| ② 画像 | 长表 **2,822,977 行 × 10 列**（1994–2025）；必需 4 / 重要 5 / 忽略 1 字段；异常值 506,766 |
| ③ 清洗 | 2,822,977 → **2,702,716** 行（剔主键缺失 120,261，4.26%）；**零填充**（生存红线） |
| ④ 校验 | 9 条断言 **8 通过、无 P0 阻断**；右删失 47.10%；左截断 51.76% |
| ⑤ 映射 | 网点 **152,538**（关闭 52.90% / 右删失 47.10%）；银行 **15,505**（L0 3,559 / L1 5,918 / L2 6,028）；`h3_r7` |
| ⑥ 训练 | 面板 **1,667,283** 网点-年（事件率 4.13%）；测试 **AUC 0.881 / C-index 0.810 / Brier 0.161**；cloglog 伪 R² 0.387；**Moran's I 0.141（p=0.005）** |
| ⑦ 可视化 | 6 图（PNG + PDF）→ `07_visualize/output/figures/`，登记在 `manifest.json` |
| ⑧ 结论 | `08_conclude/output/conclusion.md`（含已知限制 8 条 / 止损条件 5 条） |

## 关键口径（改口径改 `config/`，不改代码）

| 口径 | 取值 | 理由 |
| --- | --- | --- |
| 追踪主键 | **UNINUMBR** | BRNUM 是银行内序号：1994 年 81,297 行仅 1,531 个唯一值，全期 50.11% 的网点 BRNUM 跨年变化 |
| 出生年 | `min(year(SIMS_ESTABLISHED_DATE))` | 缺失按左截断处理 |
| 死亡年 | `max(year(SIMS_ACQUIRED_DATE))` | 该字段只在并购当年及之后若干年出现；按末行取值会把已关闭网点误判为存活（右删失率虚高到 81%） |
| 左截断 | 出生早于 1994（或出生年缺失） | 51.76%；⑥ 建模时剔除事件早于首次观测的网点 |
| 右删失 | 无死亡年 | 47.10%；**禁止填充**（`clean_plan.forbidden`） |
| 银行归属 | `CERT` 取**首次观测值** | 脆弱性为基线属性，避免用事后归属解释事前风险（按末次归属时银行数 9,545、AUC 降到 0.812） |
| 空间网格 | H3 R7（≈1.22 km），降级 0.01°（≈1.1 km） | 同格网点数 = 竞争强度 `neighbor_count` |

## 一句话结论

> 网点不是「老死」而是「被关」——**谁家的网点（银行层脆弱性）与什么时候（危机后 2009–2014 整合窗口，
> 关闭率翻倍）比网点自身年龄更能解释生死**；规模是护城河（存款越大越长寿），
> 多网点且地理分散的银行其网点是行业重组的首选裁撤对象。
> 残差 Moran's I 显著为正 → 本地市场因素仍未进入模型。

## 已知限制（摘要，完整版见 `08_conclude/output/conclusion.md`）

1. 左截断 51.76%，网点年龄分布左偏，不宜直接读「年龄效应」。
2. 死亡年口径依赖 `SIMS_ACQUIRED_DATE` 的登记方式；右删失 47%，长寿命区间样本有限。
3. 事件率 4.13%，logit 训练做了分层下采样，AUC / C-index 只在同一次运行的口径内可比。
4. 残差仍有空间自相关（Moran's I 0.141，p=0.005）：本地市场条件未进入模型。
5. **相关不等于因果**：本模型是风险预测，不是因果识别；不承诺干预阈值、不承诺 ROI。

## 与上一版（迁移前）的差异

- 旧根脚本 `model.py` / `viz.py` 已删除，逻辑分别搬入 `06_train/06_train.py` 与 `07_visualize/07_visualize.py`；
  旧 `output/`（01–07_viz、data）已清理，产物统一在各阶段 `output/` 下。
- ② 由「1994 单年画像」升级为**全期长表画像**，并输出过程数据 `raw_long.parquet` 供 ③ 复用。
- ⑤ 空间网格由 0.01° 网格升级为 **H3 R7**（同尺度）；银行归属明确为首次 CERT。
- ⑥⑦ 增加 **replication_manifest.json** 与 **manifest.json**（规范 §8.5 / §8.8.5 必交）。
- 关键指标与迁移前一致（AUC 0.881 / C-index 0.810 / Brier 0.161 / Moran's I 0.141）。
