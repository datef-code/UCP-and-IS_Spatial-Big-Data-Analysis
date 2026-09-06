# datakit 开发指引

本文档给**扩展本 SDK** 的开发者使用：模块职责、如何新增格式/清洗动作/映射操作/断言、
以及本地验证流程。通用规范见 `通用规范.md`，快速上手见 `README.md`。

## 1. 模块职责

| 模块 | 职责 | 关键类/函数 |
| --- | --- | --- |
| `core.py` | 数据容器、字段角色、异常 | `Dataset`、`Role`、`infer_roles` |
| `io.py` | 多格式读写、格式识别 | `read` / `read_*` / `write` / `detect_format` |
| `discover.py` | ① 采集：扫描、指纹、分组 | `scan`、`Catalog`、`Source` |
| `profile.py` | ② 描述性统计 | `profile`、`detect_outliers`、`null_summary` |
| `clean.py` | ③ 清洗 + 决策日志 | `CleanPlan`、`clean`、`DecisionLog` |
| `validate.py` | ④ 校验 + 前后对比 | `validate`、`compare` |
| `map.py` | ⑤ 映射 | `MappingScheme`、`map` |
| `report.py` | 报告/日志写出 | `write_report` / `write_json` / `write_markdown` |
| `pipeline.py` | 五步编排 | `Workflow` |

依赖方向：`pipeline → {discover, profile, clean, validate, map} → {core, io, report}`。

## 2. 环境准备

```powershell
cd datakit
uv sync --extra dev            # 创建 .venv 并安装依赖 + 本包（开发模式）
uv run --python 3.13 pytest    # 运行测试
uv run --python 3.13 python -c "import datakit; print(datakit.__version__)"
```

## 3. 新增一个数据格式

在 `io.py` 中：

1. 在 `_EXT_MAP` 增加扩展名 → 格式名映射。
2. 实现 `read_<fmt>(path) -> Dataset`，用 `Dataset(frame, DatasetMeta(...))` 包装。
3. 在 `read()` 的分派分支中登记。
4. 若需写出，在 `write()` 中登记（不支持的格式抛 `FormatNotSupportedError`）。
5. 可选依赖用「延迟 import + 带指引的 `ImportError`」模式（见 `read_rdf`）。

约定：读取器不吞异常，解析失败直接抛出，由调用方决定降级策略。

## 4. 新增一个清洗动作

1. 在 `clean.CleanPlan` 增加流畅方法（返回 `self`），生成一个 `CleanAction(op=...)`。
2. 在 `clean.clean()` 的分支中实现该 op，并 **必须** 调用 `log.add(...)` 写决策日志
   （影响行数、原值/新值概况、是否可逆）。
3. 在 `CleanPlan.from_spec` 登记对应配置键，便于口径外置。
4. 在 `tests/test_clean.py` 补一条用例。

## 5. 新增一个映射操作

1. 在 `map.MappingScheme` 增加流畅方法，生成 `MappingOp(op=...)`。
2. 在 `map.map()` 的分支中实现，并把操作明细追加到 `report`。
3. 在 `MappingScheme.from_spec` 登记配置键。
4. 在 `tests/test_map.py` 补用例。

## 6. 新增一个断言

在 `validate.validate()` 的 `check` 分派中新增分支即可；支持直接传 `callable` 做任意自定义断言。

## 7. 报告对象约定

需要「报告 + 日志」的对象统一实现两个方法：

- `to_report() -> dict` —— 机器可读结果。
- `to_markdown() -> str` —— 人读报告。

然后可直接交给 `report.write_report(output_dir, name, obj)`，一次产出 `.json` 与 `.md`。

## 8. 开发检查清单

- [ ] 新代码通过 `uv run --python 3.13 pytest`。
- [ ] 源数据只读，产物只写指定输出目录。
- [ ] 清洗动作写决策日志，删行记录索引。
- [ ] 可选依赖走延迟导入并给出安装指引。
- [ ] 报告对象实现 `to_report` / `to_markdown`。
- [ ] `__init__.py` 导出新增的公共 API。

## 9. 测试约定

- 测试一律用**合成数据**（`pandas.DataFrame` / 临时目录），不依赖、不触碰真实数据源。
- 覆盖：core、io（六种格式）、discover（分组/忽略/指纹）、profile（异常/空值）、
  clean（各动作 + 决策日志）、validate（断言 + 对比）、map（各操作）、pipeline（端到端）。
