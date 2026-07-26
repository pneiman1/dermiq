# DermIQ — Pitches

Ways to describe DermIQ, tuned to the audience. All first-person ("I built" — I
built it solo). Numbers cited are from the synthetic-but-story-driven Del Mar
dataset (a fictional practice) unless noted; where I estimate a market I say so.
DermIQ is a portfolio project today — I don't claim customers I don't have.

> **The through-line phrase:** *"Type your dashboard into existence — grounded in
> the practice's own numbers, never made up."*

---

## 1. The 10-second pitch

> I built an analytics platform for cosmetic dermatology practices that turns a
> year of messy EMR data into a dashboard — and an AI you can just ask.

*Quotable:* "It's a data analyst for clinics that can't afford one."

---

## 2. The 30-second pitch (memorize this cold)

I built DermIQ, a vertical analytics platform for cosmetic dermatology practices.
These are $5M+ owner-operator clinics sitting on years of EMR, marketing, and
loyalty data with no analyst to make sense of it. DermIQ pulls it all into one
warehouse and turns it into the answers an owner actually needs — which providers
are profitable, which marketing to cut, which patients to call back — plus an AI
assistant that answers plain-English questions grounded in that practice's real
numbers. I built the whole thing end to end: data pipeline, ML, API, dashboard.

*Quotable:* "Every answer is grounded in the practice's own data — it can't make
a number up."

---

## 3. The 90-second pitch (recruiter phone screen)

**The problem.** Cosmetic dermatology is a booming, cash-pay business, but the
practices running it are small owner-operators. The data that would tell them how
the business is *actually* doing — their EMR, their ad spend, their loyalty
program — is fragmented across systems, and they can't justify a full-time data
analyst. So decisions get made on gut.

**The solution.** I built DermIQ, an end-to-end analytics platform for a
reference practice, "Del Mar Cosmetic Dermatology." It ingests the source systems,
models the data, and surfaces it as eight dashboard tabs plus an AI assistant.
And because it's built around real clinical intuition, the insights are the ones
that matter: it surfaces that a top provider's volume dropped ~60% during a
medical leave and is recovering slowly; that the Meta Ads channel is acquiring
low-LTV patients at a bad LTV:CAC ratio; that Botox waste is running ~4.6% of
units consumed and there's ~$28K of inventory expiring in the next month.

**The stack.** Postgres source → Python ingestion into Snowflake → dbt for the
medallion transform (staging, intermediate, marts) → FastAPI → a Next.js
dashboard, all orchestrated by Airflow via Astronomer Cosmos. The AI is
retrieval-augmented generation over the marts, and there's a "Canvas" tab where
you type a request and an LLM composes the chart.

**The demo moment.** On the Canvas tab I type "revenue by provider" and a real
chart builds itself in about four seconds — the model composes a validated spec
over the actual data, so there are no hallucinated numbers.

**Why it matters.** It's a complete, production-shaped data platform I built solo —
warehouse, transformation, orchestration, ML, API, front end, and two LLM
features — not a notebook. It's the shape of a real vertical SaaS.

*Quotable:* "It's not a notebook — it's a production-shaped platform, built solo,
end to end."

---

## 4. The 3-minute technical deep-dive (data-engineer coffee chat)

So the shape is a medallion warehouse on Snowflake. A Nextech-shaped Postgres
source gets full-refreshed into a RAW layer by a Python job that declares explicit
Snowflake column types rather than letting pandas infer them — because an all-null
source column infers as NUMBER and breaks the downstream cast, which I learned the
annoying way and wrote an ADR about.

From RAW, dbt Core takes over: staging is thin typed views one-to-one with source,
intermediate is the reusable business logic as tables — visit economics, patient
LTV, provider-daily rollups — and marts are the consumer-facing tables, one per
dashboard tab. The dependency graph is all `ref()`-driven, and I override
`generate_schema_name` so schemas land as `LAYER_TENANT` — the same convention my
Python ingestion uses, so both sides agree on where data lives.

