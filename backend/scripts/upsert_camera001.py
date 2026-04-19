#!/usr/bin/env python3
"""
Insert or update **camera001** in the default app SQLite DB (`backend/data/crowdmuse.sqlite3`).

Ensures schema (including `cameras` + encrypted `password`) then upserts the row.

Environment overrides (optional): `CAMERA_IP`, `CAMERA_ROOM`, `CAMERA_USERNAME`, `CAMERA_PASSWORD`.

Run from `backend/`:

  python scripts/upsert_camera001.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db import SessionLocal, engine, migrate_sqlite_schema  # noqa: E402
from app.models import Base, Camera  # noqa: E402


CAMERA_NAME = "camera001"


def _env(key: str, default: str) -> str:
    return os.environ.get(key, default).strip()


def main() -> int:
    ip = _env("CAMERA_IP", "192.168.4.28")
    room = _env("CAMERA_ROOM", "102")
    user = _env("CAMERA_USERNAME", "Coolmanu")
    password = _env("CAMERA_PASSWORD", "Smart5253")
    rtsp = f"rtsp://{ip}/stream1"

    Base.metadata.create_all(bind=engine)
    migrate_sqlite_schema(engine)

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
                notes="Seeded via scripts/upsert_camera001.py",
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
        print(f"{action} camera id={row.id}")
        print(f"  name={row.name!r} room={row.room!r} ip={row.ip_address!r}")
        print(f"  username={row.username!r}  password stored encrypted  has_password={bool(row.password)}")
        print(f"  rtsp_url (no creds in DB)={row.rtsp_url!r}")
        eff = row.effective_rtsp_url()
        if eff:
            print(f"  effective_rtsp (server-side only): {eff!r}")
        print(f"DB file: {BACKEND_ROOT / 'data' / 'crowdmuse.sqlite3'}")
        print("API: GET http://127.0.0.1:8000/cameras")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
