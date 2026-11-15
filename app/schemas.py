"""API 请求/响应模型。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StrictInt,
    ValidationInfo,
    field_validator,
    model_validator,
)

MAX_RECORDS_PER_SIDE = 12


class RecordIn(BaseModel):
    """单条采样登记或仪器检测记录。"""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        min_length=1,
        max_length=64,
        description="记录唯一 ID（同一组内唯一）",
        examples=["S-01"],
    )
    barcode: str = Field(
        min_length=1,
        max_length=128,
        description="容器条码，组内允许重复",
        examples=["BC-100"],
    )
    timestamp: datetime = Field(
        description="UTC 时间，ISO 8601 格式，必须携带时区（推荐 Z 后缀）",
        examples=["2026-11-14T08:00:00Z"],
    )

    @field_validator("timestamp")
    @classmethod
    def _require_timezone(cls, v: datetime) -> datetime:
        if v.tzinfo is None or v.utcoffset() is None:
            raise ValueError("timestamp 必须携带时区信息（UTC 时间，建议以 Z 结尾）")
        return v.astimezone(timezone.utc)


class MatchRequest(BaseModel):
    """配对请求：两组记录，每组最多 12 条。"""

    model_config = ConfigDict(extra="forbid")

    sampling_records: list[RecordIn] = Field(
        default_factory=list,
        max_length=MAX_RECORDS_PER_SIDE,
        description="人工采样登记，最多 12 条",
    )
    detection_records: list[RecordIn] = Field(
        default_factory=list,
        max_length=MAX_RECORDS_PER_SIDE,
        description="仪器检测记录，最多 12 条",
    )

    @model_validator(mode="after")
    def _ids_unique_within_group(self) -> "MatchRequest":
        for name, group in (
            ("sampling_records", self.sampling_records),
            ("detection_records", self.detection_records),
        ):
            ids = [r.id for r in group]
            if len(ids) != len(set(ids)):
                raise ValueError(f"{name} 内存在重复 ID")
        return self


class PartnerOptionOut(BaseModel):
    id: str = Field(description="对方记录 ID")
    time_diff_seconds: float = Field(description="与该对象的时间差（秒）")


class CertainPairOut(BaseModel):
    sampling_id: str
    detection_id: str
    barcode: str
    time_diff_seconds: float


class RecordVerdictOut(BaseModel):
    """单条记录的配对结论。"""

    id: str
    barcode: str
    timestamp: datetime
    status: Literal["certain", "review", "unmatched"] = Field(
        description=(
            "certain=确定配对（所有同等最优方案中都成立）；"
            "review=待核查（配对关系在不同最优方案间不唯一）；"
            "unmatched=始终未配对（任何同等最优方案都不包含它）"
        )
    )
    certain_partner_id: str | None = Field(
        default=None, description="status=certain 时的确定配对对象 ID"
    )
    matched_in_all_optimal: bool = Field(
        description=(
            "是否在所有同等最优方案中都被配对。review 记录借此区分"
            "'始终被配对但对象不定'(true) 与 '部分方案中未配对'(false)"
        )
    )
    possible_partners: list[PartnerOptionOut] = Field(
        default_factory=list,
        description="在至少一个同等最优方案中可行的配对对象",
    )


class StatusCounts(BaseModel):
    certain: int = Field(description="确定配对记录数")
    review: int = Field(description="待核查记录数")
    unmatched: int = Field(description="始终未配对记录数")


class SummaryOut(BaseModel):
    sampling_count: int
    detection_count: int
    candidate_pair_count: int = Field(
        description="满足'同条码且时间差不超过 10 分钟'的候选配对数"
    )
    max_pairs: int = Field(description="最优方案的最大配对数")
    min_total_time_diff_seconds: float = Field(
        description="最优方案的最小时间差总和（秒）"
    )
    certain_pair_count: int = Field(description="所有同等最优方案中都成立的确定配对数")
    sampling_status: StatusCounts
    detection_status: StatusCounts


class MatchResponse(BaseModel):
    summary: SummaryOut
    certain_pairs: list[CertainPairOut] = Field(
        description="确定配对列表：在所有同等最优方案中都成立，可直接进入分析库"
    )
    sampling_records: list[RecordVerdictOut]
    detection_records: list[RecordVerdictOut]


# ---------------------------------------------------------------------------
# /redact-counts：阳性计数表遮盖
# ---------------------------------------------------------------------------

NameStr = Annotated[str, Field(min_length=1, max_length=64)]
CellCount = Annotated[StrictInt, Field(ge=0, le=9)]


class RedactCountsRequest(BaseModel):
    """遮盖请求：带行列名称的 2~3 行、2~3 列计数矩阵及敏感阈值。"""

    model_config = ConfigDict(extra="forbid")

    row_names: list[NameStr] = Field(
        min_length=2,
        max_length=3,
        description="行名（采样点），2~3 个，组内唯一",
        examples=[["SP-1", "SP-2"]],
    )
    column_names: list[NameStr] = Field(
        min_length=2,
        max_length=3,
        description="列名（检测项目），2~3 个，组内唯一",
        examples=[["T-A", "T-B"]],
    )
    counts: list[list[CellCount]] = Field(
        description=(
            "计数矩阵：行数须等于 row_names 长度，每行长度须等于 "
            "column_names 长度；每格为 0~9 的整数"
        ),
        examples=[[[2, 5], [6, 7]]],
    )
    threshold: StrictInt = Field(
        ge=2,
        le=4,
        description="敏感阈值：大于零且小于阈值的格子必须遮盖",
        examples=[3],
    )

    @field_validator("row_names", "column_names")
    @classmethod
    def _names_unique(cls, v: list[str], info: ValidationInfo) -> list[str]:
        if len(v) != len(set(v)):
            raise ValueError(f"{info.field_name} 内存在重复名称")
        return v

    @model_validator(mode="after")
    def _counts_shape_matches_names(self) -> "RedactCountsRequest":
        if len(self.counts) != len(self.row_names):
            raise ValueError(
                f"counts 行数（{len(self.counts)}）须等于 row_names 长度"
                f"（{len(self.row_names)}）"
            )
        for idx, row in enumerate(self.counts):
            if len(row) != len(self.column_names):
                raise ValueError(
                    f"counts 第 {idx} 行长度（{len(row)}）须等于 column_names 长度"
                    f"（{len(self.column_names)}）"
                )
        return self


class CellRefOut(BaseModel):
    """一个被遮盖的格子（只给坐标与名称，绝不含取值）。"""

    row_index: int = Field(description="行下标（从 0 开始）")
    column_index: int = Field(description="列下标（从 0 开始）")
    row: str = Field(description="行名")
    column: str = Field(description="列名")


class PublishedCellOut(CellRefOut):
    """一个可公开的格子及其取值。"""

    value: int = Field(ge=0, le=9, description="可公开的计数")


class RedactCountsResponse(BaseModel):
    """可安全发布的计数表：行列合计 + 可公开格 + 遮盖坐标。

    刻意不区分"敏感格"与"补遮盖格"：阈值为 2 时敏感格取值必为 1，
    一旦标注类型就等于公开真值。响应中所有遮盖格一视同仁。
    """

    row_names: list[str]
    column_names: list[str]
    threshold: int
    row_totals: list[int] = Field(description="行合计（与 row_names 同序）")
    column_totals: list[int] = Field(description="列合计（与 column_names 同序）")
    grand_total: int = Field(description="全表合计")
    grid: list[list[int | None]] = Field(
        description="与输入同形的发布表：整数为可公开格，null 为被遮盖格"
    )
    published_cells: list[PublishedCellOut] = Field(description="可公开格及其取值")
    redacted_cells: list[CellRefOut] = Field(
        description="被遮盖格坐标（敏感格与补遮盖格不区分，按行优先、列次之排序）"
    )
