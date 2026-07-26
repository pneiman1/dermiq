"""Build DermIQ's RAG knowledge corpus from the Snowflake marts.

Two kinds of documents:
  * static definitions — what each metric, segment, and process means; and
  * data snapshots — natural-language summaries of current mart state, so the
    chat answers with real numbers.

Each generator returns dicts of {doc_id, title, source, text}. scripts/
build_rag_corpus.py embeds these and writes them to the rag_corpus table; an
Airflow DAG rebuilds them on a schedule so snapshots stay current. See
docs/DECISIONS.md ADR-008.
"""
from __future__ import annotations

import pandas as pd
from snowflake.connector import SnowflakeConnection

from platform_core.config import get_settings
from platform_core.utils.logging import get_logger
from platform_core.warehouse.schemas import schema_name

log = get_logger(__name__)

CATS = {
    "injectable": "Injectables",
    "energy_device": "Energy devices",
    "skincare_retail": "Skincare & retail",
    "membership": "Memberships",
    "surgical": "Surgical",
    "consult": "Consults",
}


def _fq(layer: str, table: str, tenant: str) -> str:
    db = get_settings().snowflake_database
    return f"{db}.{schema_name(layer, tenant)}.{table}"


def _df(conn: SnowflakeConnection, sql: str) -> pd.DataFrame:
    cur = conn.cursor()
    cur.execute(sql)
    df = cur.fetch_pandas_all()
    df.columns = [c.lower() for c in df.columns]
    return df


def _usd(x) -> str:
    return f"${float(x):,.0f}"


def _pct(x) -> str:
    return f"{float(x) * 100:.1f}%"


def _f(x) -> float:
    return float(x) if x is not None else 0.0


# --------------------------------------------------------------------------- #
# Static definition documents (stable knowledge, authored not queried)
# --------------------------------------------------------------------------- #

STATIC_DOCS: list[dict] = [
    {
        "doc_id": "def_practice_overview",
        "title": "About the practice",
        "source": "practice profile",
        "text": (
            "Del Mar Aesthetics is a cosmetic-dermatology practice. Its service lines are "
            "grouped into six categories: injectables (neuromodulators and fillers, e.g. Botox, "
            "Alle-eligible dermal fillers), energy devices (laser and body-contouring treatments), "
            "skincare & retail (medical-grade product and facials), memberships (recurring "
            "membership plans), surgical (minor surgical and vein procedures), and consults "
            "(evaluation visits). Revenue, providers, patients, and marketing spend are all "
            "analyzed through these categories."
        ),
    },
    {
        "doc_id": "def_metric_glossary",
        "title": "Metric glossary",
        "source": "definitions",
        "text": (
            "Key metrics. Total revenue (lifetime value / LTV): a patient's cumulative net "
            "revenue to date. Annual revenue run-rate: a patient's revenue annualized over their "
            "active tenure, used to compare patients on a yearly basis. Recency (days): days since "
            "a patient's last visit. Recency tiers: active, lapsing, lapsed, dormant — from most "
            "to least recent. LTV tiers: vip, high, standard, low — from most to least valuable by "
            "lifetime revenue. Avg ticket: revenue per visit. Revenue per hour: provider revenue "
            "divided by productive (in-treatment) hours. Cross-sell rate: share of a provider's "
            "visits that touch more than one service category. Skincare attach rate: share of "
            "visits that include a skincare/retail line. LTV:CAC: patient run-rate value divided "
            "by customer-acquisition cost (marketing spend per acquired patient)."
        ),
    },
    {
        "doc_id": "def_segmentation_method",
        "title": "How patient segments are built",
        "source": "methodology",
        "text": (
            "Patient segments are produced by unsupervised k-means clustering (k=7) over 12 "
            "standardized behavioral features per patient — total visits, total revenue, annual "
            "run-rate, recency, per-category visit counts, per-category revenue shares, and visit "
            "cadence. Only cluster-eligible patients (not soft-deleted, at least one completed "
            "visit) are included. Each cluster is auto-named from its dominant service category "
            "and LTV tier, e.g. 'Injectable VIPs' or 'Skincare & facial — occasional'. The model "
            "is retrained weekly by an Airflow DAG. Segments are descriptive, not predictive."
        ),
    },
    {
        "doc_id": "def_recall_method",
        "title": "How the recall queue works",
        "source": "methodology",
        "text": (
            "The recall queue lists patients who are lapsing or lapsed (overdue for a return "
            "visit) and therefore at risk of churn. Recall priority is assigned from LTV tier and "
            "recency: 'urgent' = a vip/high-value patient who is lapsing; 'high' = a vip/high "
            "patient who has already lapsed; 'monitor' = everyone else in the queue. Revenue at "
            "risk is the annualized run-rate revenue of queued patients — what the practice stands "
            "to lose if they churn. Prioritizing urgent patients targets the highest-value, "
            "most-recoverable relationships first."
        ),
    },
    {
        "doc_id": "def_attribution_method",
        "title": "How marketing attribution works",
        "source": "methodology",
        "text": (
            "Each patient carries an acquisition channel (how they were first acquired, e.g. "
            "Instagram/Meta, RealSelf, referral, Google, walk-in). Channel attribution compares, "
            "per channel over the trailing twelve months: patients acquired, total revenue, "
            "average patient run-rate value, the mix of LTV tiers acquired, marketing spend, and "
            "LTV:CAC (run-rate value divided by cost per acquired patient). Channel health flags a "
            "channel 'organic' when it has no tracked spend, otherwise grades its LTV:CAC "
            "efficiency. A channel can be profitable yet still be the lowest-ROI paid channel."
        ),
    },
    {
        "doc_id": "def_provider_scorecard_method",
        "title": "How provider performance is measured",
        "source": "methodology",
        "text": (
            "Each provider's scorecard covers the trailing twelve months: visits, revenue, average "
            "ticket, revenue per productive hour (the core efficiency metric), cross-sell rate, "
            "and skincare attach rate, plus all-time totals. Revenue per hour, not raw revenue, is "
            "the fairest cross-provider comparison because providers work different schedules. "
            "Cross-sell and skincare-attach rates surface who is expanding each visit versus "
            "delivering a single service."
        ),
    },
]


