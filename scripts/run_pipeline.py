"""Run the whole pipeline without Airflow.

Useful for the demo, for marking, and for anyone who does not want to stand
up a scheduler just to see the project work.
"""
import json, os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.db import init_db
from app.pipeline import run_all

if __name__ == "__main__":
    init_db()
    result = run_all()
    print(json.dumps(result, indent=2))
