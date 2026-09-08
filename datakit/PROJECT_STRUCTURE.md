# datakit 项目结构规范（v2）

> 状态：**已拍板，待落地**。本文定义「一个具体数据产品项目」的标准目录结构、
> 五个阶段各自的产物清单，以及人/datakit 的分工。
> 落地动作见 §7。

## 0. 决策记录

| 项 | 结论 |
| --- | --- |
| 阶段入口 | **入口文件与目录同名**（`01_discover/01_discover.py`），暴露 `run(project) -> dict` 函数 |
| 过程数据位置 | **随报告放各阶段 `output/`**，不设集中的 `work/` |
| 配置格式 | **YAML**（需为 datakit 增加 `pyyaml>=6.0` 依赖） |
| 探索区 | **不设 `notebooks/`** |

相对最初方案的修正：补齐缺失的 `clean` 阶段、拆分 `data_raw/`（只读）与过程数据、
每个阶段补 `README.md`、`README.d` → `README.md`、新增 `config/` 与 `logs/`。

## 1. 目录结构

```text
project_xxx/
├── README.md                    # 立项文件：背景/创新点/数据可信度/空间大数据作用/可行性/运行/目录导航（见 §9）
├── main.py                      # 根编排：加载五个阶段，依次调用 run(project)
├── SUMMARY.md                   # 自动生成：五阶段结论一页纸
├── datakit.yaml                 # 项目元信息：名称、数据源根、目标分组、离群阈值
│
├── config/                      # ★ 口径外置：改口径不改代码
│   ├── schema.yaml              # 字段规格：角色 + 等级(必需/重要/可选/忽略) + 业务规则
│   ├── clean_plan.yaml          # ③ 清洗计划
│   ├── mapping.yaml             # ⑤ 映射方案
│   └── assertions.yaml          # ④ 校验断言
│
├── data_raw/                    # ★ 只读源数据，任何脚本都不得写入
│   └── README.md                # 数据来源、获取方式、字段口径、授权、更新频率、可信度评估
│
├── 01_discover/                 # ① 采集（入口文件与目录同名）
│   ├── 01_discover.py           # def run(project) -> dict
│   ├── README.md                # 本阶段做什么、输入什么、看哪份报告
│   └── output/
│       ├── catalog.yaml         # 机读清单
│       ├── catalog.md           # 人读清单
│       └── files.csv            # 文件级明细表
│
├── 02_profile/                  # ② 画像
│   ├── 02_profile.py
│   ├── README.md
│   └── output/
│       ├── profile.yaml / profile.md
│       ├── fields.csv           # 字段清单（含等级）
│       ├── nulls.csv            # 空值表
│       ├── outliers.csv         # 极端值 / 异常值表
│       └── violations.csv       # 不符合业务 / 产品需求的值
│
├── 03_clean/                    # ③ 清洗
│   ├── 03_clean.py
│   ├── README.md
│   └── output/
│       ├── clean_report.md      # 决策 + 结果汇总
│       ├── decisions.yaml / decisions.md
│       ├── impact.yaml          # 按操作 / 按字段的影响
│       ├── filled_by_field.csv  # 填充了多少、涉及哪些字段
│       ├── dropped_by_field.csv # 删除了多少、涉及哪些字段
│       └── cleaned.csv          # 过程数据（可重建）
│
├── 04_validate/                 # ④ 校验
│   ├── 04_validate.py
│   ├── README.md
│   └── output/
│       ├── validation.yaml / validation.md   # 断言结果（P0/P1/P2）
│       ├── comparison.yaml / comparison.md   # 前后对比 + 建议
│       └── before_after.csv                  # 逐字段前后对比表
│
├── 05_map/                      # ⑤ 映射
│   ├── 05_map.py
│   ├── README.md
│   └── output/
│       ├── map.yaml / map.md
│       ├── lineage.csv          # 字段血缘：输出字段 ← 来源字段 / 表达式
│       ├── fields.csv           # 映射后字段数据报告
│       └── mapped.csv           # 过程数据（交付下游）
│
├── 06_<ext>/                    # ★ 扩展阶段（插件）：课题专属下游，NN ≥ 06，见 §8
│   ├── 06_<ext>.py              # 与内置阶段同构：run(project) -> dict（文件名与目录同名）
│   ├── README.md
│   └── output/                  # metrics / manifest / 图表 / 结论
│
└── logs/
    └── pipeline.log             # 每次运行的阶段摘要与时间戳
```

> **多数据集项目**（如教学类项目，一套流程跑 N 个数据集）：阶段内按数据集再分一层，
> 即 `NN_<stage>/output/<dataset>/...`，全局产物（跨数据集对比、总结论）直接放
> `NN_<stage>/output/`，不套数据集目录。

**数据流向**

```text
data_raw/ ──▶ 01_discover（只读扫描）
          ──▶ 02_profile （读源数据 → 画像）
          ──▶ 03_clean   （读源数据 → output/cleaned.csv）
                              │
          ┌───────────────────┴───────────────────┐
          ▼                                       ▼
   04_validate（读 03 的 cleaned.csv         05_map（读 03 的 cleaned.csv
              + 02 的 profile）                     → output/mapped.csv）
```

## 2. 五个阶段的「报告必须有什么」

每阶段的报告内容固定，换数据集只换 `config/`。

### ① `01_discover` —— 采集报告

回答："我手上到底有什么数据。"

| 报告块 | 具体内容 |
| --- | --- |
| 总览 | 扫描根、扫描时间、文件总数、**总体积（字节 + 人类可读）**、分组数 |
| 格式分布 | 每种格式（csv/json/xml/xlsx/rdf…）的文件数、体积占比 |
| 目录分布 | 每个子目录的文件数、体积、涉及格式 |
| 数据集分组 | 分组名、文件数、格式、**总体积、总行数、列数、列名** |
| 组内结构一致性 | 同组文件的**列结构漂移**（新增列 / 缺失列），跨年数据尤其关键 |
| 文件级明细 | 路径、格式、**大小**、**行数**、**列数**、列名、**修改时间**、MD5（可选） |

### ② `02_profile` —— 画像报告

