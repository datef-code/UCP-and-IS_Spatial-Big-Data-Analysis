# 04_validate · ④ 校验

> 项目：[project6_spatial_teaching](../README.md)　|　规范：`datakit/PROJECT_STRUCTURE.md` §2-④

## 本阶段做什么

回答「洗得对不对、能不能进下一步」：断言结果（P0/P1/P2）+ 前后对比（阶段 2 vs 阶段 3）
+ 分级建议清单 + **版本冻结**（教学可复现性）。

## 输入 / 输出

- **输入**：`03_clean/output/<dataset>/cleaned.csv` + `02_profile/output/<dataset>/profile.yaml`
  + `config/assertions.yaml`（`when: 04_validate`）
- **输出**（`output/<dataset>/`）：

| 路径 | 内容 |
| --- | --- |
| `validation.yaml` / `validation.md` | 断言结果（名称 / 严重度 / 实际 / 期望 / 通过与否；按严重度汇总） |
| `comparison.yaml` / `comparison.md` | 前后对比 + 建议清单 + 结论（能否进入 ⑤ 映射） |
| `before_after.csv` | 逐字段前后对比：缺失率 / 唯一值 / 均值 / 中位数 / 异常值 / 类型 |
| `version_lock.json` | 版本冻结：源数据指纹、行数、库版本、合成成本参数 |

## 运行

```powershell
python main.py --stage 04
```

## 口径要点

- **P0 阻断**：经纬度范围、经纬度非空、清洗后至少 1 行。
- **P1**：计数度量非负、`version_lock` 库版本未漂移（漂移 → 教学代码须重新出图）。
- 前后对比读的是阶段 2 的 `profile.yaml`（不是重算原始画像），避免重复读 30 GB 源数据。
- 建议阈值来自 `datakit.yaml`：删除行比例 > 5%、单字段填充 > 50% → P1 建议。
- 再次运行会与上一份 `version_lock.json` 比对：库版本或行数变化会被记为**漂移**并写入报告。