# --------------------------------------------------------------------------- #
# Data snapshot documents (queried from the marts each build)
# --------------------------------------------------------------------------- #


def _revenue_docs(conn: SnowflakeConnection, t: str) -> list[dict]:
    m = _fq("mart", "mart_revenue_daily", t)
    r = _df(
        conn,
        f"""
        select
          min(date_day) as first_day, max(date_day) as last_day,
          sum(net_revenue) as rev, sum(completed_visits) as visits,
          sum(new_patients) as new_pat, sum(no_show_count) as no_shows,
          sum(scheduled_appointments) as sched,
          sum(rev_injectable) as injectable, sum(rev_device) as energy_device,
          sum(rev_skincare) as skincare_retail, sum(rev_membership) as membership,
          sum(rev_surgical) as surgical, sum(rev_consult) as consult
        from {m}
        """,
    ).iloc[0]

    cat_lines = []
    total = _f(r["rev"]) or 1.0
    for key, label in CATS.items():
        v = _f(r[key])
        cat_lines.append(f"{label} {_usd(v)} ({_pct(v / total)})")
    no_show_rate = _f(r["no_shows"]) / (_f(r["sched"]) or 1.0)

    summary = {
        "doc_id": "snap_revenue_summary",
        "title": "Revenue summary",
        "source": "mart_revenue_daily",
        "text": (
            f"Practice-wide revenue for Del Mar Aesthetics. Recorded daily activity spans "
            f"{r['first_day']} to {r['last_day']}. All-time net revenue is {_usd(r['rev'])} across "
            f"{int(_f(r['visits'])):,} completed visits, with {int(_f(r['new_pat'])):,} new "
            f"patients acquired. Revenue by category: " + "; ".join(cat_lines) + ". "
            f"The no-show rate on scheduled appointments is {_pct(no_show_rate)}."
        ),
    }

    # Monthly trend, last 6 recorded months.
    mo = _df(
        conn,
        f"""
        select date_trunc('month', date_day) as mth, sum(net_revenue) as rev,
               sum(completed_visits) as visits
        from {m}
        group by 1 order by 1 desc limit 6
        """,
    ).sort_values("mth")
    trend_lines = [
        f"{row.mth.strftime('%b %Y')}: {_usd(row.rev)} ({int(_f(row.visits)):,} visits)"
        for row in mo.itertuples()
    ]
    if len(mo) >= 2:
        last, prev = _f(mo.iloc[-1]["rev"]), _f(mo.iloc[-2]["rev"])
        mom = (last - prev) / (prev or 1.0)
        direction = "up" if mom >= 0 else "down"
        mom_txt = (
            f" The most recent recorded month is {direction} {_pct(abs(mom))} in net revenue "
            f"month over month."
        )
    else:
        mom_txt = ""
    trend = {
        "doc_id": "snap_revenue_trend",
        "title": "Recent revenue trend",
        "source": "mart_revenue_daily",
        "text": (
            "Monthly net revenue over the most recent recorded months — "
            + "; ".join(trend_lines)
            + "."
            + mom_txt
        ),
    }
    return [summary, trend]