回答："字段有哪些、哪些必需、数据质量有多差。"

| 报告块 | 具体内容 |
| --- | --- |
| 字段清单 | 字段名、类型、角色、**等级（必需/重要/可选/忽略）**、非空数、缺失率、唯一值、问题数、说明 |
| 等级分布 | 必需 N 个 / 重要 N 个 / 可选 N 个 / 忽略 N 个 |
| 空值分析 | 缺失数、缺失率、**按角色解释的语义**（主键缺失=缺陷、事件缺失=右删失）、处理建议 |
| 描述性统计 | 数值：min/p01/q1/median/q3/p99/max/mean/std、**负值率、零值率**；类别：Top-N 分布；时间：范围 |
| **极端值 / 异常值** | 检测方法（IQR / z-score / MAD）、逐字段异常数、上下界、Top-N 明细 |
| **规则违规** | **不符合实际 / 产品 / 项目需求的值**：字段、等级、严重度、规则、违规数、占比、样本 |

> 异常值 = **统计意义**上的离群；规则违规 = **业务意义**上的不合法。两者都报但分开列。
>
> **字段清单里的「角色 / 等级」必须有判定依据，不能只贴枚举**：角色的语义、等级的判定
> 标准、以及「为什么这个字段能列为主键」的判据，统一见 §3.5。画像阶段要逐字段把
> 「为什么是这个等级 / 角色」用一句话写进 `fields.csv` 的说明列，而不是让读者自己猜。

### ③ `03_clean` —— 清洗报告（决策 + 结果）

回答："动了哪些数据、为什么动、动了多少。"

| 报告块 | 具体内容 |
| --- | --- |
| 决策日志 | 步骤、动作（drop_na/fill/clip/replace/winsorize/drop_duplicates/astype/drop_columns/filter）、字段、**原因**、影响行数、处理前→处理后、是否可逆、被删行索引 |
| 形状变化 | 行数 前→后→删除数→删除率；列数 前→后→删除的列 |
| 缺失单元格 | 清洗前空单元格数 → 清洗后 → 填充了多少 |
| **按字段影响** | 每个字段：填充数、截断数、缩尾数、替换数、**因该字段删除的行数**、类型转换 |
| 按操作影响 | 每种动作执行次数、累计影响行数 |

> **每条决策必须写「为什么」，不能只报「删了多少 / 填了多少」**。判断框架（供人拍板时对齐）：
>
> | 动作 | 触发条件 | 判据（为什么可以 / 必须这样做） |
> | --- | --- | --- |
> | `drop_na`（删行） | `required` / `key` 字段缺失，且无法可信重建 | 主键缺失 = 记录无法定位 / 关联，保留反而污染下游 join |
> | `drop_columns`（删列） | 字段被判 `ignore`，或纯冗余 / 纯转码 | 与课题无关的列不进下游，减少噪声与口径歧义 |
> | `fill`（填充） | `optional` / `important` 缺失，且有合理代理值 | 用统计量 / 前值补以保样本量；**绝不对主键 / 坐标 / 事件时间填充** |
> | `to_null`（越界置空） | 值非法（越界 / 负值）但无法判定真值 | 置空保留「未知」；**截断会伪造一个看似合理的位置 / 数值** |
> | 保留缺失（不管） | 缺失本身有业务语义，或 `optional` 可接受 | 如「关闭时间缺失 = 右删失」，填充反而是错的 |
>
> 明令禁止：对空间列、主键、事件时间做「编造式」填充或截断（④ 复核是否真的没执行）。

### ④ `04_validate` —— 校验报告（断言 + 前后对比 + 建议）

回答："洗得对不对、能不能进下一步。"

| 报告块 | 具体内容 |
| --- | --- |
| 断言结果 | 名称、**严重度（P0 阻断 / P1 / P2）**、实际值、期望值、通过与否；按严重度汇总，是否存在阻断项 |
| 整体前后对比 | 行数、空单元格数、整体缺失率、异常值数、规则违规数：前 → 后 → 变化 |
| **逐字段前后对比** | 缺失率、异常值数、唯一值、均值/中位数、类型：前 → 后 → 变化量（即阶段 2 vs 阶段 3） |
| 清洗效果评估 | 关联 03 的影响汇总：填充了多少、删了多少，是否过度 |
| **建议清单** | 分级可操作建议（见 §3.4） |
| 必要字段核验 | 所有 `required` 字段的缺失率、违规数、能否进入下一步 |

### ⑤ `05_map` —— 映射报告

回答："原始字段怎么变成分析字段，映射后的数据长什么样。"

| 报告块 | 具体内容 |
| --- | --- |
| 操作明细 | 步骤、操作（rename/derive/bin/onehot/code/aggregate/geocode/drop）、对象、结果、原因 |
| **字段血缘** | 输出字段 ← 来源字段 / 表达式 / 映射方式 |
| 形状变化 | 行数、列数 前→后，新增列、删除列 |
| **映射后字段数据报告** | 逐字段：类型、来源、非空数、缺失率、唯一值、描述性统计或 Top-N 分布 |
| 产出数据 | `mapped.csv` |

> **映射阶段必须额外回答三件事**（缺一不可）：
>
> 1. **坐标缺失 / 地理编码失败的可信度**：明确报告有多少行因坐标缺失 / 越界 / H3 编码失败
>    而 **H3 格为空**，这些行如何进入下游（置空 = 不计入空间 exposure / 单独标记 / 剔除），
>    以及它对下游估计与训练的**可信度**量化影响。坐标缺失比例必须与「EXACT 坐标占比」
>    「<1 km 环是否失真」这类敏感性口径对照说明——**不能只报一个「置空」就交差**：
>    置空的 H3 意味着该观测失去空间位置，若被当作 0 强度会低估效应，若被剔除会改变样本构成，
>    两者都要量化到行数与占比。
> 2. **映射如何支撑研究**：说清 `mapped.csv` 生成了哪些分析变量（结果变量、exposure 强度、
>    对照口径），以及「空间特征 vs 区域 one-hot」这类 L1 设计取向**由映射决定**，直接决定
>    ⑥⑦⑧ 能回答什么、不能回答什么。
> 3. **字段血缘为什么需要**：`lineage.csv` 保证每个输出字段可追溯到来源字段 / 表达式 /
>    映射方式，支撑复现、口径审计与「结论漂移」定位（哪个字段的哪种变换导致结论变化）。

