# NetSage AI

An AI-assisted network fault triage tool with a mandatory human review step.

Given a symptom and some `show` command output, it proposes the most likely
root cause with evidence, a confirming command, and a fix — then requires a
person to accept, edit, or reject that proposal before it counts.

**Stack:** Flask · PostgreSQL · Apache Airflow · Anthropic API

For a plain-language walkthrough suitable for a viva or presentation, read
[`docs/NON_TECHNICAL_REPORT.md`](docs/NON_TECHNICAL_REPORT.md). For a longer
one that also covers the networking involved and explains every box on every
screen, read [`docs/HOW_NETSAGE_WORKS.md`](docs/HOW_NETSAGE_WORKS.md).

---

## Architecture

```
data/cases/*.json
      │
      ▼
 ┌──────────┐   Airflow DAG: netsage_pipeline (@hourly)
 │  ingest  │   ── every task calls app/pipeline.py ──
 └────┬─────┘
      ▼
 ┌──────────────┐   plain Python, no model, deterministic
 │ rule checker │   → rule_findings table
 └────┬─────────┘
      ▼
 ┌──────────────┐   Claude API (structured JSON) or local fallback
 │ AI diagnosis │   → diagnoses table
 └────┬─────────┘
      ▼
 ┌──────────────┐   Flask · the only place a proposal is confirmed
 │ human review │   → reviews table
 └────┬─────────┘
      ▼
   dashboard + responsible-AI log
```

The rule checker runs **before** the AI on purpose: its findings are passed
into the prompt as established facts, so the model reasons with them rather
than around them.

A case can enter this pipeline two ways, and both run the same code. The
Airflow DAG (or `scripts/run_pipeline.py`) walks `data/cases/*.json` in batch.
The console at `/` posts one case at a time to `app/api.py`, which calls the
same `rule_checker.check()` and `ai_assistant.diagnose()` and writes to the
same four tables. There is no second implementation of the logic anywhere.

---

## Setup

```bash
pip install -r requirements.txt
```

### Option A — PostgreSQL (the target setup)

```bash
createdb netsage
export NETSAGE_DATABASE_URL="postgresql+psycopg2://netsage:netsage@localhost:5432/netsage"
```

Tables are created automatically. `schema.sql` has the same schema by hand if
you prefer to provision it up front.

### Option B — SQLite (zero setup, for a quick demo)

Set nothing. The app falls back to `data/netsage.db`.

### AI engine

Copy `.env.example` to `.env` and put your key in it:

```
ANTHROPIC_API_KEY=sk-ant-...
```

`app/config.py` reads `.env` on startup, so PyCharm's Run button picks it up
with no extra setup. An exported shell variable still overrides the file.

Diagnoses go through the official `anthropic` SDK on `claude-opus-5`, using a
**structured output schema** (`ProposedDiagnosis` in `app/ai_assistant.py`):
the seven fields, the 0-1 confidence range and the eight fault-type names are
enforced by the API itself, so a proposal cannot come back malformed,
half-filled, or in a category the dashboard does not recognise.

Without a key the pipeline uses a local heuristic engine so everything still
runs end to end. Every diagnosis records its `engine` field (`claude` or
`heuristic`), so the two are never confused.

---

## Running

**Everything, one command** (this is the PyCharm run configuration `NetSage`):

```bash
python run.py
```

It creates the tables, seeds them from `data/cases/*.json` on the first run
only, and serves:

| URL | what it is |
| --- | --- |
| `/` | the triage console - describe a fault, get findings and a proposal, decide |
| `/overview` | the pipeline overview, every number read live from the tables |
| `/queue` | the server-rendered case queue |
| `/case/<ref>` | one case with the full review form |
| `/dashboard` | the server-rendered metrics page |
| `/api/health` | engine and database status |

**In PyCharm:** open the project, set the interpreter to `.venv`, then pick the
`NetSage` run configuration and press Run. Set `ANTHROPIC_API_KEY` in the
configuration's environment variables to switch the AI engine from `heuristic`
to `claude`.

**Batch pipeline only, no web server:**

```bash
python scripts/init_db.py
python scripts/run_pipeline.py
```

**With Airflow:**

```bash
export NETSAGE_PROJECT_ROOT=$(pwd)
export PYTHONPATH=$(pwd):$PYTHONPATH
cp airflow/dags/netsage_pipeline.py $AIRFLOW_HOME/dags/
airflow dags trigger netsage_pipeline
```

---

## Layout

```
run.py             start here - init, first-run seed, then serve
app/
  config.py        env-driven settings
  models.py        four tables: cases, rule_findings, diagnoses, reviews
  db.py            engine + session scope
  rule_checker.py  8 deterministic checks, no AI
  ai_assistant.py  Claude call (SDK, schema-enforced) + fallback + chat()
  pipeline.py      the four stages, called by both Airflow and the CLI
  web.py           Flask routes + the two console pages
  api.py           the JSON API the console UI runs on
  templates/       queue, case detail, dashboard
netsage-ui/        the console UI: two design files + their runtime
airflow/dags/      the DAG (orchestration only, no logic)
scripts/           init_db.py, run_pipeline.py
data/cases/        30 seed cases
docs/              non-technical report
schema.sql         PostgreSQL DDL for reference
```

---

## Scope and honest limits

Verified working: ingest of 30 cases, 17 deterministic findings raised, 30
diagnoses produced, the full review loop, and the dashboard including the
correction log. Also verified end to end through the console UI in a browser:
a case typed into `/` is checked, diagnosed, written to all four tables, and a
decision taken on screen shows up in `/api/metrics` and on `/overview`. Tested
against SQLite with the heuristic engine.

Not verified: live Claude calls through `/api/triage` and `/api/chat`. Both go
through `app/ai_assistant.py`, whose Claude path has never been executed here -
without a key the server answers from the heuristic engine and `/api/chat`
says plainly that no engine is reachable rather than inventing an answer.

The two console pages load React and three.js from CDNs, so they need internet
access to render even though the API does not.

Also verified: the deterministic checker and its in-browser fallback copy
produce identical findings on the same input.

Not yet verified: a PostgreSQL run and an Airflow scheduler run. The code paths
exist and the DAG compiles, but they have not been executed in this
environment.

Known limits:

- Reads pasted command output; does not connect to live devices.
- Proposes fixes; does not apply them.
- The dashboard's category-match figure is measured on the same seed cases the
  system was built around. It shows consistency on known cases, **not**
  real-world accuracy — the dashboard states this on screen.
- Accuracy on unseen faults is unmeasured.
- The rule checker's text parsing assumes the layout used in the seed cases;
  real device output will need the patterns widened.
