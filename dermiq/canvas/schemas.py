"""Chart grammar (chunk-12): six chart types as Pydantic specs.

These double as the LLM tool-input schemas (one tool per chart type) and as the
validated contract the query layer resolves to SQL. Keep in sync with the
TypeScript types in frontend/src/lib/types.ts.
"""
from __future__ import annotations

from typing import Annotated, Literal, Union

from pydantic import BaseModel, Field

FilterOp = Literal["=", "!=", ">", "<", ">=", "<=", "in"]
SortDir = Literal["asc", "desc"]
Orientation = Literal["vertical", "horizontal"]


class Filter(BaseModel):
    column: str
    op: FilterOp = "="
    value: Union[str, float, int, bool, list[Union[str, float, int]]]


class KpiSpec(BaseModel):
    type: Literal["kpi"] = "kpi"
    mart: str
    measure: str
    title: str
    filter: Filter | None = None
    # 'prior_period' compares the trailing window to the one before it (needs a time dim).
    comparison_period: Literal["prior_period"] | None = None


class BarSpec(BaseModel):
    type: Literal["bar"] = "bar"
    mart: str
    x: str  # dimension
    y: str  # measure
    title: str
    color: str | None = None  # dimension
    sort_by: str | None = None  # measure
    sort_direction: SortDir = "desc"
    limit: int | None = None
    orientation: Orientation = "vertical"
    filter: Filter | None = None


class LineSpec(BaseModel):
    type: Literal["line"] = "line"
    mart: str
    x: str  # time dimension
    y: Union[str, list[str]]  # measure or measures (multi-series)
    title: str
    color: str | None = None  # dimension
    filter: Filter | None = None


class ScatterSpec(BaseModel):
    type: Literal["scatter"] = "scatter"
    mart: str
    x: str  # measure
    y: str  # measure
    point_label: str  # dimension
    title: str
    color: str | None = None  # dimension
    size: str | None = None  # measure
    limit: int | None = None
    filter: Filter | None = None


class PieSpec(BaseModel):
    type: Literal["pie"] = "pie"
    mart: str
    category: str  # dimension
    value: str  # measure
    title: str
    limit: int | None = None
    filter: Filter | None = None


class TableSpec(BaseModel):
    type: Literal["table"] = "table"
    mart: str
    columns: list[str]
    title: str
    sort_by: str | None = None
    sort_direction: SortDir = "desc"
    limit: int | None = None
    filter: Filter | None = None


ChartSpec = Annotated[
    Union[KpiSpec, BarSpec, LineSpec, ScatterSpec, PieSpec, TableSpec],
    Field(discriminator="type"),
]

CHART_TYPES = ("kpi", "bar", "line", "scatter", "pie", "table")
