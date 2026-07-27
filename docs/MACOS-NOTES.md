# macOS-specific notes

Gotchas that bite on a fresh Mac. Applies to both Intel and Apple Silicon unless
noted. The main setup flow is in [`SETUP.md`](SETUP.md).

## Python: Homebrew vs system Python

macOS ships its own Python, and Homebrew installs another. They can shadow each
other and leave you with a venv built from the wrong interpreter.

- Always invoke **`python3.12`** explicitly when creating venvs:
  `python3.12 -m venv .venv`.
- Or use [`pyenv`](https://github.com/pyenv/pyenv) (`brew install pyenv`,
  `pyenv install 3.12`, `pyenv local 3.12`) to pin the version per project.
- Confirm the venv's interpreter after activating: `python --version` → `3.12.x`.

## Docker Desktop on Apple Silicon

- The Postgres image (`postgres:16-alpine`) is **multi-arch**, so it runs
  **natively (arm64)** on Apple Silicon — no emulation, full speed.
- If you ever run an amd64-only image, Docker uses Rosetta/QEMU emulation, which
  is noticeably slower and occasionally flaky. Prefer multi-arch images.
- Intel Macs run everything amd64 natively; no special handling.

## macOS Sonoma+ Full Disk Access

On Sonoma and later, the OS may block your terminal from reading files in certain
locations until you grant it permission. If scripts can't read files they should:
**System Settings → Privacy & Security → Full Disk Access → enable your terminal**
(Terminal / iTerm / VS Code), then restart the terminal.

## Snowflake driver on ARM64

The Snowflake Python connector ships native arm64 wheels — it works on Apple
Silicon without emulation. Verify your interpreter is native:

```bash
python -c "import platform; print(platform.machine())"   # 'arm64' on Apple Silicon
```

If it prints `x86_64` on an Apple Silicon Mac, your Python is running under Rosetta
— reinstall a native arm64 Python (Homebrew's `python@3.12` is native).

## Homebrew formula names vs apt package names

The same tool is often named differently across package managers:

| Tool | macOS (Homebrew) | Linux / WSL2 (apt) |
|---|---|---|
| AWS CLI | `awscli` | `awscli` (or the official bundle installer) |
| Astronomer CLI | `astro` | install script: `curl -sSL https://install.astronomer.io \| sudo bash` |
| Node.js | `node` (or `node@22`) | `nodejs` (via NodeSource or `nvm`) |
| PostgreSQL client | `libpq` (then link `psql`) | `postgresql-client` |
| Python 3.12 | `python@3.12` | `python3.12` + `python3.12-venv` |

When a `brew install <x>` "package not found" error appears, check this table —
the apt name and the brew name rarely match exactly.

## sentence-transformers / PyTorch first run (RAG, chunk-10)

`scripts/build_rag_corpus.py` embeds locally with `sentence-transformers`, which
pulls in **PyTorch**. On Apple Silicon this is fine — torch ships native arm64
wheels and the model runs on CPU (no MPS/CUDA needed for a ~30-doc corpus). Two
things to expect on the very first run:

- A one-time **model + weights download** (`all-MiniLM-L6-v2`, plus the torch
  wheels at install time) — needs network and a minute or two.
- The first embed call is slow (model load); subsequent runs are fast.

If you're offline or torch failed to install natively, the corpus build is the only
step that breaks — the rest of the pipeline and the dashboard are unaffected.

## react-grid-layout version pin (Canvas, chunk-12)

The Canvas tab uses `react-grid-layout`. A plain `npm install react-grid-layout`
now pulls **v2.x, which removed the `WidthProvider` HOC** the Canvas page uses
(v2 moved to hooks), while `@types/react-grid-layout` is still v1 — so you get a
runtime `WidthProvider is not a function`. The repo **pins `react-grid-layout@1.5.0`**
in `package.json` for this reason; a normal `npm install` respects the pin. Only if
you manually upgrade it will Canvas break. Not Mac-specific, but it bites on a fresh
`npm install` and the error is opaque.

## Anthropic SDK on Apple Silicon

No gotcha — the `anthropic` Python SDK is pure Python (HTTP client), so it runs
natively on arm64 with nothing to compile. If `/chat` or Canvas generation returns
a 401/credit error, it's the account (missing `ANTHROPIC_API_KEY` or no prepaid
credit), not the platform.
