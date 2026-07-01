# DermIQ

Analytics intelligence platform for cosmetic dermatology practices.

DermIQ surfaces operational and financial insights from a clinic's EMR, marketing platforms, and loyalty programs — turning a year of fragmented data into a single Monday-morning brief, ranked recall queue, and AI-powered chatbot.

## Status

Early development. The first vertical product on top of [`platform-core`](https://github.com/pneiman1/platform-core).

## Supported platforms

macOS (Intel & Apple Silicon), Linux, and Windows via WSL2. See
[`docs/SETUP.md`](docs/SETUP.md) for per-platform steps and
[`docs/MACOS-NOTES.md`](docs/MACOS-NOTES.md) for Apple Silicon gotchas.

## Getting started

See [`docs/SETUP.md`](docs/SETUP.md) for the full step-by-step: install Node +
clone alongside platform-core, install both in editable mode, start the Postgres
source database, seed synthetic data, run ingestion → dbt → API → the Next.js
dashboard at `localhost:3000`.

Architecture decisions specific to DermIQ are logged in
[`docs/DECISIONS.md`](docs/DECISIONS.md); shared platform decisions live in
platform-core's decision log.

## Built for cosmetic dermatology practices that

- Run on Nextech, Modernizing Medicine, or PatientNow
- Have 3+ providers and \$5M+ in annual revenue
- Use Allē or ASPIRE loyalty programs
- Spend on Google Ads, Meta Ads, or Realself
- Need to make data-driven decisions about provider productivity, marketing ROI, inventory waste, and patient recall

## License

TBD — currently all rights reserved.
