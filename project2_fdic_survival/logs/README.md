# logs/

流水线运行日志目录（规范 §1）。

- 目标文件：`logs/pipeline.log` —— 每次运行的阶段摘要与时间戳。
- **迁移前**：日志仍写在 `output/pipeline.log`（现有脚本未改动，数据未搬迁）。
- **迁移后**：根 `main.py` 统一写入本目录；扩展阶段失败写 `EXT_FAILED` 标记行。