## 3. `config/`：人来定「意图」，机器补「事实」

机器负责**从数据里量得出来的东西**（类型、取值范围、枚举、缺失率）；
人负责**产品意图**（这个字段有多重要、允不允许缺、什么值算不合法）。

### 3.1 三个层次

| 层次 | 内容 | 谁写 |
| --- | --- | --- |
| **事实层**（可测量） | dtype、唯一率、枚举取值集合、min/max、缺失率、是否主键候选 | **机器自动推断** |
| **判断层**（业务取舍） | 角色、**等级（必需/重要/可选/忽略）**、规则阈值 | **机器给建议 + 人拍板** |
| **意图层**（纯业务） | 字段说明、清洗策略（删 vs 填）、**映射方案** | **人写** |

### 3.2 四类配置的归属

| 文件 | 机器 | 人 |
| --- | --- | --- |
| `schema.yaml` | 出初稿：角色、类型、枚举、范围、**建议等级**（带置信度） | 定等级、补规则阈值、写说明 |
| `clean_plan.yaml` | 按「等级 + 缺失率」推荐：required 缺失→`drop_na`；optional 缺失→`fill`；越界→`clip` | 确认或推翻每条 |
| `mapping.yaml` | 帮不上忙 | **全人写**（映射 = 产品想法） |
| `assertions.yaml` | 从 schema 规则**自动派生** | 补跨字段断言 |

结论：**「机器起草、人签字」的合约**，不是纯手工表单。

### 3.3 `schema.yaml` 示例

```yaml
# config/schema.yaml
fields:
  - name: order_id
    role: key              # key | event | time_varying | spatial | categorical | numeric | target | ignore
    level: required        # required | important | optional | ignore
    dtype: string
    description: 订单唯一编号，主键
    rules:
      - kind: not_null
      - kind: unique

  - name: amount
    role: numeric
    level: required
    dtype: numeric
    description: 订单金额（元）
    rules:
      - kind: non_negative
        message: 金额不能为负
      - kind: range
        min: 0
        max: 10000000

  - name: lat
    role: spatial
    level: important
    dtype: numeric
    description: 发生地纬度
    rules:
      - kind: geo_lat      # 内置：[-90, 90]

  - name: closed_at
    role: event
    level: required
    dtype: datetime
    description: 关闭时间，缺失表示尚未发生
    rules:
      - kind: no_future_date
```

**YAML 书写注意**

- 一律使用 `yaml.safe_load` / `safe_dump`，禁止 `!!python/object`（防任意代码执行）。
- 正则、日期、表达式必须加引号：`pattern: '^\d{4}-\d{2}-\d{2}$'`。
- 写初稿时 `sort_keys=False`、`allow_unicode=True`，保持可读的键顺序与中文。

### 3.4 机器反过来校验人的口径

配置写完不是终点，流水线会拿数据检验它：

| 检查 | 触发的处理 |
| --- | --- |
| `schema.yaml` 声明的字段在数据里不存在 | 阶段 2 报「字段缺失」警告（拼写错误 / 数据源变了） |
| 数据里有字段但 schema 未声明 | 阶段 2 默认按 `optional` 处理，并提示「未登记字段」 |
| `required` 字段缺失率 > 0 | 阶段 4 给 **P0 阻断建议**：补数据源，或降级该字段 |
| `required` 字段存在规则违规 | 阶段 2 违规表 + 阶段 4 建议清单同时高亮 |
| 清洗后 `required` 字段仍缺失 | 阶段 4 建议「还原并用更温和的策略重洗」 |
| 删除行比例 > 5% | 阶段 4 给 P1 建议：改用填充 / 标记而非删除 |
| 某字段填充量 > 50% | 阶段 4 给 P1 建议：增加「是否填充」标记列，避免污染分布 |
| 必要字段仍有异常值 | 阶段 4 给 P2 建议：缩尾或分箱 |

### 3.5 字段角色与等级：语义 + 判定依据

`schema.yaml` 里的 `role` 与 `level` 是整套口径的起点，不能只写枚举不给解释。
画像阶段要把「为什么是这个等级 / 角色」写进 `fields.csv` 的说明列。统一语义与判据如下。

**角色（role）——这个字段是什么**

| role | 含义 | 典型空值语义 |
| --- | --- | --- |
| `key` | 标识 / 主键候选：唯一、非空、跨时间稳定，用于定位记录与 join | 缺失 = 记录无法定位（缺陷） |
| `event` | 事件时间（发生 / 关闭 / 到期） | 缺失 = 事件尚未发生（右删失） |
| `time_varying` | 随时间变化的属性（面板年份、期末值） | 缺失 = 该期未观测 |
| `spatial` | 空间列（经纬度 / 地理编码 / H3 格 / 区域码） | 缺失 = 空间位置未知，影响聚合与邻接 |
| `categorical` | 类别 / 枚举列 | 缺失 = 类别未知 |
| `numeric` | 数值列（连续 / 离散量） | 缺失 = 数量未知 |
| `target` | 结果变量（模型要解释的 Y） | 缺失 = 样本无法进入估计 |
| `ignore` | 与课题无关，不进入分析 | 缺失 = 无所谓 |

**等级（level）——这个字段有多重要**

| level | 含义 | 缺失时的默认态度 |
| --- | --- | --- |
| `required` | 必需：缺它记录不可定位 / 结论不可得 | `drop_na` 或阻断，绝不含糊 |
| `important` | 重要：直接影响结论核心，缺失须处理 | 填充 / 置空 / 标记，可容忍少量缺失 |
| `optional` | 可选：锦上添花，缺了不影响主结论 | 可填可不填，缺失可接受 |
| `ignore` | 忽略：与课题无关 | 画像后放下不管 |

**判定依据——为什么是这个等级（按顺序问）**

