"""项目编排：``Project``（规范见仓库根 ``PROJECT_STRUCTURE.md`` §1 / §4 / §8）。

datakit 负责**编排与报告底座**，项目侧只写 4 件事：``config/`` 口径、
``data_raw/README.md`` 数据说明、各阶段 ``run(project)`` 函数体、项目 README 业务叙述。

``Project`` 提供的能力：

* :meth:`Project.load` —— 读 ``datakit.yaml``，解析数据源、五阶段、扩展阶段与全局口径；
* :meth:`Project.config` / :meth:`Project.stage_output` —— 配置与产物路径的唯一入口（不再散落硬编码）；
* :meth:`Project.write_stage` —— 一次写出「机读 YAML + 人读 Markdown + 明细 CSV」；
* :meth:`Project.write_summary` —— 把各阶段摘要汇总成 ``SUMMARY.md``；
* :meth:`Project.run` —— 按目录顺序加载阶段并执行（数字前缀目录用 ``importlib`` 按文件路径加载）。

典型用法::

    import datakit as dk

    project = dk.Project.load("project1_fdic_spatial")
    project.run()                       # 全流水线
    project.run(stages=["03_clean"])    # 单阶段

    # 阶段入口内
    def run(project):
        catalog = dk.scan(project.source_root)
        project.write_stage(STAGE, "catalog", catalog, tables={"files": catalog.to_frame()})
        return {"stage": STAGE, "file_count": len(catalog)}
"""

from __future__ import annotations

import datetime as _dt
import importlib.util
import json
import sys
import time
import traceback
from pathlib import Path
from typing import Any, Iterable

import yaml

from .report import write_csv, write_markdown, write_yaml

__all__ = ["Project", "BUILTIN_STAGES"]

#: 内置五阶段（与 datakit 模块同名，目录名即入口名）
BUILTIN_STAGES = ["01_discover", "02_profile", "03_clean", "04_validate", "05_map"]

_TITLE = {
    "01_discover": "① 采集",
    "02_profile": "② 画像",
    "03_clean": "③ 清洗",
    "04_validate": "④ 校验",
    "05_map": "⑤ 映射",
}


