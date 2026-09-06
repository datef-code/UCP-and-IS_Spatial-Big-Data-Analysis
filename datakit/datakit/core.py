"""核心数据容器与基础类型。

本模块定义 SDK 最基础的两个抽象：

* :class:`Dataset` —— 对 ``pandas.DataFrame`` 的轻量封装，携带来源/格式/指纹等元信息，
  是贯穿「采集 → 描述 → 清洗 → 校验 → 映射」全流程的统一数据载体。
* :class:`Role` —— 字段角色枚举，用于表达「同一字段在不同目的下，空值/异常值含义不同」这一
  通用事实。例如 ``SIMS_ACQUIRED_DATE`` 缺失可能表示「右删失（仍存活）」而非脏数据。

设计原则：SDK 只在内存中处理数据，**不修改任何源文件**；所有对外的写入都通过显式的
``datakit.io.write`` 或报告/日志接口完成，且默认写入调用方指定的输出目录。
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable

import pandas as pd

__version__ = "0.1.0"

__all__ = [
    "DataKitError",
    "FormatNotSupportedError",
    "Dataset",
    "Role",
    "DatasetMeta",
    "infer_roles",
]


class DataKitError(RuntimeError):
    """SDK 通用异常基类。"""


class FormatNotSupportedError(DataKitError):
    """当输入/输出格式不在支持列表内时抛出。"""

    def __init__(self, fmt: str, supported: Iterable[str]):
        self.fmt = fmt
        self.supported = sorted(supported)
        super().__init__(f"unsupported format '{fmt}', supported: {', '.join(self.supported)}")


class Role(str, enum.Enum):
    """字段角色：决定描述性统计、清洗时如何解释空值/异常值。

    关键点：**异常值/空值的判定依赖目的**。同一个字段在不同分析目标下可以声明为不同角色，
    从而让 ``profile`` / ``clean`` 采用不同的处理策略。
    """

    KEY = "key"                    # 主键/分组键：缺失即数据缺陷，通常剔除
    EVENT = "event"                # 事件时间（如关闭日期）：缺失=右删失，是有意义信息，不应当作脏数据
    TIME_VARYING = "time_varying"  # 时变协变量：缺失可标记/填充，不轻易删行
    SPATIAL = "spatial"            # 空间字段（经纬度）：需做边界/精度检查
    CATEGORICAL = "categorical"    # 类别字段：缺失可重编码为 UNKNOWN
    NUMERIC = "numeric"            # 数值字段：缺失可填充/标记
    TARGET = "target"              # 目标变量：通常只观测，不自动清洗
    IGNORE = "ignore"              # 忽略字段：不参与统计/清洗


@dataclass
class DatasetMeta:
    """数据集元信息（来源、格式、指纹）。"""

    name: str | None = None
    source: str | None = None
    format: str | None = None
    rows: int | None = None
    cols: int | None = None
    md5: str | None = None
    loaded_at: str | None = None
    extra: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        out = {
            "name": self.name,
            "source": self.source,
            "format": self.format,
            "rows": self.rows,
            "cols": self.cols,
            "md5": self.md5,
            "loaded_at": self.loaded_at,
        }
        out.update(self.extra)
        return {k: v for k, v in out.items() if v is not None}


class Dataset:
    """统一数据容器：包装 ``pandas.DataFrame`` 并携带元信息。

    典型用法::

        import datakit as dk
        ds = dk.read("data.csv")       # 自动识别格式
        ds.frame                        # 底层 DataFrame
        ds.columns, ds.shape, ds.dtypes

    ``Dataset`` 是不可变包装：修改底层数据请通过 ``dk.clean`` / ``dk.map`` 等函数，
    它们会返回新的 ``Dataset`` 并保留来源与元信息，从而保证可追溯。
    """

    def __init__(self, frame: pd.DataFrame, meta: DatasetMeta | None = None):
        self._frame = frame
        self.meta = meta or DatasetMeta(rows=len(frame), cols=len(frame.columns))

    # ---- 数据访问（委托给 DataFrame，保持 pandas 手感）----
    @property
    def frame(self) -> pd.DataFrame:
        """返回底层 ``pandas.DataFrame``。"""
        return self._frame

    @property
    def columns(self) -> pd.Index:
        return self._frame.columns

    @property
    def dtypes(self) -> pd.Series:
        return self._frame.dtypes

    @property
    def shape(self) -> tuple[int, int]:
        return self._frame.shape

    def __len__(self) -> int:
        return len(self._frame)

    def __getitem__(self, key: Any) -> Any:
        return self._frame[key]

    def head(self, n: int = 5) -> pd.DataFrame:
        return self._frame.head(n)

    def copy(self) -> "Dataset":
        """返回浅拷贝（DataFrame 复制、元信息复制）。"""
        return Dataset(self._frame.copy(), DatasetMeta(**self.meta.to_dict()))

    def with_frame(self, frame: pd.DataFrame) -> "Dataset":
        """基于新 DataFrame 构造 ``Dataset``，自动继承来源/格式，并更新行列数与行数。"""
        meta = DatasetMeta(**self.meta.to_dict())
        meta.rows = len(frame)
        meta.cols = len(frame.columns)
        return Dataset(frame, meta)

    def __repr__(self) -> str:  # pragma: no cover - 调试辅助
        name = self.meta.name or self.meta.source or "<unnamed>"
        return f"Dataset({name}, shape={self.shape})"


def infer_roles(
    columns: Iterable[str],
    overrides: dict[str, str | Role] | None = None,
    key_like: Iterable[str] = ("id", "_key", "key", "record_id", "brnum", "cert"),
    event_like: Iterable[str] = ("acquired", "closed", "death", "end_date", "end_time"),
    spatial_like: Iterable[str] = ("lat", "lon", "lng", "longitude", "latitude", "x_", "y_"),
) -> dict[str, Role]:
    """根据列名启发式推断字段角色，可用 ``overrides`` 覆盖。

    这是一个「默认口径」生成器：**不替代用户显式声明**，只为批量场景提供可复现的起点。
    用户应始终结合分析目的用 ``overrides`` 或自定义映射修正角色。
    """
    override_map = {str(k): Role(v) for k, v in (overrides or {}).items()}
    roles: dict[str, Role] = {}
    for col in columns:
        if col in override_map:
            roles[col] = override_map[col]
            continue
        c = str(col).lower()
        if any(c.endswith(k) or k in c for k in key_like):
            roles[col] = Role.KEY
        elif any(e in c for e in event_like):
            roles[col] = Role.EVENT
        elif any(s in c for s in spatial_like):
            roles[col] = Role.SPATIAL
        else:
            roles[col] = Role.NUMERIC
    return roles
