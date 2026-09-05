"""Create the database tables. Run once before the first pipeline run."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import DATABASE_URL
from app.db import init_db

if __name__ == "__main__":
    init_db()
    print(f"Tables created on: {DATABASE_URL}")
