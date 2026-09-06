# 01_discover · ① 采集

> 项目：[project2_fdic_survival](../README.md)　|　规范：`datakit/PROJECT_STRUCTURE.md` §2-①

## 本阶段做什么

回答「我手上到底有什么数据」：扫描源数据根，统计文件数 / 体积 / 格式分布 / 目录分布 /
数据集分组 / 组内列结构漂移，产出文件级明细。

## 输入 / 输出

- **输入**：`data_raw/fdic`（只读，实际指向仓库根 `data_raw/fdic`）+ `datakit.yaml` 的 `source_root` / `group`
- **输出**（本阶段 `output/`）：

| 产物 | 内容 |
| --- | --- |
| `catalog.yaml` / `catalog.md` | 机读 / 人读清单：总览、格式分布、目录分布、分组、列结构漂移 |
| `files.csv` | 文件级明细：路径 / 格式 / 大小 / 列数 / 行数 / 修改时间 |

## 实现

`01_discover.py::run(project)`：调 `dk.scan(project.source_root)`（只读探测），
按「数字归一为 `#`」分组，再拼装报告；统计算法全部由 datakit 提供。

## 本阶段口径要点（本次运行）

- 32 个年度文件（`fdic_sod_1994.csv` … `fdic_sod_2025.csv`），单一分组 `fdic_sod_#`，合计 **1.58 GB**。
- 组内列结构**一致**（32 年 81 列无增减）→ 跨年可直接拼接。
- `with_md5=false` / `count_rows=false`（源数据量大，默认不做全量指纹与行数统计）。