def _service_mix_doc(conn: SnowflakeConnection, t: str) -> list[dict]:
    tx = _fq("stg", "stg_nextech__transactions", t)
    sv = _fq("stg", "stg_nextech__services", t)

    # Category revenue mix (all-time).
    cat = _df(
        conn,
        f"select service_category as cat, sum(net_amount) as rev from {tx} group by 1",
    )
    total = _f(cat["rev"].sum()) or 1.0
    cat = cat.sort_values("rev", ascending=False)
    mix_lines = [
        f"{CATS.get(row.cat, row.cat)} {_pct(_f(row.rev) / total)} ({_usd(row.rev)})"
        for row in cat.itertuples()
    ]

    # Month-over-month trend for the top 3 categories.
    top3 = list(cat["cat"].head(3))
    trend_lines = []
    for c in top3:
        mo = _df(
            conn,
            f"""
            select date_trunc('month', transaction_date) as mth, sum(net_amount) as rev
            from {tx} where service_category = '{c}'
            group by 1 order by 1 desc limit 2
            """,
        ).sort_values("mth")
        if len(mo) == 2:
            last, prev = _f(mo.iloc[-1]["rev"]), _f(mo.iloc[-2]["rev"])
            mom = (last - prev) / (prev or 1.0)
            trend_lines.append(
                f"{CATS.get(c, c)} {'grew' if mom >= 0 else 'declined'} {_pct(abs(mom))} MoM"
            )

    # Top-performing services within each category, and notable underperformers.
    svc = _df(
        conn,
        f"""
        select s.service_category as cat, s.service_name as name, sum(t.net_amount) as rev,
               count(*) as n
        from {tx} t join {sv} s on t.service_code = s.service_code
        group by 1, 2
        """,
    )
    top_by_cat = []
    for c in top3:
        sub = svc[svc["cat"] == c].sort_values("rev", ascending=False)
        if len(sub):
            r0 = sub.iloc[0]
            top_by_cat.append(f"{CATS.get(c, c)}: {r0['name']} ({_usd(r0['rev'])})")
    weakest = svc.sort_values("rev").head(3)
    weak_lines = [f"{row.name} ({CATS.get(row.cat, row.cat)}, {_usd(row.rev)})" for row in weakest.itertuples()]

    text = (
        "Service mix by category. Share of net revenue: " + "; ".join(mix_lines) + ". "
        "Recent momentum on the top categories — "
        + ("; ".join(trend_lines) if trend_lines else "insufficient history")
        + ". Top-performing service within each leading category: "
        + "; ".join(top_by_cat)
        + ". Notable underperformers (lowest-revenue services): "
        + "; ".join(weak_lines)
        + ". This answers which categories are growing and which services the practice is winning "
        "on versus lagging."
    )
    return [
        {
            "doc_id": "snap_service_mix_by_category",
            "title": "Service mix by category",
            "source": "stg_nextech__transactions + services",
            "text": text,
        }
    ]


