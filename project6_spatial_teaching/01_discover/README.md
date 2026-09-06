# 01_discover · ① 采集

> 项目：[project6_spatial_teaching](../README.md)　|　规范：`datakit/PROJECT_STRUCTURE.md` §1 / §2-①

## 本阶段做什么

回答「我手上到底有什么数据」：**逐数据集**扫描只读源目录，统计文件数 / 体积 / 格式分布 /
目录分布 / 数据集分组 / 组内列结构漂移，产出文件级明细，并**逐数据集标注许可状态**。

## 输入 / 输出

- **输入**：`data_raw/`（即仓库根 `../data_raw`，只读）+ `datakit.yaml` 的 `source_root`
- **输出**（多数据集：阶段内按 `<dataset>/` 分目录，全局产物直接放 `output/`）：

| 路径 | 内容 |
| --- | --- |
| `output/<dataset>/catalog.yaml` | 机读清单（总览 / 格式 / 目录 / 分组 / 漂移 / 许可） |
| `output/<dataset>/catalog.md` | 人读清单 |
| `output/<dataset>/files.csv` | 文件级明细：路径 / 格式 / 大小 / 行数 / 列数 / 列名 / 修改时间 / MD5 |
| `output/catalog.yaml`、`output/catalog.md`、`output/files.csv` | 四数据集总览 |

`<dataset>` ∈ `fdic` / `sz_bike` / `snap_brightkite` / `snap_gowalla`。

## 运行

```powershell
python main.py --stage 01                 # 或 python 01_discover/01_discover.py
```

## 口径要点

- **多数据集项目**：阶段内按 `<dataset>/` 分目录（规范 §1 注）。
- SNAP 源数据为 `.txt.gz`：datakit 的 `SUPPORTED_FORMATS` 不含 `txt`，本阶段显式纳入扫描。
- MD5 / 行数默认关闭（`datakit.yaml` 的 `options.with_md5=false`、`count_rows=false`）：
  sz_bike 有 2.5 万个文件、29 GB，全量指纹成本过高。
- 每章开头必须标注许可状态：fdic 公共领域可商用；sz_bike 研究用途且源已停更；
  SNAP 两个数据集**仅限研究、不允许商用、不再分发原始文件**。