class Project:
    """一个具体数据产品项目的运行上下文。

    参数
    ----
    root : 项目根目录（含 ``datakit.yaml`` / ``config/`` / 各阶段目录）。
    meta : 已解析的 ``datakit.yaml`` 内容。
    """

    def __init__(self, root: str | Path, meta: dict[str, Any]):
        self.root = Path(root).resolve()
        self.meta = meta or {}
        self.name: str = self.meta.get("name", self.root.name)
        self.title: str = self.meta.get("title", self.name)
        self.version: Any = self.meta.get("version", 1)
        self.options: dict[str, Any] = dict(self.meta.get("options") or {})
        self.extensions: list[dict[str, Any]] = list(self.meta.get("extensions") or [])
        self.stages: list[str] = list(self.meta.get("stages") or BUILTIN_STAGES)
        self.log_path = self.root / "logs" / "pipeline.log"
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------ #
    # 加载
    # ------------------------------------------------------------------ #
    @classmethod
    def load(cls, root: str | Path) -> "Project":
        """从项目根加载 ``datakit.yaml``。"""
        root = Path(root).resolve()
        cfg = root / "datakit.yaml"
        if not cfg.exists():
            raise FileNotFoundError(f"缺少项目配置文件：{cfg}")
        meta = yaml.safe_load(cfg.read_text(encoding="utf-8")) or {}
        return cls(root, meta)

    # ------------------------------------------------------------------ #
    # 路径
    # ------------------------------------------------------------------ #
    @property
    def source_root(self) -> Path:
        """只读源数据根目录（相对路径按 ``datakit.yaml`` 位置解析）。"""
        raw = self.meta.get("source_root", "data_raw")
        p = Path(raw)
        return (self.root / p).resolve() if not p.is_absolute() else p

    @property
    def group(self) -> str:
        return str(self.meta.get("group") or "")

    def config(self, name: str) -> dict[str, Any]:
        """读 ``config/<name>.yaml``；文件不存在返回空 dict。"""
        p = self.root / "config" / f"{name}.yaml"
        if not p.exists():
            return {}
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}

    def stage_output(self, stage: str) -> Path:
        """阶段产物目录 ``<stage>/output``（自动创建）。"""
        p = self.root / stage / "output"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def stage_path(self, stage: str, *parts: str) -> Path:
        """阶段产物目录下的具体文件路径。"""
        return self.stage_output(stage).joinpath(*parts)

    @property
    def stage_names(self) -> list[str]:
        """内置五阶段 + 扩展阶段（按编号顺序）。"""
        return list(self.stages) + [e["stage"] for e in self.extensions]

    # ------------------------------------------------------------------ #
    # 日志
    # ------------------------------------------------------------------ #
    def log(self, msg: str, echo: bool = True) -> None:
        """写 ``logs/pipeline.log``（带时间戳），并默认打印到 stdout。"""
        line = f"[{_dt.datetime.now().isoformat(timespec='seconds')}] {msg}"
        if echo:
            print(line, flush=True)
        with self.log_path.open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    # ------------------------------------------------------------------ #
    # 产物写出
    # ------------------------------------------------------------------ #
    def write_stage(
        self,
        stage: str,
        name: str,
        report: Any,
        tables: dict[str, Any] | None = None,
        markdown: str | None = None,
    ) -> dict[str, Path]:
        """写一份阶段报告：YAML（机读）+ Markdown（人读）+ 若干 CSV 明细表。

        返回 ``{"yaml": Path, "md": Path|None, "csv": {name: Path}}``。
        """
        out = self.stage_output(stage)
        paths: dict[str, Any] = {"yaml": write_yaml(out, name, report)}
        md_text = markdown
        if md_text is None and hasattr(report, "to_markdown"):
            try:
                md_text = report.to_markdown()
            except Exception:
                md_text = None
        if md_text:
            paths["md"] = write_markdown(out, name, md_text)
        csvs = {}
        for tname, frame in (tables or {}).items():
            if frame is None:
                continue
            csvs[tname] = write_csv(out, tname, frame)
        paths["csv"] = csvs
        return paths

    def write_summary(self, summaries: Iterable[dict[str, Any]]) -> Path:
        """把各阶段摘要汇总写入 ``SUMMARY.md``，返回路径。"""
        rows = [s for s in summaries if isinstance(s, dict)]
        lines = [
            f"# SUMMARY.md · {self.name}",
            "",
            f"> {self.title}",
            f"> 自动生成于 {_dt.datetime.now().isoformat(timespec='seconds')}；"
            f"规范见 `datakit/PROJECT_STRUCTURE.md`。",
            "",
            "## 阶段摘要",
            "",
            "| 阶段 | 状态 | 关键指标 |",
            "| --- | --- | --- |",
        ]
        for s in rows:
            stage = str(s.get("stage", "?"))
            status = "✅" if s.get("ok", True) else "⚠️ 降级"
            metrics = {k: v for k, v in s.items()
                       if k not in {"stage", "ok", "blocking", "artifacts", "error", "seconds"}}
            metric_txt = "；".join(f"{k}={_fmt_metric(v)}" for k, v in metrics.items()) or "—"
            metric_txt = metric_txt if len(metric_txt) <= 220 else metric_txt[:217] + "…"
            lines.append(f"| {stage} | {status} | {metric_txt} |")

        lines += ["", "## 一句话结论", ""]
        concl = next((s.get("conclusion") for s in rows if s.get("conclusion")), None)
        lines.append(f"> {concl}" if concl else "> （由 08_conclude 阶段写入）")
        lines.append("")
        p = self.root / "SUMMARY.md"
        p.write_text("\n".join(lines), encoding="utf-8")
        return p

    # ------------------------------------------------------------------ #
    # 阶段加载与编排
    # ------------------------------------------------------------------ #
    def load_stage(self, stage: str):
        """按文件路径加载阶段模块（数字前缀目录不能 ``import``）。"""
        path = self.root / stage / f"{stage}.py"
        if not path.exists():
            raise FileNotFoundError(f"阶段入口文件缺失：{path}")
        spec = importlib.util.spec_from_file_location(f"_stage_{stage}", path)
        module = importlib.util.module_from_spec(spec)
        sys.modules[spec.name] = module
        spec.loader.exec_module(module)
        return module

    def run(self, stages: Iterable[str] | None = None) -> list[dict[str, Any]]:
        """按序执行阶段；扩展阶段默认 ``blocking: false``，失败降级为告警。"""
        selected = list(stages) if stages is not None else self.stage_names
        ext_meta = {e["stage"]: e for e in self.extensions}
        summaries: list[dict[str, Any]] = []
        prior = self._load_summaries()      # 单阶段重跑时保留其它阶段的摘要

        self.log(f"== 流水线开始：{self.name} == 阶段：{', '.join(selected)}")
        for stage in selected:
            blocking = bool(ext_meta.get(stage, {}).get("blocking", True))
            t0 = time.perf_counter()
            try:
                module = self.load_stage(stage)
                summary = module.run(self) or {}
            except Exception as exc:
                summary = {
                    "stage": stage, "ok": False, "blocking": blocking,
                    "error": f"{type(exc).__name__}: {exc}",
                }
                self.log(f"[{stage}] 失败：{summary['error']}")
                self.log(traceback.format_exc().strip().replace("\n", " | "), echo=False)
                if blocking:
                    summaries.append(summary)
                    self.log(f"== 流水线中断于 {stage}（阻断）==")
                    break
            else:
                if not isinstance(summary, dict):
                    summary = {"stage": stage, "value": summary}
                summary.setdefault("stage", stage)
                summary.setdefault("ok", True)
                summary.setdefault("blocking", blocking)
                self.log(f"[{stage}] 完成：{_brief(summary)}")
            summary["seconds"] = round(time.perf_counter() - t0, 1)
            summaries.append(summary)
            prior[summary["stage"]] = summary

        self._save_summaries(prior)
        ordered = [prior[n] for n in self.stage_names if n in prior]
        self.write_summary(ordered)
        self.log(f"== 流水线结束：{len(summaries)} 个阶段 ==")
        return summaries

    # ---- 阶段摘要持久化（供单阶段重跑后重建完整 SUMMARY）----
    @property
    def _summaries_path(self) -> Path:
        return self.root / "logs" / "stage_summaries.json"

    def _load_summaries(self) -> dict[str, dict]:
        p = self._summaries_path
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except Exception:
                return {}
        return {}

    def _save_summaries(self, summaries: dict[str, dict]) -> None:
        p = self._summaries_path
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(summaries, ensure_ascii=False, indent=2, default=str) + "\n",
                     encoding="utf-8")


def _fmt_metric(value: Any) -> Any:
    """摘要里的数值统一 4 位有效数字（避免 SUMMARY 出现超长浮点）。"""
    if isinstance(value, float):
        return f"{value:.4g}"
    if isinstance(value, dict):
        return {k: _fmt_metric(v) for k, v in value.items()}
    return value


def _brief(summary: dict[str, Any], max_len: int = 200) -> str:
    """把阶段摘要压成一行日志文本。"""
    items = [f"{k}={v}" for k, v in summary.items()
             if k not in {"stage", "ok", "blocking", "artifacts", "seconds"}]
    txt = "；".join(items) or "完成"
    return txt if len(txt) <= max_len else txt[: max_len - 1] + "…"
