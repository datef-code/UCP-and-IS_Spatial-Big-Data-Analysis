# logs/

流水线运行日志目录（规范 §1）。

- 目标文件：`logs/pipeline.log` —— 每次运行的阶段摘要与时间戳，由 `datakit.Project.log()`
  在 `Project.run()` 时追加写入。
- `stage_summaries.json` —— 机读阶段摘要，单阶段重跑后用于重建完整的 `SUMMARY.md`。

## 关于「本地看不到 pipeline.log」

仓库根 `.gitignore` 第 11 行规则为 `*.log`，因此 **`pipeline.log` 不入库**：

- 全新 `git clone` 后本目录只有 `README.md` + `stage_summaries.json`，
  **这是预期行为，不是产物缺失**；
- 本地跑过 `python main.py` 后会自动生成 `logs/pipeline.log`；
- 扩展阶段（⑥ ⑦）失败时按规范 §8 降级为告警，写入 `SUMMARY.md` 并在日志中留
  `EXT_FAILED` 标记行。

> 迁移说明已清理：早期单文件 `main.py` 时代日志写在 `output/pipeline.log`，
> 该路径已不存在（旧产物整体迁入 `../output_legacy_v1/`，见其 README），
> 现行唯一日志路径就是本目录。
