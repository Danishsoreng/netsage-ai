"""Start NetSage AI. This is the file to run in PyCharm.

It does three things, in order:

    1. create the tables if they are not there yet
    2. seed the database from data/cases/*.json the first time only, so the
       console and the overview screen have something to show
    3. serve the Flask app on http://127.0.0.1:5000

Nothing here calls the AI. Seeding runs the deterministic checker and then one
diagnosis per case through app/ai_assistant.py, which uses the local heuristic
engine unless ANTHROPIC_API_KEY is set - so a first run works offline.

Environment (all optional, see .env.example):
    NETSAGE_DATABASE_URL   PostgreSQL URL; omit for the SQLite fallback
    ANTHROPIC_API_KEY      turns on the Claude engine
    NETSAGE_SEED           set to 0 to skip first-run seeding
    NETSAGE_PORT           default 5000
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import pipeline
from app.config import AI_ENABLED, AI_MODEL, DATABASE_URL
from app.db import init_db, session_scope
from app.models import Case
from app.web import app


def seed_if_empty():
    """Run the batch pipeline once, only when there is nothing in the tables."""
    with session_scope() as s:
        if s.query(Case).count():
            return None
    print("Empty database - running the pipeline once to seed it...")
    result = pipeline.run_all()
    print("  ingest:    %s" % result["ingest"])
    print("  rules:     %s" % result["rules"])
    print("  diagnoses: %s" % result["diagnoses"])
    return result


def main():
    init_db()
    if os.environ.get("NETSAGE_SEED", "1") != "0":
        seed_if_empty()

    port = int(os.environ.get("NETSAGE_PORT", "5000"))
    engine = ("claude (%s)" % AI_MODEL) if AI_ENABLED else "heuristic (no API key)"

    print("")
    print("NetSage AI")
    print("  database : %s" % DATABASE_URL)
    print("  ai engine: %s" % engine)
    print("")
    print("  console  : http://127.0.0.1:%d/" % port)
    print("  overview : http://127.0.0.1:%d/overview" % port)
    print("  queue    : http://127.0.0.1:%d/queue" % port)
    print("  dashboard: http://127.0.0.1:%d/dashboard" % port)
    print("  health   : http://127.0.0.1:%d/api/health" % port)
    print("")

    # use_reloader off: the reloader re-imports this module and would print the
    # banner twice, which reads like the server started twice.
    app.run(host="127.0.0.1", port=port, debug=True, use_reloader=False)


if __name__ == "__main__":
    main()