1. **业务必需性**：缺这个字段，研究问题还能不能回答？不能 → `required`；勉强 → `important`。
2. **是否主键 / 定位**：能否唯一、稳定地定位一条记录？能 → `key` + `required`。
3. **是否结果变量**：是模型要解释的 Y → `target` + `required`。
4. **是否核心解释变量**：直接进入模型的 X → `required` 或 `important`，按课题取舍。
5. **是否承担空间结构**：参与聚合 / 邻接 / 距离 → `spatial` 起步 `important`，坐标缺失会破坏空间结构。
6. **是否纯冗余 / 无关**：与课题无关或纯转码 → `ignore` / `optional`。

**主键判据——为什么这个字段能列为主键（必须逐条满足）**

1. **唯一性**：列内唯一值 ≈ 行数（或与键组合唯一）。
2. **非空性**：缺失率 ≈ 0。
3. **稳定性**：跨时间 / 跨文件不漂移（跨年数据尤其要验；值会被复用 / 重分配的字段不能作键）。
4. **业务标识**：能对应真实实体，且不会被重新分配。

> 反例（FDIC）：`BRNUM` 表面唯一，但跨年会变化，**不能作跨年追踪键**，改用 `UNINUMBR`。
> 这就是「主键判据」第 3 条稳定性的一票否决——**唯一 ≠ 稳定**。

## 4. 阶段入口：入口文件与目录同名

### 4.1 约定

每个阶段目录内放**与目录同名的入口文件**（`01_discover/01_discover.py`），
**必须暴露 `run(project) -> dict`**：

```python
# 01_discover/01_discover.py
from pathlib import Path
import datakit as dk

STAGE = "01_discover"
OUT = Path(__file__).resolve().parent / "output"


def run(project: "dk.Project") -> dict:
    """被根 main.py 编排调用；返回本阶段摘要，供 SUMMARY.md 汇总。"""
    catalog = dk.scan(project.source_root, with_md5=project.with_md5,
                      count_rows=project.count_rows)
    project.write_stage(STAGE, catalog, tables={"files": catalog.to_frame()})
    return {"stage": STAGE, "file_count": len(catalog),
            "group_count": len(catalog.groups)}


def main():
    project = dk.Project.load(Path(__file__).resolve().parent.parent)
    print(run(project))


if __name__ == "__main__":
    main()
```

### 4.2 调用方式

| 目的 | 命令 |
| --- | --- |
| 单跑一个阶段 | `python 01_discover/01_discover.py` |
| 单跑（先进入阶段目录） | `cd 01_discover && python 01_discover.py` |
| 全流水线 | `python main.py` |
| 全流水线（单阶段） | `python main.py --stage 03` |
| 跑扩展阶段（插件） | `python main.py --stage 06` 或 `python 06_<ext>/<目录名>.py` |

### 4.3 技术约束：数字前缀不是合法模块名

目录名 `01_discover` 带数字前缀，**不是合法的 Python 标识符**，因此：

- ✅ `python 01_discover/01_discover.py` —— 可用（按文件路径直接执行）
- ✅ `importlib` 按文件路径加载 —— 可用（根 `main.py` 采用，见下）
- ❌ `python -m 01_discover` —— **不可用**（模块名不能以数字开头）
- ❌ `import 01_discover` —— **不可用**（语法错误）
- ❌ `python 01_discover/` —— **不可用**（目录当脚本执行依赖 `__main__.py`，本规范已不再使用）

> 入口文件名与目录同名，是为了在 IDE / 终端里一眼看出「这个文件属于哪个阶段」，
> 避免打开多个 `__main__.py` 时全靠标签页路径分辨。

因此根 `main.py` 用 `importlib` 按文件路径加载：

```python
# main.py
import argparse
import importlib.util
import sys
from pathlib import Path

import datakit as dk

STAGES = ["01_discover", "02_profile", "03_clean", "04_validate", "05_map"]


def load_stage(root: Path, name: str):
    """按文件路径加载阶段模块（绕开数字前缀不能 import 的限制）。"""
    path = root / name / f"{name}.py"          # 入口文件与目录同名
    spec = importlib.util.spec_from_file_location(f"_stage_{name}", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--stage", default=None, help="01|02|03|04|05，缺省跑全流程")
    ap.add_argument("--draft", action="store_true", help="只生成 config 初稿后退出")
    args = ap.parse_args()

    root = Path(__file__).resolve().parent
    project = dk.Project.load(root)

    if args.draft:
        print(project.draft_configs())
        return

    stages = STAGES if args.stage is None else [
        s for s in STAGES if s.startswith(args.stage)
    ]
    summaries = [load_stage(root, s).run(project) for s in stages]
    print(project.write_summary(summaries))


if __name__ == "__main__":
    main()
```

## 5. 命名与约定

| 对象 | 规范 | 示例 |
| --- | --- | --- |
| 阶段目录 | `NN_<模块名>`，与 datakit 模块同名，目录名即入口名 | `01_discover` `03_clean` |
| 阶段入口 | 与目录同名的 `.py`，暴露 `run(project) -> dict` | `02_profile/02_profile.py` |
| 阶段产出 | 一律进 `output/`，不散在阶段根目录 | `02_profile/output/profile.md` |
| 报告（机读） | YAML，与 config 统一 | `catalog.yaml` `impact.yaml` |
| 报告（人读） | Markdown | `profile.md` `clean_report.md` |
| 报告（明细表） | CSV，便于再分析 | `files.csv` `before_after.csv` `lineage.csv` |
| 过程数据 | 与报告同目录，名字带状态 | `cleaned.csv` `mapped.csv` |
| 配置 | `config/*.yaml`，与 datakit 的 `from_spec` 一一对应 | `clean_plan.yaml` |
| 配置初稿 | `*.draft.yaml`，与正式配置并列便于 diff | `schema.draft.yaml` |
| 源数据 | `data_raw/` 只读，禁止任何写入 | — |
| 扩展阶段目录 | `NN_<ext>`，**NN ≥ 06**，与内置五阶段同构 | `06_train` `07_visualize` |
| 扩展阶段配置 | `config/<ext>.yaml`（可选，口径较多时才建） | `config/train.yaml` |
| 扩展阶段产出 | 一律进本阶段 `output/`，禁止回写上游阶段 | `06_train/output/metrics.json` |

