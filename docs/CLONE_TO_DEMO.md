# From Fresh Clone to Running Demo (60–90 minutes)

**Battle-tested on:** Mac Monterey 12.7.6 Intel (Aug 2, 2026)

This is a follow-the-script guide, not a tutorial. For the "why," see
[`SETUP.md`](SETUP.md). Budget **60–90 min** the first time (mostly downloads and
Docker pulls). Subsequent setups on a prepared machine: ~20 min.

---

## 1. Prerequisites (verified list, no aspirational)

Every tool below is **required**. Install commands and known gotchas per OS.

### For Mac (Intel or Apple Silicon)

#### Homebrew

```bash
/bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
```

**Monterey 12.x gotcha:** You'll see "Tier 3 support" warnings. This is fine —
Homebrew still works, just not officially supported.

#### Python 3.12

```bash
brew install python@3.12
brew link --overwrite python@3.12
```

**Monterey gotcha:** If you have old Python symlinks, `brew link` may fail. Run
the overwrite flag as shown.

Verify:
```bash
python3.12 --version   # → Python 3.12.x
```

#### Node 22

```bash
brew install node@22
brew link --overwrite node@22
```

**Ownership gotcha:** If `brew link` errors with "not writable," fix ownership first:
```bash
sudo chown -R $(whoami) /usr/local/include/node
brew link --overwrite node@22
```

Verify:
```bash
node --version   # → v22.x.x
```

#### Git and GitHub SSH setup

```bash
brew install git
```

