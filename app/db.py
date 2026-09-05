"""Engine and session handling.

One place that knows how to open a database connection, so the Flask app,
the Airflow DAG and the CLI scripts all share identical behaviour.
"""
from contextlib import contextmanager

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import DATABASE_URL
from app.models import Base

_connect_args = {}
if DATABASE_URL.startswith("sqlite"):
    # Needed so the Flask dev server and background jobs can share the file.
    _connect_args = {"check_same_thread": False}

engine = create_engine(DATABASE_URL, future=True, connect_args=_connect_args)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False, future=True)


def init_db():
    """Create all tables if they do not already exist."""
    Base.metadata.create_all(engine)


@contextmanager
def session_scope():
    """Transactional scope: commits on success, rolls back on error."""
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()