## 6. 项目侧 vs datakit 侧的分工

| 谁 | 负责 |
| --- | --- |
| **datakit（SDK）** | 五步算法、报告对象（`to_report` / `to_markdown`）、`Project.init()` 脚手架、`Project.load()` / `run()` 编排、YAML 配置解析与初稿推断 |
| **项目侧（人写）** | 4 件事：① `config/` 里的口径（字段等级、规则、清洗计划、映射方案、断言）② `data_raw/README.md` 的数据说明 ③ 各阶段的 `run()` 函数体（通常 5～10 行）④ 项目 `README.md` 的业务叙述 |

项目侧**不写**任何统计 / 清洗 / 映射算法。

## 7. 落地计划

1. **新增 `datakit/schema.py`**：`FieldLevel`（必需/重要/可选/忽略）+ `FieldSpec` + `Rule`，产出「规则违规」表（阶段 2 需要、现有代码没有）。
2. **增强五个模块的报告**：
   - `discover`：体积、格式分布、目录分布、修改时间、组内列结构漂移
   - `profile`：字段等级、极端值统计、规则违规表
   - `clean`：按操作 / 按字段的影响汇总（填充数、删除行数）
   - `validate`：逐字段前后对比、分级建议清单、必要字段核验
   - `map`：字段血缘、映射后字段数据报告
3. **新增 `datakit/project.py`**：`Project.init()` 生成完整骨架（含各阶段 `README.md` 与配置模板），`Project.load()` / `run()` / `write_stage()` / `write_summary()`。
4. **YAML 支持**：`pyyaml>=6.0` 加入主依赖，`report.py` 增加 YAML 写出。
5. **补测试并同步文档**：`tests/test_schema.py`、`tests/test_project.py`，更新 `README.md` / `通用规范.md` / `DEVELOPMENT_GUIDE.md`。
6. **扩展阶段（§8）支持**：`project.py` 解析 `datakit.yaml` 的 `extensions`，`main.py` 把它并入 `STAGES`；`Project.load()` 校验 `depends_on` / `requires` 是否满足，并对 `blocking: false` 的失败降级为告警。

## 8. 扩展阶段（插件）规范

> 内置五阶段（`01`–`05`）是**通用数据底座**，产物终点是 `05_map/output/mapped.csv`。
> 但真实课题在这之后还有「建模 / 估计 / 可视化 / 结论 / 教学素材」这类**课题专属**动作，
> 它们不该塞进 datakit 内核，也不该散在项目根目录（如 `step5_estimate.py`、`model.py`、`viz.py`）。
> 统一收敛为**扩展阶段（插件）**。

### 8.1 定位与边界

| 项 | 内置五阶段 `01`–`05` | 扩展阶段 `NN ≥ 06` |
| --- | --- | --- |
| 归属 | datakit 内核，跨项目通用 | 项目侧自有，课题专属 |
| 数量 | 固定 5 个 | 任意，按执行顺序编号 |
| 输入 | `data_raw/` + 上游 `output/` | **只读** `05_map/output/mapped.csv`、`data_raw/`、其它阶段 `output/` |
| 输出 | 结构化报告（yaml/md/csv） | 模型、指标、图表、结论稿 |
| 依赖 | datakit 主依赖 | 可声明可选依赖 `extras`（modeling / geo / …） |
| 失败影响 | 阻断后续阶段 | **默认不阻断**五阶段（`blocking: false`），但必须写进 `SUMMARY.md` |
| 是否进 datakit | 是 | 否（跑通后可沉淀为内核模块，见 §8.7） |

硬约束：**扩展阶段禁止回写上游阶段的 `output/`**，只能读；自己的产物只进本阶段 `output/`。

### 8.2 目录与文件

```text
06_<ext>/
├── 06_<ext>.py        # 必须暴露 run(project) -> dict，签名与内置阶段一致（文件名与目录同名）
├── README.md          # 本阶段做什么、依赖哪个上游产物、需要哪个 extras、看哪份产出
└── output/            # 产物（可视化阶段：figures/*.png|pdf + manifest.json，见 §8.8）
```

可选辅助模块（`helpers.py` / `figures.py` / …）放在阶段目录内，**不允许**在项目根目录堆脚本。

### 8.3 入口契约

```python
# 06_train/06_train.py
from pathlib import Path

STAGE = "06_train"
OUT = Path(__file__).resolve().parent / "output"


def run(project) -> dict:
    """只读上游 05_map/output/mapped.csv；返回摘要供 SUMMARY.md 汇总。"""
    mapped = project.stage_output("05_map") / "mapped.csv"
    ...
    return {"stage": STAGE, "blocking": False, "artifacts": [...]}


def main():
    ...
```

`main.py` 用同一套 `importlib` 按文件路径加载（数字前缀同样不能 `import`），
阶段清单 = 内置五阶段 + `datakit.yaml` 里登记的 `extensions`。

### 8.4 在 `datakit.yaml` 登记

```yaml
extensions:
  - stage: 06_train          # 目录名，NN ≥ 06
    kind: modeling           # modeling | visualization | conclusion | teaching | custom
    depends_on: [05_map]     # 只读这些阶段的 output/
    requires: [mapped.csv]   # 上游必备文件，缺失则本阶段拒绝启动并给出明确报错
    extras: [modeling]       # 可选依赖组：uv run --extra modeling
    blocking: false          # 失败是否阻断整条流水线
    outputs: [metrics.json, logit_pipeline.pkl]
```

### 8.5 报告最低要求（比内置阶段减配，但不许没有）

