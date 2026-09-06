"""工作流编排：把「采集 → 描述 → 清洗 → 校验 → 映射」五步串成一条可复现的流水线。

每一阶段都写出 JSON 报告 + Markdown 报告，并把阶段摘要追加到 ``pipeline.log``。
这是从具体数据集（如 FDIC / 深圳共享单车）中**提炼出的通用流程骨架**：具体口径
（字段角色、清洗计划、映射方案、断言）通过参数注入，流程本身与数据无关。

目录产物::

    output_dir/
    ├── pipeline.log
    ├── 01_discover/catalog.{json,md}
    ├── 02_profile/profile.{json,md}
    ├── 03_clean/decisions.md + clean_stats.json
    ├── 04_validate/comparison.{json,md} + validation.{json,md}
    └── 05_map/map.{json,md}
"""

from __future__ import annotations

import datetime as _dt
from pathlib import Path
from typing import Any, Iterable

import pandas as pd

from .clean import CleanPlan, clean as _clean
from .core import Dataset, Role
from .discover import Catalog, scan as _scan
from .io import read
from .map import MappingScheme, map as _map
from .profile import profile as _profile
from .report import write_json, write_markdown, write_report
from .validate import compare as _compare, validate as _validate

__all__ = ["Workflow"]


class Workflow:
    """通用数据处理工作流。

    参数
    ----
    output_dir : 输出目录（报告/日志落盘位置）。
    with_md5 / count_rows : 见 :func:`datakit.discover.scan`（大目录建议关闭）。
    """

    def __init__(self, output_dir: str | Path, with_md5: bool = False, count_rows: bool = False):
        self.output_dir = Path(output_dir)
        self.with_md5 = with_md5
        self.count_rows = count_rows
        self.output_dir.mkdir(parents=True, exist_ok=True)

    # ---- 日志 ----
    def _log(self, msg: str) -> None:
        line = f"[{_dt.datetime.now().isoformat(timespec='seconds')}] {msg}"
        with (self.output_dir / "pipeline.log").open("a", encoding="utf-8") as f:
            f.write(line + "\n")

    # ---- 读取一个数据集分组 ----
    def _read_group(self, catalog: Catalog, group: str, max_files: int | None) -> Dataset:
        sources = catalog.groups.get(group, [])
        if max_files is not None:
            sources = sources[:max_files]
        if not sources:
            raise ValueError(f"数据集分组不存在或为空: {group}")
        frames = [read(s.path).frame for s in sources]
        frame = pd.concat(frames, ignore_index=True)
        return Dataset(frame)

    # ---- 主流程 ----
    def run(
        self,
        source_root: str | Path,
        *,
        group: str | None = None,
        max_files: int | None = None,
        formats: Iterable[str] | None = None,
        roles: dict[str, str | Role] | None = None,
        clean_plan: CleanPlan | None = None,
        mapping_scheme: MappingScheme | None = None,
        assertions: Iterable[dict[str, Any]] | None = None,
        key_fields: Iterable[str] | None = None,
        outlier_method: str = "iqr",
        outlier_threshold: float = 1.5,
    ) -> dict[str, Any]:
        """执行完整流水线，返回各阶段产物路径的汇总 dict。

        ``group`` 指定要处理的数据集分组名（``catalog.groups`` 的键）；缺省时处理
        第一个分组。``clean_plan`` / ``mapping_scheme`` / ``roles`` / ``assertions``
        是「目的相关」的可注入口径。
        """
        root = Path(source_root)
        results: dict[str, Any] = {}
        self._log(f"== 流水线开始：源目录 {root} ==")

        # 1. 采集
        catalog = _scan(root, formats=formats, with_md5=self.with_md5, count_rows=self.count_rows)
        write_report(self.output_dir / "01_discover", "catalog", catalog)
        results["discover"] = {"groups": list(catalog.groups.keys()), "file_count": len(catalog)}
        self._log(f"[1/5] 采集完成：{len(catalog)} 个文件，{len(catalog.groups)} 个数据集分组")

        if not catalog.sources:
            self._log("未发现任何数据文件，流程终止")
            return results

        # 选择目标分组
        group = group or next(iter(catalog.groups))
        dataset = self._read_group(catalog, group, max_files)
        self._log(f"[1/5] 读取数据集分组「{group}」，形状 {dataset.shape}")

        # 2. 描述性统计 1
        prof1 = _profile(dataset, roles=roles, outlier_method=outlier_method,
                         outlier_threshold=outlier_threshold)
        write_report(self.output_dir / "02_profile", "profile", prof1)
        results["profile1"] = prof1.summary
        self._log(f"[2/5] 描述性统计完成：{prof1.summary}")

        # 3. 清洗
        plan = clean_plan or CleanPlan()
        cleaned = _clean(dataset, plan)
        write_markdown(self.output_dir / "03_clean", "decisions", cleaned.decisions.to_markdown())
        write_json(self.output_dir / "03_clean", "clean_stats", cleaned.stats)
        results["clean"] = cleaned.stats
        self._log(f"[3/5] 清洗完成：{cleaned.stats}")

        # 4. 校验分析 2（清洗后画像 + 前后对比 + 断言）
        prof2 = _profile(cleaned.dataset, roles=roles, outlier_method=outlier_method,
                         outlier_threshold=outlier_threshold)
        removed_rate = cleaned.stats.get("removed_rows", 0) / max(cleaned.stats.get("before_rows", 1), 1)
        comparison = _compare(prof1, prof2, removed_rate=removed_rate, key_fields=key_fields)
        write_report(self.output_dir / "04_validate", "comparison", comparison)
        if assertions is not None:
            vr = _validate(cleaned.dataset, assertions)
            write_report(self.output_dir / "04_validate", "validation", vr)
            results["validation"] = vr.to_report()
        results["profile2"] = prof2.summary
        self._log(f"[4/5] 校验分析完成：建议「{comparison.recommendation}」")

        # 5. 映射
        scheme = mapping_scheme or MappingScheme()
        mapped = _map(cleaned.dataset, scheme)
        write_report(self.output_dir / "05_map", "map", mapped)
        results["map"] = mapped.to_report()
        self._log(f"[5/5] 映射完成：形状 {mapped.dataset.shape}")

        self._log("== 流水线结束 ==")
        return results
