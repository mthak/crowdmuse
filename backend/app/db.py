from __future__ import annotations

from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import Session, sessionmaker


DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "crowdmuse.sqlite3"
DATABASE_URL = f"sqlite:///{DB_PATH}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
)

SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


@contextmanager
def session_scope() -> Session:
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def migrate_sqlite_schema(engine) -> None:
    """
    Lightweight migrations for existing SQLite files (no Alembic).
    """
    insp = inspect(engine)
    tables = set(insp.get_table_names())

    with engine.connect() as conn:
        if "attendance" in tables:
            cols = {c["name"] for c in insp.get_columns("attendance")}
            if "camera_id" not in cols:
                conn.execute(text("ALTER TABLE attendance ADD COLUMN camera_id INTEGER"))
                conn.execute(text("CREATE INDEX IF NOT EXISTS ix_attendance_camera_id ON attendance (camera_id)"))
                conn.commit()

        if "cameras" in tables:
            cols = {c["name"] for c in insp.get_columns("cameras")}
            if "username" not in cols:
                conn.execute(text("ALTER TABLE cameras ADD COLUMN username VARCHAR(128)"))
            if "password" not in cols:
                conn.execute(text("ALTER TABLE cameras ADD COLUMN password TEXT"))
            conn.commit()