def _recall_docs(conn: SnowflakeConnection, t: str) -> list[dict]:
    q = _fq("mart", "mart_recall_queue", t)
    agg = _df(
        conn,
        f"""
        select recall_priority as pri, count(*) as n,
               sum(annual_revenue_run_rate) as rev_at_risk
        from {q} group by 1
        """,
    )
    by_pri = {row.pri: (int(_f(row.n)), _f(row.rev_at_risk)) for row in agg.itertuples()}
    total_n = sum(v[0] for v in by_pri.values())
    total_risk = sum(v[1] for v in by_pri.values())
    urgent_n, urgent_risk = by_pri.get("urgent", (0, 0.0))
    high_n, _ = by_pri.get("high", (0, 0.0))
    monitor_n, _ = by_pri.get("monitor", (0, 0.0))

    summary = {
        "doc_id": "snap_recall_summary",
        "title": "Recall queue summary",
        "source": "mart_recall_queue",
        "text": (
            f"The recall queue holds {total_n:,} lapsing or lapsed patients, representing "
            f"{_usd(total_risk)} of annualized revenue at risk if they churn. By priority: "
            f"{urgent_n:,} urgent (high-value and newly lapsing, {_usd(urgent_risk)} at risk), "
            f"{high_n:,} high (high-value and already lapsed), and {monitor_n:,} monitor. Recall "
            f"outreach should start with the urgent cohort."
        ),
    }

    # Top patients at risk (urgent, then high), by run-rate value.
    top = _df(
        conn,
        f"""
        select first_name, last_name, total_revenue, annual_revenue_run_rate,
               recency_days, recency_tier, ltv_tier, last_provider_name, recall_priority
        from {q}
        where recall_priority in ('urgent','high')
        order by annual_revenue_run_rate desc nulls last
        limit 15
        """,
    )
    lines = [
        f"{row.first_name} {row.last_name} ({row.ltv_tier}, {_usd(row.annual_revenue_run_rate)}/yr "
        f"run-rate, {int(_f(row.recency_days))}d since last visit, provider "
        f"{row.last_provider_name or 'n/a'}, {row.recall_priority})"
        for row in top.itertuples()
    ]
    at_risk = {
        "doc_id": "snap_top_patients_at_risk",
        "title": "Top patients at risk",
        "source": "mart_recall_queue",
        "text": (
            "The highest-value patients currently at risk (lapsing or lapsed high-value "
            "patients), ranked by annual run-rate value: " + "; ".join(lines) + ". These are the "
            "individuals to prioritize for personal recall outreach."
        ),
    }
    return [summary, at_risk]


def _channel_doc(conn: SnowflakeConnection, t: str) -> list[dict]:
    c = _fq("mart", "mart_channel_attribution", t)
    df = _df(
        conn,
        f"""
        select acquisition_channel as channel, patients_acquired_ttm as patients,
               total_revenue_ttm as revenue, avg_ltv_run_rate_ttm as avg_ltv,
               spend_ttm as spend, ltv_cac_ratio_ttm as ltv_cac, channel_health
        from {c} order by ltv_cac_ratio_ttm desc nulls last
        """,
    )
    lines = []
    for row in df.itertuples():
        cac = f"{_f(row.ltv_cac):.0f}x LTV:CAC" if row.ltv_cac is not None else "organic"
        lines.append(
            f"{row.channel}: {int(_f(row.patients)):,} patients acquired (TTM), "
            f"{_usd(row.revenue)} revenue, {_usd(row.avg_ltv)} avg run-rate value, "
            f"{_usd(row.spend)} spend, {cac} ({row.channel_health})"
        )
    return [
        {
            "doc_id": "snap_channel_attribution",
            "title": "Marketing channel attribution",
            "source": "mart_channel_attribution",
            "text": (
                "Acquisition channels over the trailing twelve months, ranked by LTV:CAC "
                "efficiency: " + "; ".join(lines) + ". Lower-LTV:CAC paid channels are the first "
                "candidates to trim or re-target."
            ),
        }
    ]


