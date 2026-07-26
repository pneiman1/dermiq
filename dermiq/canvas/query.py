"""Resolve a validated chart spec to a parameterized Snowflake query (chunk-12).

Security: identifiers (mart, columns) are never taken raw — every one is checked
against the curated schema allowlist (`schema.column`), so the only interpolated
identifiers come from a fixed set. All *values* (filters) are bound as query
parameters. LIMITs are coerced to int. No user string ever reaches the SQL text.
"""
from __future__ import annotations

from typing import Any

from snowflake.connector.cursor import SnowflakeCursor

from dermiq.api.fqn import fq
from dermiq.canvas import schema as canvas_schema
from dermiq.canvas.schemas import (
    BarSpec, ChartSpec, Filter, KpiSpec, LineSpec, PieSpec, ScatterSpec, TableSpec,
)


class SpecError(ValueError):
    """Spec references a mart/column that doesn't exist (used for LLM retry)."""


def _mart(mart: str) -> dict:
    m = canvas_schema.MARTS.get(mart)
    if not m:
        raise SpecError(
            f"Unknown mart '{mart}'. Available marts: {', '.join(canvas_schema.MARTS)}"
        )
    return m


def _col(mart: str, name: str, want: str | None = None) -> dict:
    c = canvas_schema.column(mart, name)
    if c is None:
        avail = [x["name"] for x in _mart(mart)["columns"]]
        raise SpecError(f"Column '{name}' does not exist in mart '{mart}'. Available: {', '.join(avail)}")
    if want and c["kind"] != want:
        raise SpecError(f"Column '{name}' in '{mart}' is a {c['kind']}, but a {want} is required here.")
    return c


def _fqn(mart: str, tenant: str) -> str:
    return fq(_mart(mart)["layer"], mart, tenant)


def _agg_expr(mart: str, name: str) -> str:
    c = _col(mart, name, "measure")
    fn = "AVG" if c.get("agg") == "avg" else "SUM"
    return f'{fn}("{c["name"].upper()}")'


def _time_col(mart: str) -> str | None:
    for c in _mart(mart)["columns"]:
        if c.get("is_time"):
            return c["name"].upper()
    return None


def _where(mart: str, f: Filter | None, params: list[Any]) -> str:
    if f is None:
        return ""
    col = _col(mart, f.column)["name"].upper()
    if f.op == "in":
        vals = f.value if isinstance(f.value, list) else [f.value]
        placeholders = ", ".join(["%s"] * len(vals))
        params.extend(vals)
        return f'WHERE "{col}" IN ({placeholders})'
    params.append(f.value)
    return f'WHERE "{col}" {f.op} %s'


def _limit(n: int | None, default: int | None = None) -> str:
    n = n if n is not None else default
    return f" LIMIT {int(n)}" if n is not None else ""