| 类别 | 必须有 | 说明 |
| --- | --- | --- |
| **建模 / 估计** | `metrics.json`（指标）+ `replication_manifest.json`（版本 / 参数 / 随机种子 / 输入指纹） | 没有 manifest = 不可复现 = 不算产出 |
| **可视化** | `manifest.json`（图清单：文件名 → 标题 → 口径 → 来源产物 → alt_text）+ `figures/*.png|pdf` | 每张图必须能追溯到哪份数据；字段结构见 §8.8.5，出图要求见 §8.8 |
| **结论** | `conclusion.md`（结论 + **已知限制 / 止损条件**）+ `conclusion_report.json` | 结论必须带约束，见各项目 README 的「已知限制」 |
| 通用 | 机读（json/yaml）+ 人读（md）各一份 | 与内置阶段一致 |

### 8.6 三个项目的落地映射

| 项目 | 根目录散落脚本（现状） | 收敛为扩展阶段 |
| --- | --- | --- |
| `project1_fdic_spatial` | `step5_estimate.py` / `step6_visualize.py` / `step7_conclude.py` | `06_estimate` / `07_visualize` / `08_conclude` |
| `project2_fdic_survival` | `model.py` / `viz.py` | `06_train` / `07_visualize` / `08_conclude` |
| `project6_spatial_teaching` | （全部在 `main.py` 内） | `06_visualize` / `07_conclude`（阶段内按 `<dataset>/` 分目录） |

> 迁移原则：**先建目录、登记映射，数据暂不搬迁**。旧产物留在原 `output/` 下，
> 各阶段 `README.md` 中标注「迁移前实际位置」，脚本逻辑逐阶段搬入与目录同名的入口文件
> （如 `06_train/06_train.py`）。

### 8.7 沉淀路径

扩展阶段跑通并被 ≥2 个项目复用了，才考虑升级为 datakit 内核模块
（如 `datakit.model` / `datakit.viz`），届时编号并入内置五阶段之后并提升 `extras` 为默认依赖。

### 8.8 可视化出图规范（选型 / 中文 / 落盘）

> 适用：所有 `kind: visualization` 的扩展阶段（以及内置阶段里顺手画的参数检查图）。
> 目标：**一眼看懂结论，且能追溯到哪份数据、哪行代码**。

#### 8.8.1 先选对图，再谈美化

| 要回答的问题 | 首选 | 次选 | 不要这样画 |
| --- | --- | --- | --- |
| 单变量分布 | 直方图 / ECDF | 箱线图 | 饼图 |
| 分组分布比较 | 分组箱线 / 山脊图 | 小提琴图 | 多张直方图硬叠 |
| 时间趋势 | 折线（≤ 5 条） | 小倍数 / 斜率图 | 双 Y 轴 |
| 生存 / 持续时间 | Kaplan–Meier 阶梯 + 置信带（标 at-risk） | Nelson–Aalen 累计风险 | 忽略删失的普通折线 |
| 两变量关系 | 散点 + 回归线 + `r` 注记 | 六边形分箱（> 5k 点） | 无透明度的原始散点 |
| 空间分布 | 分级统计（choropleth）/ H3 网格聚合 | 六边形分箱填色 | 上万点原始散点 |
| 构成（≤ 5 类） | 排序条形 / 百分比堆叠柱 | 堆叠面积 | > 5 类的饼图、3D 饼 |
| 排名 | 排序条形图 | 棒棒糖图 | 用折线表示排名 |
| 模型结果 | 系数森林图（点 + 95% CI） | 标准化后分组条 | 只给 p 值表 |
| 前后 / 两组对比 | 哑铃图 / 斜率图 | 配对条形 | 两张分开的图让人肉眼对齐 |

配色：默认 **Okabe–Ito / viridis** 色盲友好色板；强度用顺序色板，涨跌用发散色板（中心固定 0）；
**禁止红绿同现、禁止 jet 彩虹、禁止 3D**。

#### 8.8.2 标注简化：少即是多

| 元素 | 规则 |
| --- | --- |
| `title` | 写**结论**不写"字段名 vs 字段名"，≤ 20 字。例：`脆弱性越高，网点存活率越低` |
| 副标题 | 放口径与样本量，小一号字。例：`1994–2024，右删失计入风险集，n=12,345` |
| `xlabel` / `ylabel` | 只写「短名 + 单位」，单位进轴标签、不要重复到每个刻度。例：`存款（千美元）` |
| 刻度 | 千分位用 `k` / `M`；年份每 5 年一个刻度；**能横排就不旋转** |
| 图例 | ≤ 3 条系列时**在线尾直接标注**，取消图例；必须保留则放图外上方、去边框 |
| 网格 | 只留 y 轴浅灰水平线（`alpha=0.3`），去掉 x 网格、去掉上/右边框（despine） |
| 注记 | 只标**关键的那一个点**（峰值 / 拐点 / 政策年），带箭头；不要每个点都标数字 |
| 脚注 | 右下角小字：数据来源产物路径 + 生成时间，字号 8–9 |

反面清单：3D 效果、双 Y 轴、图例压住数据、默认彩虹色、旋转 45° 的刻度文字、全图铺满数值标签。

#### 8.8.3 中文显示：乱码 90% 是字体，不是编码

先分清两类问题，**不要一上来就把文件改成 GBK**：

1. **字形缺失（最常见）**：默认字体 DejaVu Sans 没有汉字 → 满屏"□□□"。解法是**换字体**。
2. **编码不匹配**：读外部文件/打印控制台时字节解释错了 → `UnicodeDecodeError` 或终端乱码。

统一做法：

```python
# -*- coding: utf-8 -*-        # ① 源码一律 UTF-8，禁止用 GBK 存 .py
import sys
from pathlib import Path

# ② 控制台乱码（Windows PowerShell 默认 GBK）：脚本开头重配 stdout
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
# 或在运行前：set PYTHONIOENCODING=utf-8   或   chcp 65001

# ③ 读外部数据：UTF-8 优先，GBK 系兜底（gb18030 是 GBK 超集，能读就别用 gbk）
def read_text(path: Path) -> str:
    for enc in ("utf-8-sig", "utf-8", "gb18030", "cp1252"):
        try:
            return path.read_text(encoding=enc)
        except UnicodeDecodeError:
            continue
    raise UnicodeDecodeError("all", b"", 0, 1, f"无法解码：{path}")
# pandas: pd.read_csv(p, encoding="utf-8-sig") 失败再试 encoding="gb18030"

# ④ 画图字体（关键）：本机实测可用的中文字体
import matplotlib as mpl
mpl.rcParams.update({
    "font.family": "sans-serif",
    "font.sans-serif": ["Microsoft YaHei", "SimHei", "Noto Sans CJK SC",
                        "Noto Sans SC", "KaiTi", "SimSun", "DejaVu Sans"],
    "axes.unicode_minus": False,   # 负号变方块的元凶
    "pdf.fonttype": 42,            # PDF 嵌入 TrueType，别人打开不缺字
    "ps.fonttype": 42,
    "svg.fonttype": "none",        # SVG 保留文本（可搜索/可再编辑）
    "figure.dpi": 110, "savefig.dpi": 200,
    "figure.facecolor": "white", "savefig.facecolor": "white",
})
```

