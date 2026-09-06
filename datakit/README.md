# datakit —— 通用数据处理 SDK

把「**数据采集 → 描述性统计 → 清洗 → 校验 → 映射**」五步提炼为可复用的通用方法，面向
`json` / `csv` / `xml` / `rdf` / `xlsx` 等常见数据格式，风格接近 `pandas` / `numpy`。

- 每步都有 **报告**（JSON + Markdown）与 **日志**，全程可追溯、可审计。
- **只读源数据**：SDK 从不写回源文件，所有产出落到调用方指定的输出目录。
- **目的驱动**：异常值 / 空值的判定取决于字段「角色」与清洗计划，不搞一刀切。

```python
import datakit as dk

# 1. 采集：扫描目录，识别并分组数据集（含指纹）
catalog = dk.scan("data_raw")

# 2. 描述性统计：字段画像 + 异常值 + 空值
ds = dk.read("data.csv")
profile = dk.profile(ds, roles={"SIMS_ACQUIRED_DATE": dk.Role.EVENT})

# 3. 清洗：每个动作写入决策日志
plan = dk.CleanPlan().drop_na(["BRNUM"]).fill("DEPSUMBR", method="median")
result = dk.clean(ds, plan)

# 4. 校验：清洗后画像 + 前后对比 + 建议
comparison = dk.compare(profile, dk.profile(result.dataset))

# 5. 映射：不同想法 → 不同映射方案
mapped = dk.map(result.dataset, dk.MappingScheme().rename({"lat": "latitude"}))

# 或一条命令跑完整流程（每步产出报告与日志）
wf = dk.Workflow("output").run("data_raw", group="fdic_sod_#", clean_plan=plan)
```

## 安装

使用 `uv`（推荐，Python 3.13）：

```powershell
cd datakit
uv sync --extra dev          # 安装依赖 + 本包（开发模式）
uv sync --extra modeling     # 建模可选依赖（statsmodels/sklearn/shap 等）
uv run --python 3.13 pytest  # 运行测试
```

或标准 pip：

```powershell
pip install -e ".[dev]"
```

可选依赖：

| extra | 用途 |
| --- | --- |
| `rdf` | RDF 读取（`rdflib`） |
| `geo` | H3 空间网格映射（`h3`） |
| `modeling` | 建模可选依赖：`statsmodels` / `scikit-learn` / `matplotlib` / `seaborn` / `shap` |
| `dev` | 测试（`pytest`） |

## 支持的数据格式

| 格式 | 扩展名 | 说明 |
| --- | --- | --- |
| CSV / TSV | `.csv` `.tsv` | 自动尝试多种编码（含 BOM / latin-1） |
| JSON / JSONL | `.json` `.jsonl` `.ndjson` | 数组或换行分隔，自动探测 |
| XML | `.xml` | 重复子元素 → 记录，属性/嵌套递归扁平化 |
| RDF | `.rdf` `.ttl` `.nt` `.n3` | 三元组 → `(subject, predicate, object)` |
| XLSX | `.xlsx` | 第一个 sheet |
| 压缩 | `*.gz` | 文本类文件的 gzip 包裹 |

## 五阶段流程

| 阶段 | 模块 | 关键 API | 产物 |
| --- | --- | --- | --- |
| ① 采集 | `datakit.discover` | `scan` / `discover` | `Catalog`（清单 + 指纹 + 分组） |
| ② 描述性统计 | `datakit.profile` | `profile` / `detect_outliers` / `null_summary` | `Profile`（字段画像 + 异常值 + 空值） |
| ③ 清洗 | `datakit.clean` | `CleanPlan` / `clean` | `CleanResult`（清洗数据 + 决策日志） |
| ④ 校验分析 | `datakit.validate` | `validate` / `compare` | `ValidationReport` / `ComparisonReport` |
| ⑤ 映射 | `datakit.map` | `MappingScheme` / `map` | `MapResult`（映射数据 + 报告） |

编排：`datakit.Workflow` 一条命令串起五步，自动落盘 `01_discover/` … `05_map/` 与 `pipeline.log`。

## 公共 API 一览

```python
# 核心
Dataset, Role, infer_roles, __version__

# 读写
read, read_csv, read_json, read_xml, read_rdf, read_xlsx, write, detect_format

# 采集
scan, discover, Catalog, Source

# 描述
profile, describe, detect_outliers, null_summary, Profile, FieldProfile

# 清洗
clean, CleanPlan, CleanAction, CleanResult, DecisionLog

# 校验
validate, compare, ValidationReport, CheckResult, ComparisonReport

# 映射
map, MappingScheme, MappingOp, MapResult

# 报告/编排
write_report, write_json, write_markdown, write_jsonl, Workflow
```

## 目录结构

```text
datakit/
├── pyproject.toml
├── README.md
├── 通用规范.md
├── DEVELOPMENT_GUIDE.md
├── datakit/
│   ├── __init__.py      # 公共 API
│   ├── core.py          # Dataset / Role / 异常
│   ├── io.py            # 多格式读写
│   ├── discover.py      # ① 采集/发现
│   ├── profile.py       # ② 描述性统计
│   ├── clean.py         # ③ 清洗 + 决策日志
│   ├── validate.py      # ④ 校验 + 对比
│   ├── map.py           # ⑤ 映射
│   ├── report.py        # 报告/日志写出
│   └── pipeline.py      # Workflow 编排
└── tests/               # 单元测试（合成数据）
```

## 许可与约束

- 仅本地开发使用；**不修改源数据、不修改系统环境、不修改工作空间外文件**。
- 详细规范见 `通用规范.md`，扩展开发见 `DEVELOPMENT_GUIDE.md`。
