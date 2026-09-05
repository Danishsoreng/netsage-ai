"""Configuration for NetSage AI.

Reads settings from environment variables so the same code runs on a laptop
(SQLite) and on a real deployment (PostgreSQL) without edits.
"""
import os

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _load_env_file(path=os.path.join(PROJECT_ROOT, ".env")):
    """Read KEY=value lines out of a .env file into the environment.

    Written by hand rather than pulled in as a dependency so there is nothing
    hidden here: copy .env.example to .env, paste your key in, press Run.
    Anything already set in the real environment wins, so an export or a
    PyCharm run-configuration variable still overrides the file.
    """
    if not os.path.isfile(path):
        return
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            key, value = key.strip(), value.strip().strip("'\"")
            if key and key not in os.environ:
                os.environ[key] = value


_load_env_file()

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------
# Production / assignment target: PostgreSQL
#   postgresql+psycopg2://netsage:netsage@localhost:5432/netsage
# Fallback for quick local demos with no server installed: SQLite file.
DATABASE_URL = os.environ.get(
    "NETSAGE_DATABASE_URL",
    "sqlite:///" + os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
        "data", "netsage.db",
    ),
)

# ---------------------------------------------------------------------------
# AI assistant
# ---------------------------------------------------------------------------
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
AI_MODEL = os.environ.get("NETSAGE_AI_MODEL", "claude-opus-5")

# When no API key is present the assistant falls back to a local heuristic
# engine so the pipeline still runs end to end. Every diagnosis records which
# engine produced it, so results are never silently mixed up.
AI_ENABLED = bool(ANTHROPIC_API_KEY)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
CASE_INTAKE_DIR = os.environ.get(
    "NETSAGE_CASE_DIR", os.path.join(PROJECT_ROOT, "data", "cases")
)

# Confidence below this is flagged in the UI as "needs closer human look".
LOW_CONFIDENCE_THRESHOLD = 0.55
