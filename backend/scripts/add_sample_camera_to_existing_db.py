#!/usr/bin/env python3
"""
Add the **`cameras`** table (if missing), apply SQLite column migrations, and upsert one sample row
**without** wiping an existing database.

Defaults target **`backend/data/crowdmuse.sqlite3`** (same file the API uses — `app.db`). Use **`--db`**
to point at another file (e.g. `data/sample_crowdmuse.sqlite3`).

Sample row (same as discussed for your network camera):

- **name:** camera001  
- **ip:** 192.168.4.28  
- **room:** 102  
- **username / password:** stored; password is encrypted at rest (`app/camera_crypto.py`).  
- **rtsp_url:** `rtsp://192.168.4.28/stream1` (path only; full URL with creds via `Camera.effective_rtsp_url()` in code).

From `backend/`:

  python scripts/add_sample_camera_to_existing_db.py

  python scripts/add_sample_camera_to_existing_db.py --db data/sample_crowdmuse.sqlite3

Requires: SQLAlchemy, cryptography (see `requirements.txt`).
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.db import DATA_DIR, migrate_sqlite_schema  # noqa: E402
from app.models import Base, Camera  # noqa: E402

# Same path as `app.db.DB_PATH` — the running FastAPI app reads this file by default.
DEFAULT_SQLITE = DATA_DIR / "crowdmuse.sqlite3"

CAMERA_NAME = "camera001"
DEFAULT_IP = "192.168.4.28"
DEFAULT_ROOM = 
DEFAULT_USER = os.getenv("CAMERA_USERNAME")
DEFAULT_PASSWORD = os.getenv("CAMERA_PASSWORD")


def _env(name: str, default: str) -> str:
    return os.environ.get(name, default).strip()


def main() -> int:
    p = argparse.ArgumentParser(description="Add cameras schema + sample camera row to an existing SQLite file.")
    p.add_argument(
        "--db",
        type=Path,
        default=DEFAULT_SQLITE,
        help=f"SQLite file (default: {DEFAULT_SQLITE})",
    )
    args = p.parse_args()
    db_path: Path = args.db.resolve()
    if not db_path.parent.is_dir():
        db_path.parent.mkdir(parents=True, exist_ok=True)

    url = f"sqlite:///{db_path}"
    engine = create_engine(url, connect_args={"check_same_thread": False})

    # Creates only missing tables (e.g. `cameras`) — does not drop existing data.
    Base.metadata.create_all(bind=engine)
    migrate_sqlite_schema(engine)

    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    ip = _env("CAMERA_IP", DEFAULT_IP)
    room = _env("CAMERA_ROOM", DEFAULT_ROOM)
    user = _env("CAMERA_USERNAME", DEFAULT_USER)
    password = _env("CAMERA_PASSWORD", DEFAULT_PASSWORD)
    rtsp = f"rtsp://{ip}/stream1"

    db = SessionLocal()
    try:
        row = db.query(Camera).filter(Camera.name == CAMERA_NAME).first()
        if row is None:
            row = Camera(
                name=CAMERA_NAME,
                ip_address=ip,
                room=room,
                username=user,
                password=password,
                rtsp_url=rtsp,
                is_active=True,
                notes="Added by scripts/add_sample_camera_to_existing_db.py",
            )
            db.add(row)
            action = "Inserted"
        else:
            row.ip_address = ip
            row.room = room
            row.username = user
            row.password = password
            row.rtsp_url = rtsp
            row.is_active = True
            action = "Updated"
        db.commit()
        db.refresh(row)
        print(f"{action} camera id={row.id} in {db_path}")
        print(f"  name={row.name!r} room={row.room!r} ip={row.ip_address!r} username={row.username!r}")
        print(f"  password: encrypted in DB  has_password={bool(row.password)}")
        print(f"  rtsp_url={row.rtsp_url!r}")
        eff = row.effective_rtsp_url()
        if eff:
            print(f"  effective_rtsp (server-side only): {eff!r}")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
