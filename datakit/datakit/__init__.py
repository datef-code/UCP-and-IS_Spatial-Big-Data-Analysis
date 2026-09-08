"""datakit —— 通用数据处理 SDK。

把「数据采集 → 描述性统计 → 清洗 → 校验 → 映射」五步沉淀为可复用的通用方法，
面向 json / csv / xml / rdf / xlsx 等常见数据格式，风格接近 pandas / numpy。

快速上手::

    import datakit as dk

    # 1. 采集：扫描目录，识别并分组数据集
    catalog = dk.scan("data_raw")

    # 2. 描述性统计：字段画像 + 异常值 + 空值
    ds = dk.read("data.csv")
    profile = dk.profile(ds, roles={"SIMS_ACQUIRED_DATE": dk.Role.EVENT})

    # 3. 清洗
    plan = dk.CleanPlan().drop_na(["BRNUM"]).fill("DEPSUMBR", method="median")
    result = dk.clean(ds, plan)

    # 4. 校验与前后对比
    comparison = dk.compare(profile, dk.profile(result.dataset))

    # 5. 映射
    mapped = dk.map(result.dataset, dk.MappingScheme().rename({"lat": "latitude"}))

    # 或一条命令跑完整流程（每步产出报告与日志）
    wf = dk.Workflow("output").run("data_raw", group="fdic_sod_#")

完整的规范与开发指引见仓库根目录的 ``通用规范.md`` 与 ``DEVELOPMENT_GUIDE.md``。
"""

from .core import (
    DataKitError,
    Dataset,
    DatasetMeta,
    FormatNotSupportedError,
    Role,
    infer_roles,
    __version__,
)
from .io import (
    SUPPORTED_FORMATS,
    detect_format,
    read,
    read_csv,
    read_json,
    read_rdf,
    read_xlsx,
    read_xml,
    write,
)
from .discover import Catalog, Source, discover, scan
from .profile import FieldProfile, Profile, describe, detect_outliers, null_summary, profile
from .clean import CleanAction, CleanPlan, CleanResult, DecisionLog, clean
from .validate import (
    CheckResult,
    ComparisonReport,
    ValidationReport,
    compare,
    validate,
)
from .map import MappingOp, MappingScheme, MapResult, map
from .anim import animate, video_page, ffmpeg_available
from .report import write_json, write_jsonl, write_markdown, write_report, write_yaml, write_csv
from .pipeline import Workflow
from .project import Project, BUILTIN_STAGES
from .schema import (
    FieldSpec,
    Rule,
    LEVELS,
    LEVEL_SEVERITY,
    load_schema,
    schema_roles,
    violations,
    missing_fields,
    unregistered_fields,
)

__all__ = [
    "__version__",
    # anim（展示层：mp4 + 自包含 HTML，可交互扩展阶段复用）
    "animate",
    "video_page",
    "ffmpeg_available",
    # core
    "DataKitError",
    "Dataset",
    "DatasetMeta",
    "FormatNotSupportedError",
    "Role",
    "infer_roles",
    # io
    "SUPPORTED_FORMATS",
    "detect_format",
    "read",
    "read_csv",
    "read_json",
    "read_rdf",
    "read_xlsx",
    "read_xml",
    "write",
    # discover
    "Catalog",
    "Source",
    "discover",
    "scan",
    # profile
    "FieldProfile",
    "Profile",
    "describe",
    "detect_outliers",
    "null_summary",
    "profile",
    # clean
    "CleanAction",
    "CleanPlan",
    "CleanResult",
    "DecisionLog",
    "clean",
    # validate
    "CheckResult",
    "ComparisonReport",
    "ValidationReport",
    "compare",
    "validate",
    # map
    "MappingOp",
    "MappingScheme",
    "MapResult",
    "map",
    # report
    "write_json",
    "write_jsonl",
    "write_markdown",
    "write_report",
    "write_yaml",
    "write_csv",
    # pipeline
    "Workflow",
    # project
    "Project",
    "BUILTIN_STAGES",
    # schema
    "FieldSpec",
    "Rule",
    "LEVELS",
    "LEVEL_SEVERITY",
    "load_schema",
    "schema_roles",
    "violations",
    "missing_fields",
    "unregistered_fields",
]
