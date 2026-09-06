# 01_discover · ① 采集

> 规范：`datakit/PROJECT_STRUCTURE.md` §2-①。入口文件与目录同名：`01_discover.py`。

## 做什么

只读扫描源数据目录，回答「我手上到底有什么数据」：文件清单、体积、格式/目录分布、
数据集分组，以及**跨年文件的列结构漂移**（SOD 逐年增减字段，跨年拼接前必须查）。

## 输入

- `../data_raw/fdic/fdic_sod_1994..2025.csv`（32 个年度文件，约 1.6 GB，**只读，任何脚本不得写入**）

## 输出

| 文件 | 说明 |
| --- | --- |
| `output/catalog.yaml` | 机读清单（总览 / 格式分布 / 目录分布 / 分组 / 列漂移） |
| `output/catalog.md` | 人读清单（**先看这份**） |
| `output/files.csv` | 文件级明细：路径、格式、大小、行数、列数、列名、修改时间 |

## 口径

- `with_md5` / `count_rows` 由根 `datakit.yaml` 的 `options` 控制（当前：MD5 关、行数开）。
- 分组规则：文件名中连续数字归一为 `#`（`fdic_sod_1994.csv` → `fdic_sod_#`）。

## 怎么跑

```powershell
python main.py --stage 01        # 从项目根
python 01_discover/01_discover.py  # 或直接单跑
```
