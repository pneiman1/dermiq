# DermIQ — Demo Script (~90 seconds)

> **Draft.** No demo script had been finalized previously — this is a first cut
> built from the actual shipped tabs and data. Adjust timing/wording to taste.

The goal: show DermIQ turning a year of fragmented practice data into decisions,
ending on the AI assistant. Reference tenant: **Del Mar Cosmetic Dermatology**.

## Beat sheet

| Time | Tab | Do / say |
|---|---|---|
| 0:00–0:10 | **Executive** | Land here. "This is a year of one practice's data in one view." Point at the revenue trend (January slump, April–May wedding-season spike) and the category mix. |
| 0:10–0:25 | **Providers** | "Ranked by revenue per hour, not raw revenue." Call out the provider on medical leave (volume dip) and the rising star (up ~30% YoY). |
| 0:25–0:40 | **Marketing** | "Every channel by LTV:CAC." Point at a paid channel flagged unprofitable vs. referral/organic — "this is where the next dollar shouldn't go." |
| 0:40–0:52 | **Recall** | "Patients lapsing, ranked, with revenue at risk." Note the total annual LTV at risk if no one re-engages them. |
| 0:52–1:05 | **Inventory** | The chunk-11 highlight. "True margin — real cost of goods, not list price." Point at a service where true margin sits well below catalog margin, then the "expiring soon" lots with value at risk. |
| 1:05–1:30 | **AI Studio** | The closer. Type: **"What inventory is expiring soon and what's the value at risk?"** Let the grounded answer stream in, citing the practice's own numbers. "Every answer is grounded in this practice's marts — no hallucinated figures." |

Optional 10s tail: hover the shimmer wordmark / toggle dark mode to show polish.

## OBS setup

- **Canvas:** 1920×1080 (record at 1440p source if the display allows; scale down).
- **Capture:** Window Capture on the browser, not full display (hides the taskbar/other apps).
- **Browser:** full-screen or a clean window at ~1440px wide; zoom 100%.
- **Notifications OFF:** enable Do Not Disturb (OS + Slack/email) before recording.
- **Cursor:** enable "show cursor"; consider a subtle click-highlight.
- **Audio:** if narrating, noise-suppression filter on the mic; test levels first.
- **Frame rate:** 30fps is plenty; 60fps only if showing the shimmer motion closely.

## Pre-recording checklist

- [ ] `docker ps` is clean — only `dermiq-postgres` + the airflow stack running; no
      stray/exited containers cluttering the environment.
- [ ] Pipeline is fresh: `seed_postgres` → `seed_inventory` → `ingest_raw` → `dbt build`
      have all run; marts are populated.
- [ ] RAG corpus rebuilt (`scripts/build_rag_corpus.py`) **and API restarted** so the
      corpus cache is current (needed for the AI Studio beat).
- [ ] API healthy: `curl -s -H "X-Tenant-ID: del_mar" localhost:8000/api/v1/health`
      returns `snowflake_reachable: true`. (If false, the connection expired —
      restart the API.)
- [ ] **Warm the query cache:** click through all 7 tabs once so the demo run is snappy
      (first load per tab hits Snowflake cold).
- [ ] Frontend on `localhost:3000`, single dev server (no stray second instance on
      3001), styled correctly (hard-refresh once).
- [ ] Pick the light/dark theme you want on camera and set it before recording.
- [ ] Have the AI Studio question copied to clipboard (or typed slowly on purpose).
