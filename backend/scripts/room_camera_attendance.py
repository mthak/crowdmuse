#!/usr/bin/env python3
"""
Face-based attendance for one **room** using the **camera row** stored in SQLite (`cameras` table).

Flow (same as **`mark_attendance.py`** live/hybrid mode):

1. Load the first **active** `Camera` for `--room` (e.g. **102**) and build the RTSP URL with
   **`Camera.effective_rtsp_url()`** (password decrypted only in this process).
2. Open that stream (or USB with **`--no-db-camera`**), run face recognition against
   **`data/face_encodings/*.json`**.
3. Poll **`GET /timetable/active?room=...`** — when a class is in session for that room, POST
   **`/attendance/mark-by-face-scheduled`** with a face crop (server checks timetable + cohort).

Prerequisites: API running, **`class_schedule`** rows for the room/time, students enrolled with
face encodings, and a **`cameras`** row for the room (see **`add_sample_camera_to_existing_db.py`**).

From **`backend/`**:

  python scripts/room_camera_attendance.py
  python scripts/room_camera_attendance.py --room 102 --api-url http://127.0.0.1:8000

Override RTSP or skip DB:

  python scripts/room_camera_attendance.py --rtsp 'rtsp://...' --no-db-camera
  python scripts/room_camera_attendance.py --no-db-camera --camera 0
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND))


def _get_camera_for_room(room: str):
    """First active camera for this room, or None."""
    from app.db import SessionLocal
    from app.models import Camera

    db = SessionLocal()
    try:
        return (
            db.query(Camera)
            .filter(Camera.room == room.strip(), Camera.is_active.is_(True))
            .order_by(Camera.id)
            .first()
        )
    finally:
        db.close()


def main() -> int:
    import argparse

    p = argparse.ArgumentParser(
        description="Room face attendance: RTSP from DB cameras table + mark-by-face-scheduled when class is active.",
    )
    p.add_argument("--room", default="102", help="Must match cameras.room and class_schedule.room")
    p.add_argument("--api-url", default="http://localhost:8000")
    p.add_argument("--rtsp", default=None, help="Override RTSP URL (skip DB URL if set)")
    p.add_argument(
        "--no-db-camera",
        action="store_true",
        help="Do not load cameras from SQLite; use --rtsp and/or USB --camera instead",
    )
    p.add_argument("--camera", type=int, default=0, help="USB camera index when not using RTSP")
    p.add_argument("--camera-id", type=int, default=None, dest="camera_id", help="Override cameras.id for API audit")
    p.add_argument("--tolerance", type=float, default=0.6)
    p.add_argument("--schedule-poll-sec", type=float, default=3.0)
    p.add_argument("--no-display", action="store_true")
    p.add_argument("--lat", default=None)
    p.add_argument("--lng", default=None)
    p.add_argument(
        "--rtsp-live",
        action="store_true",
        help="Single-thread RTSP (like a webcam). Default without this flag uses hybrid grabber for RTSP.",
    )
    args = p.parse_args()

    cam_row = None
    if not args.no_db_camera:
        cam_row = _get_camera_for_room(args.room)

    rtsp = args.rtsp
    if rtsp is None and cam_row is not None:
        rtsp = cam_row.effective_rtsp_url()
        if not rtsp:
            print("❌ Camera row has no usable rtsp_url / credentials. Fix the `cameras` row.")
            return 1

    camera_id = args.camera_id
    if camera_id is None and cam_row is not None:
        camera_id = cam_row.id

    # Video source: RTSP string or local USB index (no RTSP).
    if rtsp is None:
        if args.no_db_camera:
            pass
        else:
            print(f"❌ No active camera in DB for room {args.room!r} and no --rtsp override.")
            print("   Run: python scripts/add_sample_camera_to_existing_db.py")
            print("   Or: --rtsp 'rtsp://...'  |  --no-db-camera --camera 0")
            return 1

    ma_args = [
        "mark_attendance",
        "--room",
        args.room,
        "--api-url",
        args.api_url,
        "--tolerance",
        str(args.tolerance),
        "--schedule-poll-sec",
        str(args.schedule_poll_sec),
    ]
    if args.no_display:
        ma_args.append("--no-display")
    if args.lat:
        ma_args.extend(["--lat", args.lat])
    if args.lng:
        ma_args.extend(["--lng", args.lng])
    if rtsp:
        ma_args.extend(["--rtsp", rtsp])
        if args.rtsp_live:
            ma_args.append("--rtsp-live")
    else:
        ma_args.extend(["--camera", str(args.camera)])
    if camera_id is not None:
        ma_args.extend(["--camera-id", str(camera_id)])

    os.chdir(BACKEND)
    sys.argv = ma_args
    import mark_attendance

    return mark_attendance.main()


if __name__ == "__main__":
    raise SystemExit(main())