- 装了新字体后要清一次缓存：`matplotlib.font_manager._load_fontmanager(try_read_cache=False)`。
- 出图前跑一次**自检图**：画一张只写「中文测试 中文测试 −2024」的图，确认不是豆腐块再批量出图。
- Linux / CI：装 `fonts-noto-cjk`，字体名换成 `Noto Sans CJK SC`。
- 把实际生效的编码与字体名写进 `manifest.json`（见 8.8.5），换机器时一眼知道差在哪。

#### 8.8.4 图片质量与落盘

| 项 | 约定 |
| --- | --- |
| 尺寸 | 单栏 `6×4 in`；宽图 / 时间轴 `10×4.5`；地图 `8×8`；小倍数每格 ≥ `2×2` |
| 分辨率 | 屏幕看 PNG @ 150–200 dpi；进报告/PPT @ 300 dpi |
| 字号 | title 13–15 / axis label 10–11 / tick 9 / annotate 9 / footnote 8（@ 6×4 in 基准） |
| 导出 | `fig.savefig(p, dpi=200, bbox_inches="tight", pad_inches=0.1, facecolor="white")` |
| 双格式 | 每张图同时出 `PNG`（看）+ `PDF`（矢量，进文档）；地图额外出 `SVG` |
| 命名 | `<序号>-<对象>-<图型>.png`，如 `03-km-by-fragility.png`；**禁止** `figure1.png` / `未命名.png` |
| 位置 | 统一 `NN_<ext>/output/figures/`，散在阶段根目录视为未完成（Tableau 导出的图同样落这里，见 §8.8.6） |
| 源文件 | 工作簿/工程文件另存 `NN_<ext>/assets/`，> 10 MB 不入库 |

**每图必带的 7 项信息**（缺一项不算完成；图内放 1–4，5–7 放 manifest）：

1. 标题是**结论**（不是字段名罗列）
2. 轴标签带**单位**
3. 样本量 `n=` 与**时间/空间范围**
4. **口径**：含不含删失、是否加权、是否截断、聚合层级（如 H3 r8 / 州）
5. 数据来源产物路径（如 `05_map/output/data/branch_panel.csv`）
6. 生成脚本 + 库版本 + 生成时间
7. 一句话 `alt_text`：这张图回答什么问题（≤ 25 字），供 README / 无障碍阅读复用

#### 8.8.5 `manifest.json` 结构（可视化阶段必交）

```json
{
  "generated_at": "2026-09-06T21:30:00+08:00",
  "generator": {
    "tool": "matplotlib", "version": "3.9.2",
    "script": "07_visualize/07_visualize.py",
    "encoding": "utf-8", "font": "Microsoft YaHei", "reproducible": true
  },
  "figures": [
    {
      "file": "figures/03-km-by-fragility.png",
      "pdf": "figures/03-km-by-fragility.pdf",
      "title": "脆弱性越高，网点存活率越低",
      "type": "km_curve",
      "question": "不同银行脆弱性分层的网点存活曲线是否有差异？",
      "alt_text": "三条 KM 曲线显示 L2 组存活率最低，20 年存活率约 45%",
      "source": "05_map/output/data/branch_panel.csv",
      "n": 12345,
      "scope": "1994–2024；右删失计入风险集；左截断已剔除",
      "unit": "x=年，y=存活率",
      "notes": "置信带为 95% CI；at-risk 表见同目录 km_at_risk.csv"
    }
  ]
}
```

`README.md` 里直接引用这份 manifest 生成图目录表，**不要手写第二份清单**（会漂移）。

#### 8.8.6 Tableau（本机 Public Edition）：出"好看的图"，图片必须落本地

本机：`E:\software_work\20260829tableau\bin\tabpublic.exe` = **Tableau Desktop Public Edition**。

| 能力 | 结论（以官方说明为准） |
| --- | --- |
| **本地保存工作簿** | ✅ 可以。`File → Save As` 存 `.twb` / `.twbx` 到本地（Public Edition 同时提供"发布到 Public"与"本地保存"两个选项，本地保存用于离线工作和不宜公开的数据） |
| **本地导出图片** | ✅ 可以。`Worksheet → Export → Image` 出 PNG；整份用 `File → Print to PDF` 出矢量 PDF，再按需转 300 dpi PNG |
| 脚本自动化出图 | ❌ 不行。bin 下只有 `tabpublic` / `tabprotosrv` / `tabcrash*`，无 `tabcmd`（那是 Tableau Server/Cloud 的工具）；Tableau 没有出图 CLI |
| 发布到 Public 云端 | 🟡 **可选，非必需**。发布即**公开**：任何人可查看、可下载工作簿与完整数据（可在 viz 设置里关掉下载） |
| 容量与连接 | 单工作簿 ≤ 1500 万行；连接器有限；不能连 Tableau Server / Cloud 私有站点 |

**项目内定位**：Tableau 出**汇报/展示用图**（好看、可交互、可分享），
Python 出**可复现图**（流水线批跑）。同一结论若两种图都有，以 Python 图为准（口径可复算）。

**本地出图 SOP（图片必须落本地）**

1. 数据源只连**已聚合的本地 CSV**（如 `05_map/output/data/branch_panel.csv`，或 `NN_<ext>/output/tableau/*.csv`），
   不连原始明细库、不连生产库。