Orchestration is Airflow through Astronomer Cosmos. Cosmos is the nice part: it
parses the dbt project at DAG-parse time and renders each model as its own Airflow
task in a task group, so I get per-model retries and native graph visibility
instead of one opaque `dbt build`. There are three DAGs — the daily ingest+dbt
pipeline, a weekly k-means re-clustering job that rebuilds the segment marts, and
a daily RAG-corpus refresh.

Auth across all of it is Snowflake key-pair JWT — the account enforced MFA, which
killed headless password auth, so everything signs a short-lived JWT with a
private key.

Two LLM features sit on top. The AI assistant is RAG: I build a small corpus from
the marts, embed with sentence-transformers, store the vectors as JSON in a
VARCHAR column, and do in-process cosine retrieval before generating with Claude —
deliberately no warehouse VECTOR type so the store stays portable. The Canvas tab
is the interesting one: instead of letting the LLM write SQL, I give it tool-use
with one tool per chart type, so it returns a *validated* chart spec against a
curated schema, and that spec resolves to a parameterized query. No model-authored
SQL, no hallucinated columns.

And here's what makes it interesting from a data-engineering perspective: the LLM
never touches the warehouse directly — it composes a constrained spec that my code
validates and executes. That's the pattern I'd defend hardest: you get natural-
language flexibility with the safety and determinism of a fixed grammar.

*Quotable:* "The LLM composes a validated spec, not SQL — flexibility with the
safety of a fixed grammar."

---

## 5. The 5-minute founder pitch (if I ever sell this)

**Market.** Cosmetic dermatology and medical aesthetics is a large, fast-growing,
mostly cash-pay market — the US med-spa/aesthetics space is on the order of $15–20B
and compounding double digits (rough industry figures). The buyers I care about
are multi-provider cosmetic derm practices doing $5M+ a year — there are on the
order of a few thousand of them in the US. Priced as vertical SaaS at, say,
$1–2K/month, that's a serviceable market in the low hundreds of millions of ARR.
These are back-of-envelope numbers, but the point holds: it's a real, monetizable,
underserved niche.

**Problem.** These practices are owner-operated. The owner is a physician, not an
analyst, and the business data — EMR, ad platforms, the Allē/ASPIRE loyalty
programs — is scattered and unqueryable. They can't justify a data hire, so they
fly blind on exactly the decisions that move the P&L: provider productivity,
marketing ROI, patient recall, inventory waste.

**Solution.** DermIQ is vertical SaaS with the clinical intuition baked into the
data model. It's not a generic BI tool you have to configure — it already knows
what a Botox unit costs, what a lapsing patient is worth, and what a healthy
LTV:CAC looks like for RealSelf vs Meta. And it has an AI layer: an assistant that
answers grounded questions, and a Canvas that builds any chart you ask for.

**Traction.** Honest version: it's a fully working end-to-end product on a
realistic synthetic practice — the whole pipeline, ML, and both AI features run.
The next step is design partners: three real practices to swap the synthetic data
for their live feeds through the same ingestion path.

**Moat.** The vertical-specific data model and an LLM grounded *in* it. A generic
tool can render a chart; it can't tell a Del Mar owner that Meta is their worst
channel by LTV:CAC because it doesn't have the model or the numbers. The moat
compounds: every clinic's data makes the benchmarks sharper.

**Ask.** I'm looking for feedback and intros — specifically to cosmetic derm
practice owners or operators who'd give me 20 minutes, and to anyone who's built
vertical SaaS in healthcare. If you're an angel who invests early, I'd take a
first check to fund design-partner onboarding.

*Quotable:* "It's not generic BI you configure — it ships already knowing what a
Botox unit costs and what a lapsing patient is worth."

---

## 6. Resume bullets (5 lengths)

**1 line:**
- Built **DermIQ**, an end-to-end analytics + AI platform for cosmetic dermatology practices (Snowflake, dbt, Airflow, FastAPI, Next.js, Anthropic Claude).