def _provider_docs(conn: SnowflakeConnection, t: str) -> list[dict]:
    p = _fq("mart", "mart_provider_scorecard", t)
    df = _df(
        conn,
        f"""
        select provider_name, provider_role, visits_ttm, revenue_ttm, avg_ticket_ttm,
               revenue_per_hour_ttm, cross_sell_rate_ttm, skincare_attach_rate_ttm,
               total_revenue_alltime
        from {p} order by revenue_ttm desc nulls last
        """,
    )
    docs: list[dict] = []

    # Ranking overview.
    rank_lines = [
        f"{i}. {row.provider_name} ({row.provider_role}) — {_usd(row.revenue_ttm)} TTM revenue, "
        f"{_usd(row.revenue_per_hour_ttm)}/productive hour, {_usd(row.avg_ticket_ttm)} avg ticket"
        for i, row in enumerate(df.itertuples(), start=1)
    ]
    docs.append(
        {
            "doc_id": "snap_provider_ranking",
            "title": "Provider performance ranking",
            "source": "mart_provider_scorecard",
            "text": (
                "Providers ranked by trailing-twelve-month revenue: "
                + "; ".join(rank_lines)
                + ". Revenue per productive hour is the fairest efficiency comparison across "
                "different schedules."
            ),
        }
    )

    # Cross-sell / skincare-attach analysis.
    avg_cross = _f(df["cross_sell_rate_ttm"].mean())
    avg_skin = _f(df["skincare_attach_rate_ttm"].mean())
    cs_lines = [
        f"{row.provider_name}: {_pct(row.cross_sell_rate_ttm)} cross-sell, "
        f"{_pct(row.skincare_attach_rate_ttm)} skincare attach"
        for row in df.itertuples()
    ]
    docs.append(
        {
            "doc_id": "snap_provider_cross_sell_analysis",
            "title": "Provider cross-sell analysis",
            "source": "mart_provider_scorecard",
            "text": (
                f"Cross-sell and skincare-attach rates by provider (practice averages: "
                f"{_pct(avg_cross)} cross-sell, {_pct(avg_skin)} skincare attach). "
                + "; ".join(cs_lines)
                + ". Providers well below the practice average on cross-sell or skincare attach "
                "are the clearest coaching and revenue-expansion opportunities."
            ),
        }
    )

    # One snapshot per provider.
    for row in df.itertuples():
        docs.append(
            {
                "doc_id": f"snap_provider_{_slug(row.provider_name)}",
                "title": f"Provider snapshot — {row.provider_name}",
                "source": "mart_provider_scorecard",
                "text": (
                    f"{row.provider_name} ({row.provider_role}) — trailing twelve months: "
                    f"{int(_f(row.visits_ttm)):,} visits, {_usd(row.revenue_ttm)} revenue, "
                    f"{_usd(row.avg_ticket_ttm)} average ticket, {_usd(row.revenue_per_hour_ttm)} "
                    f"per productive hour, {_pct(row.cross_sell_rate_ttm)} cross-sell rate, "
                    f"{_pct(row.skincare_attach_rate_ttm)} skincare attach rate. All-time revenue "
                    f"{_usd(row.total_revenue_alltime)}."
                ),
            }
        )
    return docs


def _segment_docs(conn: SnowflakeConnection, t: str) -> list[dict]:
    s = _fq("mart", "mart_patient_segments", t)
    df = _df(
        conn,
        f"""
        select cluster_id, cluster_name, patient_count, avg_ltv, avg_annual_run_rate,
               dominant_category, top_provider_name, avg_recency_days,
               urgent_recall_count, active_patient_count
        from {s} order by avg_ltv desc
        """,
    )
    docs: list[dict] = []

    overview_lines = [
        f"{row.cluster_name} ({int(_f(row.patient_count)):,} patients, {_usd(row.avg_ltv)} avg LTV)"
        for row in df.itertuples()
    ]
    docs.append(
        {
            "doc_id": "snap_segment_overview",
            "title": "Patient segment overview",
            "source": "mart_patient_segments",
            "text": (
                f"The practice's patients fall into {len(df)} behavioral segments, highest to "
                f"lowest average lifetime value: " + "; ".join(overview_lines) + ". The highest-"
                "value segments concentrate the most revenue and warrant retention focus."
            ),
        }
    )

    for row in df.itertuples():
        docs.append(
            {
                "doc_id": f"snap_segment_{int(row.cluster_id)}",
                "title": f"Segment profile — {row.cluster_name}",
                "source": "mart_patient_segments",
                "text": (
                    f"Segment '{row.cluster_name}' has {int(_f(row.patient_count)):,} patients "
                    f"with {_usd(row.avg_ltv)} average lifetime value and "
                    f"{_usd(row.avg_annual_run_rate)} average annual run-rate. Its dominant "
                    f"service category is {CATS.get(row.dominant_category, row.dominant_category)}. "
                    f"The most common provider is {row.top_provider_name or 'n/a'}. Average "
                    f"recency is {int(_f(row.avg_recency_days))} days; "
                    f"{int(_f(row.active_patient_count)):,} are currently active and "
                    f"{int(_f(row.urgent_recall_count)):,} are urgent recall candidates."
                ),
            }
        )
    return docs


def _slug(name: str) -> str:
    return "".join(ch.lower() if ch.isalnum() else "_" for ch in str(name)).strip("_")