2. 尺寸先定死再导出：仪表板用固定尺寸（推荐 `1600×900` 或 `1200×800`），避免导出后被拉伸模糊。
3. 导出：
   - 单图：`Worksheet → Export → Image` → PNG（存 `figures/`）
   - 汇报用：`File → Print to PDF` → 矢量 PDF（存 `figures/`），需要位图时再
     `magick -density 300 a.pdf a.png` 或 `pdftoppm -r 300 -png a.pdf a`
4. 落盘：图片一律 `NN_<ext>/output/figures/`（命名同 §8.8.4）；
   工作簿 `.twbx` 另存 `NN_<ext>/assets/`（> 10 MB 不入库，README 注明获取方式）。
5. 每张图登记进 `manifest.json`，标 `reproducible: false` + `human_steps`（人工步骤写清楚，别人才复现得了）。

**"好看"的硬要求（Tableau 端对齐 §8.8.2）**

- 工作表标题**写结论**并改掉默认 `Sheet 1`；副标题写口径 + `n=`。
- 轴标题带单位；数字格式统一（千分位 / 百分比 / 小数位），不用默认"自动"。
- 网格线只留必要的、颜色 `#E5E7EB`；去掉多余边框与零线噪音。
- 配色用 Tableau 内置**色盲友好**调色板，禁红绿同现、禁彩虹色。
- ≤ 3 条系列时用「标签 → 线尾」直接标注，**关掉图例**。
- Tooltip 写清：口径、`n`、单位、来源产物路径。
- 字体与 Python 图保持一致（微软雅黑 / 思源黑体）：标题 14–18、轴 10–12。

**manifest 登记（Tableau 出的图）**

```json
{
  "file": "figures/05-km-by-fragility.png",
  "pdf": "figures/05-km-by-fragility.pdf",
  "title": "脆弱性越高，网点存活率越低",
  "type": "km_curve",
  "alt_text": "三条生存曲线显示 L2 组 20 年存活率最低",
  "tool": "tableau-public",
  "workbook": "assets/fdic-survival.twbx",
  "reproducible": false,
  "human_steps": "连 05_map/output/data/branch_panel.csv → 建 KM 工作表 → Export Image @1600×900",
  "public_url": null,
  "source": "05_map/output/data/branch_panel.csv",
  "n": 12345,
  "scope": "1994–2024；右删失计入风险集"
}
```

**若选择发布（可选）：先过脱敏清单**

1. 只发布**已聚合**到分析粒度的数据，不含个人/机构可识别字段；
2. 发布后在 viz 设置里把「允许他人下载或制作副本」**关掉**（默认是谁都能下载工作簿和完整数据）；
3. 描述里写明数据出处、口径、时间范围与已知限制；
4. 发布成功后把链接填进 `manifest.public_url`，README 同时给出**本地 PNG 路径 + 线上链接**双通道；
5. 只想分享一张图、不想交出数据 → 不要发工作簿，直接把导出的 PNG 贴进 README / 报告。

## 9. 数据、立项与 README 的说明规范

> 报告回答「数据怎么样」，README 回答「为什么做、数据从哪来、靠不靠谱、能做什么」。
> 这两层缺一不可。**项目主 README 是立项文件**，不是运行说明的附注。

### 9.1 三层 README，各管一件事

| 文件 | 定位 | 必须写清 |
| --- | --- | --- |
| 项目主 `README.md` | **立项文件**：这个项目为什么成立 | 立项背景与研究问题、创新点、数据来源与可信度、空间大数据的作用、可行性、运行方式、结论与限制 |
| `data_raw/README.md` | 数据说明书 | 来源、获取方式、授权、更新频率、字段口径、可信度评估 |
| 各阶段 / 插件 `README.md` | 单点作用说明 | 本阶段 / 插件做什么（作用定位）、输入输出、依赖的上游产物、关键口径与决策理由 |

### 9.2 项目主 `README.md` 必含（立项六问）

1. **为什么做**：立项背景 + 研究问题（一句话可证伪的问题）。
2. **新在哪**：创新点 / 贡献，相对已有工作的差异（不是「用了空间方法」这么空）。
3. **数据哪来、靠不靠谱**：来源 + 可信度评估（权威性、覆盖、精度、已知缺陷，如 EXACT 坐标占比 < 100%）。
4. **空间大数据起什么作用**：为什么需要空间维度、空间结构（邻接 / 距离 / 网格）如何支撑结论、去掉空间维度结论还成立吗。
5. **做不做得了**：可行性论证（数据规模、字段是否支撑、方法是否可行）。
6. **怎么跑、结论、限制**：运行方式 + 目录导航 + 一句话结论 + 已知限制（含止损条件）。

### 9.3 `data_raw/README.md` 必含

数据来源、获取方式、授权 / 许可、更新频率、**逐字段口径**（含义 / 单位 / 编码），
以及**可信度评估**：覆盖范围、精度、缺失与已知偏差（这些是立项可行性论证的事实来源）。

### 9.4 各阶段 / 插件 `README.md` 必含

- **本阶段 / 插件的作用定位**：一句话讲清「这个插件解决哪一段」，不要只写「见代码」。
- 输入（依赖哪个上游 `output/` 的哪个文件）、输出（本阶段 `output/` 里的产物）。
- 关键口径与**决策理由**（为什么这么删 / 填 / 映射，指向对应阶段报告）。

## 10. 待确认

1. **`--draft` 自动生成配置初稿**是否实现？即机器从数据推断 `schema.draft.yaml`（角色 / 类型 / 枚举 / 范围 / 建议等级 + 置信度），并派生 `clean_plan.draft.yaml`、`assertions.draft.yaml`。不实现则 `config/` 需纯手写。
2. 报告机读格式统一为 **YAML**（与 config 一致）还是保留 **JSON**？
3. 阶段间数据交接：单阶段运行时，从 `data_raw/` 重跑上游，还是直接读上游 `output/*.csv`？
4. 扩展阶段失败时，除写入 `SUMMARY.md` 外，是否还需要在 `logs/pipeline.log` 中单独标注 `EXT_FAILED` 标记行？