**2 lines:**
- Built **DermIQ**, a solo end-to-end vertical analytics platform: Postgres → Snowflake → dbt medallion warehouse → FastAPI → Next.js, orchestrated with Airflow (Astronomer Cosmos).
- Added two LLM features — a RAG assistant grounded in the warehouse marts and an LLM-composed "type-it-into-existence" chart builder.

**3 lines:**
- Built **DermIQ**, an end-to-end vertical analytics platform for cosmetic dermatology practices, solo: Python ingestion → Snowflake → **dbt** medallion models (staging/intermediate/marts) → **FastAPI** → **Next.js** dashboard (8 tabs).
- Orchestrated the daily pipeline, weekly k-means patient re-clustering, and RAG-corpus refresh with **Airflow** via **Astronomer Cosmos** (per-model task rendering); migrated all warehouse auth to Snowflake **key-pair JWT** under MFA enforcement.
- Shipped a **RAG** assistant (sentence-transformers embeddings, in-process cosine, **Anthropic Claude**) and an LLM chart composer using tool-use to emit validated, injection-safe chart specs.

**4 lines:**
- Designed and built **DermIQ** solo — a production-shaped, multi-layer vertical analytics platform for cosmetic dermatology practices — from a Nextech-shaped Postgres source through a Snowflake medallion warehouse to a Next.js dashboard.
- Modeled the warehouse in **dbt Core** (9 staging views, 6 intermediate tables, 9 marts) with a custom schema-naming macro, referential/enum/business-rule tests, and `ref()`-driven lineage; ingestion declares explicit Snowflake types to prevent inference bugs.
- Orchestrated three **Airflow** DAGs via **Astronomer Cosmos** (daily ingest+dbt, weekly ML re-clustering, daily RAG refresh); authenticated every headless service with Snowflake **key-pair JWT**.
- Built two AI features on **Anthropic Claude**: a retrieval-augmented assistant grounded in the marts, and a natural-language **Canvas** that uses LLM tool-use to compose validated chart specs (no model-authored SQL). **Stack:** Python, TypeScript, Snowflake, dbt, Airflow, FastAPI, React/Next.js, Docker.

---

## 7. LinkedIn post

> I spent the last few weeks building something I'm genuinely proud of, and it's
> finally at a place I can show it.
>
> It's called **DermIQ** — an end-to-end analytics platform for cosmetic
> dermatology practices. These are $5M+ owner-operated clinics sitting on years of
> EMR, marketing, and loyalty data, with no analyst to make sense of it. Decisions
> get made on gut.
>
> So I built the thing that would make sense of it — solo, end to end:
>
> • A full data pipeline: Postgres → Snowflake → dbt (medallion warehouse) →
>   FastAPI → a Next.js dashboard, all orchestrated by Airflow.
> • Real insights, not vanity charts: it flags a top provider whose volume dropped
>   ~60% during a medical leave, a marketing channel bleeding money on low-LTV
>   patients, and ~$28K of inventory quietly about to expire.
> • Two AI features: an assistant that answers plain-English questions grounded in
>   the practice's *actual* numbers (so it can't make one up), and a "Canvas" where
>   you type "revenue by provider" and the chart builds itself in ~4 seconds.
>
> The part I'm proudest of: the AI never writes SQL or invents figures. It composes
> a validated spec over the real data model. Flexibility, with guardrails.
>
> It's a portfolio project for now — the data is synthetic but modeled on a real
> practice. I'd love feedback, especially from data engineers and anyone who knows
> the aesthetics space. And if you run or know a cosmetic derm practice, I'd love
> 20 minutes to see if this solves a real problem.
>
> Demo + write-up: [link]
>
> #DataEngineering #Analytics #AI #VerticalSaaS

*Quotable:* "The AI never writes SQL or invents figures — it composes a validated
spec over the real data model."

---

## 8. Twitter/X thread (6 tweets)