def _rows(cur: SnowflakeCursor, sql: str, params: list[Any]) -> list[dict]:
    cur.execute(sql, tuple(params))
    cols = [d[0].lower() for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def _q(name: str) -> str:
    return f'"{name.upper()}"'


def resolve_and_run(cur: SnowflakeCursor, spec: ChartSpec, tenant: str) -> list[dict]:
    """Validate + execute a chart spec, returning row dicts (lowercased keys).

    KPI returns a single-row list: [{value, comparison_value?, delta_pct?}].
    """
    fqn = _fqn(spec.mart, tenant)
    params: list[Any] = []

    if isinstance(spec, KpiSpec):
        c = _col(spec.mart, spec.measure, "measure")
        fn = "AVG" if c.get("agg") == "avg" else "SUM"
        m = _q(spec.measure)
        tcol = _time_col(spec.mart)
        if spec.comparison_period == "prior_period" and tcol:
            where = _where(spec.mart, spec.filter, params)
            sql = (
                f'SELECT {fn}(CASE WHEN "{tcol}" >= dateadd(day, -90, current_date) THEN {m} END) AS value, '
                f'{fn}(CASE WHEN "{tcol}" >= dateadd(day, -180, current_date) '
                f'AND "{tcol}" < dateadd(day, -90, current_date) THEN {m} END) AS comparison_value '
                f"FROM {fqn} {where}"
            )
            rows = _rows(cur, sql, params)
            r = rows[0] if rows else {"value": None, "comparison_value": None}
            v, pv = r.get("value"), r.get("comparison_value")
            r["delta_pct"] = (float(v) - float(pv)) / float(pv) if v is not None and pv else None
            return [r]
        where = _where(spec.mart, spec.filter, params)
        return _rows(cur, f"SELECT {fn}({m}) AS value FROM {fqn} {where}", params)

    if isinstance(spec, BarSpec):
        _col(spec.mart, spec.x, "dimension")
        _col(spec.mart, spec.y, "measure")
        yexpr = _agg_expr(spec.mart, spec.y)
        select = [f"{_q(spec.x)} AS {_q(spec.x)}"]
        group = [_q(spec.x)]
        if spec.color:
            _col(spec.mart, spec.color, "dimension")
            select.append(f"{_q(spec.color)} AS {_q(spec.color)}")
            group.append(_q(spec.color))
        select.append(f"{yexpr} AS {_q(spec.y)}")
        where = _where(spec.mart, spec.filter, params)
        order_col = _q(spec.sort_by) if spec.sort_by else _q(spec.y)
        if spec.sort_by:
            _col(spec.mart, spec.sort_by)
        sql = (f"SELECT {', '.join(select)} FROM {fqn} {where} "
               f"GROUP BY {', '.join(group)} ORDER BY {order_col} {spec.sort_direction.upper()}"
               f"{_limit(spec.limit)}")
        return _rows(cur, sql, params)

    if isinstance(spec, LineSpec):
        _col(spec.mart, spec.x, "dimension")
        ys = spec.y if isinstance(spec.y, list) else [spec.y]
        select = [f"{_q(spec.x)} AS {_q(spec.x)}"]
        for y in ys:
            select.append(f"{_agg_expr(spec.mart, y)} AS {_q(y)}")
        where = _where(spec.mart, spec.filter, params)
        sql = (f"SELECT {', '.join(select)} FROM {fqn} {where} "
               f"GROUP BY {_q(spec.x)} ORDER BY {_q(spec.x)} ASC")
        return _rows(cur, sql, params)

    if isinstance(spec, ScatterSpec):
        _col(spec.mart, spec.x, "measure")
        _col(spec.mart, spec.y, "measure")
        _col(spec.mart, spec.point_label, "dimension")
        select = [_q(spec.point_label), _q(spec.x), _q(spec.y)]
        if spec.color:
            _col(spec.mart, spec.color, "dimension")
            select.append(_q(spec.color))
        if spec.size:
            _col(spec.mart, spec.size, "measure")
            select.append(_q(spec.size))
        where = _where(spec.mart, spec.filter, params)
        sql = f"SELECT {', '.join(select)} FROM {fqn} {where}{_limit(spec.limit, 500)}"
        return _rows(cur, sql, params)

    if isinstance(spec, PieSpec):
        _col(spec.mart, spec.category, "dimension")
        _col(spec.mart, spec.value, "measure")
        vexpr = _agg_expr(spec.mart, spec.value)
        where = _where(spec.mart, spec.filter, params)
        sql = (f"SELECT {_q(spec.category)} AS {_q(spec.category)}, {vexpr} AS {_q(spec.value)} "
               f"FROM {fqn} {where} GROUP BY {_q(spec.category)} "
               f"ORDER BY {_q(spec.value)} DESC{_limit(spec.limit)}")
        return _rows(cur, sql, params)

    if isinstance(spec, TableSpec):
        for cn in spec.columns:
            _col(spec.mart, cn)
        cols = ", ".join(_q(c) for c in spec.columns)
        where = _where(spec.mart, spec.filter, params)
        order = ""
        if spec.sort_by:
            _col(spec.mart, spec.sort_by)
            order = f" ORDER BY {_q(spec.sort_by)} {spec.sort_direction.upper()}"
        sql = f"SELECT {cols} FROM {fqn} {where}{order}{_limit(spec.limit, 100)}"
        return _rows(cur, sql, params)

    raise SpecError(f"Unsupported chart type: {getattr(spec, 'type', '?')}")