**Full SSH walkthrough (if you don't already have keys on this machine):**

```bash
# 1. Generate a new SSH key (use your GitHub email)
ssh-keygen -t ed25519 -C "your_email@example.com"
# Press Enter to accept default file (~/.ssh/id_ed25519)
# Enter a passphrase (recommended) or leave blank

# 2. Start ssh-agent and add key
eval "$(ssh-agent -s)"
ssh-add ~/.ssh/id_ed25519

# 3. Copy public key to clipboard
pbcopy < ~/.ssh/id_ed25519.pub

# 4. Add to GitHub:
#    → github.com → Settings → SSH and GPG keys → New SSH key
#    → Paste and save

# 5. Test connection
ssh -T git@github.com
# → "Hi username! You've successfully authenticated..."
```

#### Docker Desktop — CRITICAL for Monterey

**⚠️ Monterey 12.x users: Docker Desktop 4.35+ dropped macOS 12 support.**

Download **Docker Desktop 4.34.x** (last Monterey-compatible version) from:
https://docs.docker.com/desktop/release-notes/

Do **NOT** use `brew install --cask docker` — it installs the latest (incompatible) version.

**Broken symlinks gotcha:** If you previously had Docker installed:
```bash
brew cleanup
# If docker command still broken:
sudo ln -sf /Applications/Docker.app/Contents/Resources/bin/docker /usr/local/bin/docker
sudo ln -sf /Applications/Docker.app/Contents/Resources/bin/docker-compose /usr/local/bin/docker-compose
```

**Credential helper gotcha:** If you see `docker-credential-desktop` errors:
```bash
# Edit ~/.docker/config.json and remove or comment out:
#   "credsStore": "desktop"
# Or delete the line entirely
```

Verify:
```bash
docker --version        # → Docker version 24.x or 25.x
docker info >/dev/null  # no errors = daemon running
```

#### AWS CLI

```bash
brew install awscli
aws --version   # → aws-cli/2.x.x
```

#### Astronomer CLI (Astro)

```bash
curl -sSL install.astronomer.io | sudo bash -s
astro version   # → Astro CLI Version: 1.x.x
```

#### Final prerequisite check

```bash
python3.12 --version && node --version && docker info >/dev/null && astro version && aws --version
```

All five should print versions with no errors.

---

### For Linux / WSL2

Same tools, different package manager:

```bash
# Python 3.12
sudo add-apt-repository ppa:deadsnakes/ppa -y
sudo apt update && sudo apt install python3.12 python3.12-venv python3.12-dev -y

# Node 22
curl -fsSL https://deb.nodesource.com/setup_22.x | sudo -E bash -
sudo apt install nodejs -y

# Git
sudo apt install git -y

# Docker (Docker Engine, not Desktop)
curl -fsSL https://get.docker.com | sudo bash
sudo usermod -aG docker $USER
# Log out and back in for group membership to take effect

# AWS CLI
curl "https://awscli.amazonaws.com/awscli-exe-linux-x86_64.zip" -o "awscliv2.zip"
unzip awscliv2.zip && sudo ./aws/install

# Astro CLI
curl -sSL install.astronomer.io | sudo bash -s
```

---

### For Windows

**Recommended:** Use WSL2 with Ubuntu 24.04 (matches the known-working Windows setup).

```powershell
# In PowerShell as Administrator:
wsl --install -d Ubuntu-24.04
```

Then open Ubuntu and follow the Linux/WSL2 instructions above.

---

## 2. Clone repos

```bash
mkdir -p ~/projects
cd ~/projects
git clone git@github.com:pneiman1/platform-core.git
git clone git@github.com:pneiman1/dermiq.git
```

---

## 3. Transfer secrets from previous machine

Three things need to travel from your old machine:

### The .env files

Both repos need their `.env` files:
- `~/projects/platform-core/.env`
- `~/projects/dermiq/.env`

**On the source machine:**
```bash
# Option A: Secure copy via SSH (if both machines on same network)
scp ~/projects/platform-core/.env newmac:~/projects/platform-core/.env
scp ~/projects/dermiq/.env newmac:~/projects/dermiq/.env

# Option B: AirDrop (Mac to Mac)
# Right-click each .env → Share → AirDrop

# Option C: Encrypted USB
# Copy to USB, transfer, delete from USB after

# Option D: Password manager with secure notes
# Paste contents into 1Password/Bitwarden secure note, retrieve on new machine
```

**On the new machine:** place files at:
```bash
~/projects/platform-core/.env
~/projects/dermiq/.env
```

### The Snowflake private key

```bash
# On source machine — copy the key file
scp ~/.ssh/snowflake_rsa_key.p8 newmac:~/.ssh/snowflake_rsa_key.p8

# On new machine — lock down permissions
chmod 600 ~/.ssh/snowflake_rsa_key.p8
```

**Verify `.env` has these set:**
```
SNOWFLAKE_PRIVATE_KEY_PATH=~/.ssh/snowflake_rsa_key.p8
SNOWFLAKE_PRIVATE_KEY_PASSPHRASE=<your-passphrase>
ANTHROPIC_API_KEY=<your-key>
```

---

## 4. Python environment setup (5 min)

```bash
cd ~/projects/dermiq
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -e "../platform-core[all]" -e ".[all]"
```

**Verify Snowflake key-pair auth works:**
```bash
python -c "from platform_core.warehouse.connection import test_connection; print(test_connection())"
# → dict with version/account/user/role/warehouse
# → NO MFA prompt = key-pair auth is working
```

---

## 5. Data pipeline (15 min)

Run from `~/projects/dermiq` with `.venv` active. Note the **two dbt passes** —
the segment marts read clustering output:

```bash
# Start source Postgres (auto-loads schema)
docker compose up -d

# Seed data
python scripts/seed_postgres.py          # ~3,500 patients, ~9,261 transactions
python scripts/seed_inventory.py         # lots / stock / consumption

# Ingest to Snowflake
python scripts/ingest_raw.py             # Postgres → Snowflake RAW

# dbt build (two passes)
make dbt-deps                            # first time only
make dbt-build                           # pass 1 — segment marts ERROR (expected)
python scripts/run_clustering.py         # k-means → INT_..._CLUSTER_ASSIGNMENTS
make dbt-build                           # pass 2 — now ERROR=0

# Build RAG corpus
python scripts/build_rag_corpus.py       # build + embed + write RAG_CORPUS
```

**Optional** — Canvas Save/Load table (only if you need layout persistence):

```bash
python - <<'PY'
from platform_core.warehouse.connection import get_snowflake_connection
with get_snowflake_connection(database="DERMIQ_DEV") as c:
    c.cursor().execute("CREATE TABLE IF NOT EXISTS DERMIQ_DEV.MART_DEL_MAR.CANVAS_LAYOUTS "
                       "(canvas_id VARCHAR PRIMARY KEY, tenant_id VARCHAR, title VARCHAR, "
                       "layout_json VARIANT, created_at TIMESTAMP_TZ DEFAULT CURRENT_TIMESTAMP(), "
                       "updated_at TIMESTAMP_TZ DEFAULT CURRENT_TIMESTAMP())")
print("CANVAS_LAYOUTS ready")
PY
```

---

## 6. Services (5 min — up to 3 terminals)

```bash
# Terminal 1 — API on :8000
cd ~/projects/dermiq && source .venv/bin/activate && make api-run

# Terminal 2 — Frontend on :3000
cd ~/projects/dermiq/frontend && npm install && npm run dev

# Terminal 3 — Airflow (OPTIONAL; pipeline already ran manually)
cd ~/projects/dermiq/airflow && astro dev start   # webserver at localhost:8080
```

> **Airflow is optional for the demo** — you ran the pipeline by hand in step 5.
> Start it only to show the three DAGs. Takes ~1 min to bring up 4 containers.

---

## 7. Verify (5 min)

```bash
curl -s -H "X-Tenant-ID: del_mar" localhost:8000/api/v1/health
# → {"status":"ok","snowflake_reachable":true}
```

**In the browser:**
- **`localhost:3000/executive`** — KPIs render; both story callouts show.
- **`localhost:3000/canvas`** — empty state ("Type a request below…").
- In Canvas, type **"Revenue by provider"** → bar chart in ~4s.
- **`localhost:3000/ai-studio`** — segment cards render.

---

## 8. Troubleshooting

| Symptom | Fix |
|---------|-----|
| **`brew link` fails "not writable"** | `sudo chown -R $(whoami) /usr/local/include/node` (or whatever path it complains about) |
| **Docker Desktop won't start on Monterey** | You installed 4.35+. Uninstall, download 4.34.x from release notes page. |
| **`docker-credential-desktop` not found** | Remove `"credsStore": "desktop"` from `~/.docker/config.json` |
| **Docker command not found after install** | `sudo ln -sf /Applications/Docker.app/Contents/Resources/bin/docker /usr/local/bin/docker` |
| **Snowflake auth fails / MFA prompt** | Check `SNOWFLAKE_PRIVATE_KEY_PATH` + `PASSPHRASE` in `.env`; `chmod 600` the key; confirm public key on user (`DESC USER`). |
| **API 500 / `snowflake_reachable:false`** | Token expired — restart `make api-run`. Known tech debt. |
| **Port 3000 in use** | `lsof -ti :3000 \| xargs kill -9` then `npm run dev` |
| **Anthropic 401 / credit_balance** | Verify `ANTHROPIC_API_KEY` in `.env`; need ≥$10 prepaid at console.anthropic.com |
| **dbt segment marts error** | Expected on first `make dbt-build`. Run `run_clustering.py` then `make dbt-build` again. |
| **Canvas `WidthProvider is not a function`** | `npm i react-grid-layout@1.5.0` |
| **`/chat` says "corpus is empty"** | Run `build_rag_corpus.py`, restart API (corpus cached in-process). |
| **Airflow UI won't load** | Check `astro dev start` logs; all 4 containers must be healthy. |
| **`pip install` fails on `cryptography`** | `brew install openssl rust` then retry. |
| **Node modules won't install** | Delete `node_modules` and `package-lock.json`, then `npm install`. |

---

## Quick reference: Full fresh-machine checklist

```bash
# 1. Install prereqs (see Section 1 for details)
brew install python@3.12 node@22 git awscli
brew link --overwrite python@3.12 node@22
# Install Docker Desktop 4.34.x manually for Monterey
curl -sSL install.astronomer.io | sudo bash -s

# 2. Clone
mkdir -p ~/projects && cd ~/projects
git clone git@github.com:pneiman1/platform-core.git
git clone git@github.com:pneiman1/dermiq.git

# 3. Transfer secrets (.env files + snowflake key)

# 4. Python env
cd ~/projects/dermiq
python3.12 -m venv .venv && source .venv/bin/activate
pip install -e "../platform-core[all]" -e ".[all]"

# 5. Pipeline
docker compose up -d
python scripts/seed_postgres.py
python scripts/seed_inventory.py
python scripts/ingest_raw.py
make dbt-deps && make dbt-build
python scripts/run_clustering.py
make dbt-build
python scripts/build_rag_corpus.py

# 6. Run
make api-run                           # Terminal 1
cd frontend && npm install && npm run dev  # Terminal 2

# 7. Verify
curl -s -H "X-Tenant-ID: del_mar" localhost:8000/api/v1/health
open http://localhost:3000/executive
```

---

*Last updated: Aug 2, 2026 — Mac Monterey 12.7.6 Intel setup*