**1/**
I built an analytics platform for cosmetic dermatology practices — solo, end to
end. Data pipeline, ML, an AI you can just ask, and a dashboard that builds
charts from a sentence. Here's what's under the hood 🧵

**2/**
The problem: these are $5M+ owner-operated clinics drowning in EMR + marketing +
loyalty data, with no analyst. So it's all gut calls on provider productivity,
ad ROI, patient recall, inventory waste.

**3/**
The stack: Postgres → Snowflake → dbt (medallion: staging/intermediate/marts) →
FastAPI → Next.js. Three Airflow DAGs via Astronomer Cosmos handle daily ingest,
weekly k-means re-clustering, and a RAG refresh. Everything auths with Snowflake
key-pair JWT.

**4/**
It surfaces real things, not vanity metrics: a top provider down ~60% on medical
leave, a Meta Ads channel with a bad LTV:CAC, ~4.6% Botox waste, ~$28K of stock
about to expire. Numbers an owner would actually act on.

**5/**
The fun part: two LLM features. A RAG assistant grounded in the warehouse marts.
And "Canvas" — you type "revenue by provider" and a real chart builds itself in
~4s. The model composes a *validated spec*, never raw SQL, so no hallucinated
columns.

**6/**
It's a portfolio project (synthetic data, modeled on a real practice), but it's
production-shaped. Demo + write-up 👉 [link]. Would love feedback from data folks
and anyone in aesthetics — what would you ask it first?

*Quotable:* "You type a sentence; a real chart builds itself — from a validated
spec, never raw SQL."

---

## 9. Cold email to a cosmetic derm practice owner

**Subject:** A quick tool I built for practices like yours — 15 min?

Hi Dr. [Name],

I'll keep this short. I've been building a tool that takes a cosmetic derm
practice's own data — patient visits, providers, marketing, inventory — and turns
it into the handful of answers an owner actually wants: which providers are most
profitable, which marketing is worth the spend, which patients are slipping away,
and where money is leaking on wasted or expiring product.

I built it around how these practices really run, not as a generic dashboard. It
even has an assistant you can just ask questions in plain English, and it only
answers from your real numbers.

Right now it runs on a realistic sample practice. Before I take it further, I want
to make sure it solves a problem you actually have — not one I imagined.

Would you give me 15 minutes to show you and tell me where I'm wrong? No pitch, no
obligation, nothing to buy. I mostly want your honest reaction.

Thanks either way,
Phil
[link] · [phone]

*Quotable:* "I want to make sure it solves a problem you actually have — not one I
imagined."

---

## 10. Cold DM to a data-engineering hiring manager

Hi [Name] — I've been following [team/company] and admire [specific thing]. I
recently built a solo end-to-end data platform I think you'd have opinions on:
Snowflake + dbt medallion warehouse, Airflow via Astronomer Cosmos (per-model dbt
task rendering), key-pair JWT auth, and two LLM features — RAG over the marts and
an LLM chart-composer that emits validated specs instead of raw SQL.

I'm not asking for a job — I'd genuinely value 15 minutes of your feedback on the
architecture, especially the LLM-as-spec-composer pattern and how I'd take the
orchestration to production. Demo + write-up here: [link].

Happy to send specific questions ahead of time so it's worth your while.

*Quotable:* "An LLM chart-composer that emits validated specs instead of raw SQL —
I'd love your read on the pattern."

---

## Notes for delivery

- **Register:** casual and human for LinkedIn/Twitter/cold outreach; precise and
  unhedged for the technical deep-dive; warm and low-pressure for the practice-owner
  email.
- **Honesty:** always say "portfolio project / synthetic data" — it lands better
  than implying customers. The work speaks for itself.
- **Numbers to keep in your pocket** (all from the Del Mar dataset): 3,500 patients,
  7 providers, 38 services, ~9,261 transactions over 18 months; provider on ~60%
  reduced volume during leave; Meta Ads = worst LTV:CAC channel; ~4.6% Botox waste;
  ~$28K expiring within 30 days; 7 k-means patient segments; 8 dashboard tabs.
- **Every pitch has one quotable line** (marked above) — say it slowly and let it
  land.
