# output_legacy_v1/

> **旧脚本（单文件 `main.py` 时代）的产物存档，仅用于与新版比对，不参与流水线、不被任何阶段读取。**
> 规范符合性说明见 `datakit/PROJECT_STRUCTURE.md` §8.6（迁移原则：先建目录、登记映射，
> 旧产物留在原处并标注；本项目把旧产物整体收拢到本目录，比留在 `output/` 更干净）。

## 旧 → 新阶段编号映射

| 旧（本目录） | 新（现行五阶段 + 扩展） | 说明 |
| --- | --- | --- |
| `01_import/` | `01_discover/` | 导入 → 采集：`import_report.json` ≈ `catalog.*` |
| `02_process/` | `02_profile/` + `03_clean/` | 旧版把画像与清洗合成一步，新版拆成②③ |
| `03_validate/` | `04_validate/` | `version_lock.json` 口径被保留并沿用至今 |
| `04_map/` | `05_map/` | `L2_spatial_lag.csv` / `L3_ring_spillover.csv` / `ladder_report.json` 同名沿用 |
| `05_visualize/` | `06_visualize/` | 旧版只有每数据集 2 张图，新版每数据集 3 张（补 L0 ECDF）+ 全局 1 张 |
| `06_conclusion/` | `07_conclude/` | 结论 + 已知限制 |

## 与新版的关键差异（为什么不能直接比数字）

1. **旧版不做多数据集分层**：产物按 `<dataset>/<stage>/` 组织，新版按 `<stage>/output/<dataset>/`
   （规范 §1 多数据集约定）。
2. **旧版没有 config/ 口径外置**：参数硬编码在脚本里，改口径要改代码。
3. **旧版没有 manifest / lineage / version_lock 三件套**：图与数据不可追溯、不可复现。
4. 因此旧产物**只用于数量级比对**（如 Moran's I 是否同号同量级），**不用于结论引用**。

## 处置

- 确认新版结论稳定后可直接删除本目录（根 `README.md` 的目录结构块已注明）。
- 删除前建议先把 `06_conclusion/conclusion.md` 的结论数字与 `07_conclude/output/conclusion.md` 对一次。