def _inventory_docs(conn: SnowflakeConnection, t: str) -> list[dict]:
    """Inventory snapshots (chunk-11): stock/true-margin summary + expiring lots."""
    status = _fq("mart", "mart_inventory_status", t)
    tm = _fq("mart", "mart_true_margin_by_service", t)
    inv = _fq("int", "int_inventory_movements", t)
    exp = _fq("mart", "mart_expiring_soon", t)

    tot = _df(conn, f"select sum(on_hand_value) v, count(*) n from {status}")
    total_value = _usd(tot.iloc[0]["v"])
    n_skus = int(_f(tot.iloc[0]["n"]))

    below = _df(
        conn,
        f"select sku_name, on_hand_quantity, par_level, stock_status from {status} "
        "where stock_status in ('out','low') order by stock_status, sku_name",
    )
    below_lines = [
        f"{r.sku_name} ({r.stock_status}, {int(_f(r.on_hand_quantity))} on hand vs par {int(_f(r.par_level))})"
        for r in below.itertuples()
    ]

    waste = _df(
        conn,
        "select sum(case when movement_type='waste' then quantity else 0 end)"
        " / nullif(sum(case when movement_type in ('consumption','waste') then quantity else 0 end),0) as rate,"
        " sum(case when movement_type in ('waste','expiry') then movement_cost else 0 end) as val "
        f"from {inv} where consumed_date >= dateadd('month', -12, current_date)",
    )
    waste_rate = _pct(waste.iloc[0]["rate"])
    waste_val = _usd(waste.iloc[0]["val"])

    surprises = _df(
        conn,
        f"select service_name, true_margin_pct, catalog_margin_pct, revenue_ttm from {tm} "
        "order by (catalog_margin_pct - true_margin_pct) desc nulls last limit 5",
    )
    surprise_lines = [
        f"{r.service_name}: true margin {_pct(r.true_margin_pct)} vs catalog {_pct(r.catalog_margin_pct)} "
        f"({_usd(r.revenue_ttm)} revenue TTM)"
        for r in surprises.itertuples()
    ]

    inventory_summary = {
        "doc_id": "snap_inventory_summary",
        "title": "Inventory summary: stock, true margin, and waste",
        "source": "mart_inventory_status",
        "text": (
            f"The practice holds {total_value} of consumable inventory across {n_skus} SKUs. "
            f"Trailing-twelve-month waste (overage + expiry write-offs) is {waste_val}, a waste "
            f"rate of {waste_rate} of units consumed. "
            + (f"Items below par or out of stock: {'; '.join(below_lines)}. " if below_lines else "All SKUs are at or above par. ")
            + "True margin (revenue net of real consumables cost) runs below the catalog margin "
            "because real acquisition cost, overage, and expiry exceed the list-price assumption. "
            "Biggest margin surprises: " + "; ".join(surprise_lines) + "."
        ),
    }

    edf = _df(
        conn,
        f"select sku_name, lot_number, days_to_expiry, quantity_remaining, "
        f"estimated_value_at_risk, urgency_level from {exp} "
        "where days_to_expiry <= 60 order by days_to_expiry asc",
    )
    exp_lines = [
        f"{r.sku_name} lot {r.lot_number}: {int(r.days_to_expiry)} days to expiry, "
        f"{int(_f(r.quantity_remaining))} remaining, {_usd(r.estimated_value_at_risk)} at risk ({r.urgency_level})"
        for r in edf.itertuples()
    ]
    total_at_risk = _usd(edf["estimated_value_at_risk"].astype(float).sum()) if len(edf) else "$0"
    expiring_summary = {
        "doc_id": "snap_expiring_summary",
        "title": "Inventory expiring soon",
        "source": "mart_expiring_soon",
        "text": (
            (
                f"{len(edf)} on-hand lots expire within 60 days, {total_at_risk} of product at risk. "
                "By urgency (critical <14 days, warning <30, watch <60): " + "; ".join(exp_lines) + ". "
                "Expiring stock should be used first (FIFO) or the loss booked as waste."
            )
            if len(edf)
            else "No on-hand inventory lots are expiring within the next 60 days."
        ),
    }
    return [inventory_summary, expiring_summary]


def build_documents(conn: SnowflakeConnection, tenant_id: str | None = None) -> list[dict]:
    """Assemble the full corpus (static definitions + live snapshots)."""
    tenant = tenant_id or get_settings().default_tenant_id
    docs: list[dict] = list(STATIC_DOCS)
    docs += _revenue_docs(conn, tenant)
    docs += _service_mix_doc(conn, tenant)
    docs += _recall_docs(conn, tenant)
    docs += _channel_doc(conn, tenant)
    docs += _provider_docs(conn, tenant)
    docs += _segment_docs(conn, tenant)
    docs += _inventory_docs(conn, tenant)
    log.info("build_documents", tenant=tenant, count=len(docs))
    return docs
