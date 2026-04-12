#!/usr/bin/env python3
"""
End-to-end demo: **POST /attendance/mark-by-face-scheduled** (face + room → server picks class from timetable).

Prerequisites
-------------
- API running, e.g. `python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000`
- A **face encoding** on the server for the roll you use (`data/face_encodings/<roll>.json`).
  Enroll first, e.g. `python enroll_student.py --roll-number 98104ME003 --name "Vikram Singh" --batch-year 2025 --stream "Mechanical Engineering" --photo path/to.jpg`

Quick run (creates a 2h slot **starting a few minutes ago** so “now” is inside the window, then marks):
-------------
  cd backend && source ../.cmuse/bin/activate   # your venv

  python scripts/demo_face_scheduled_e2e.py --setup --image ~/Pictures/you.jpg --room DemoRoom

Without `--setup`, you must already have a `class_schedule` row for **this room**, **today’s weekday**,
**server local time** inside [start_time, end_time), and matching the student’s **stream + batch_year**.

Check active slot:
  curl -s "http://127.0.0.1:8000/timetable/active?room=DemoRoom"
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests


def _ensure_stream(base: str, name: str) -> int:
    r = requests.get(f"{base}/streams", timeout=30)
    r.raise_for_status()
    for row in r.json():
        if row["name"] == name:
            return int(row["id"])
    c = requests.post(f"{base}/streams", json={"name": name}, timeout=30)
    c.raise_for_status()
    return int(c.json()["id"])


def _ensure_student(base: str, stream_id: int, roll: str, name: str, batch_year: int) -> None:
    payload = {
        "roll_number": roll,
        "name": name,
        "stream_id": stream_id,
        "batch_year": batch_year,
    }
    r = requests.post(f"{base}/students", json=payload, timeout=30)
    if r.status_code == 409:
        return
    r.raise_for_status()


def _create_slot_now(
    base: str,
    stream_id: int,
    batch_year: int,
    room: str,
    class_name: str,
    course_code: str,
    minutes_back: int,
    minutes_forward: int,
) -> None:
    now = datetime.now()
    dow = now.weekday()
    start_dt = now - timedelta(minutes=minutes_back)
    end_dt = now + timedelta(minutes=minutes_forward)
    start_time = start_dt.strftime("%H:%M")
    end_time = end_dt.strftime("%H:%M")
    body = {
        "stream_id": stream_id,
        "batch_year": batch_year,
        "room": room.strip(),
        "course_code": course_code,
        "class_name": class_name,
        "day_of_week": dow,
        "start_time": start_time,
        "end_time": end_time,
    }
    r = requests.post(f"{base}/timetable/slots", json=body, timeout=30)
    r.raise_for_status()
    print(
        f"Created slot: weekday={dow} (0=Mon..6=Sun) {start_time}-{end_time} "
        f"room={room!r} class={class_name!r} cohort stream_id={stream_id} batch={batch_year}"
    )


def main() -> int:
    p = argparse.ArgumentParser(description="Demo mark-by-face-scheduled")
    p.add_argument("--api-url", default="http://127.0.0.1:8000")
    p.add_argument("--image", type=Path, required=True, help="JPEG/PNG face image (same person as encoding)")
    p.add_argument("--room", default="DemoRoom", help="Room passed to API (must match timetable row)")
    p.add_argument(
        "--setup",
        action="store_true",
        help="Create ME stream, student, and a timetable row that includes server local NOW",
    )
    p.add_argument("--roll", default="98104ME003", help="Roll number (must match face encoding file)")
    p.add_argument("--student-name", default="Vikram Singh")
    p.add_argument("--stream-name", default="Mechanical Engineering")
    p.add_argument("--batch-year", type=int, default=2025)
    p.add_argument("--class-name", default="Demo scheduled class")
    p.add_argument("--course-code", default="DEMO101")
    p.add_argument("--minutes-back", type=int, default=10, help="Slot starts this many minutes ago")
    p.add_argument("--minutes-forward", type=int, default=120, help="Slot ends this many minutes from now")
    args = p.parse_args()
    base = args.api_url.rstrip("/")

    if not args.image.is_file():
        print(f"Image not found: {args.image}", file=sys.stderr)
        return 1

    try:
        requests.get(f"{base}/health", timeout=5).raise_for_status()
    except requests.RequestException as e:
        print(f"API not up at {base}: {e}", file=sys.stderr)
        return 1

    if args.setup:
        sid = _ensure_stream(base, args.stream_name)
        _ensure_student(base, sid, args.roll, args.student_name, args.batch_year)
        _create_slot_now(
            base,
            sid,
            args.batch_year,
            args.room,
            args.class_name,
            args.course_code,
            args.minutes_back,
            args.minutes_forward,
        )
        print("(If you already had another slot overlapping this room/time, /timetable/active may pick the first match.)\n")

    active = requests.get(f"{base}/timetable/active", params={"room": args.room}, timeout=30)
    active.raise_for_status()
    print("GET /timetable/active:", active.json())

    with open(args.image, "rb") as f:
        files = {"image": (args.image.name, f, "image/jpeg")}
        data = {"room": args.room.strip()}
        mr = requests.post(f"{base}/attendance/mark-by-face-scheduled", files=files, data=data, timeout=60)

    if mr.status_code != 200:
        print(mr.status_code, mr.text, file=sys.stderr)
        return 1
    print("POST /attendance/mark-by-face-scheduled OK:", mr.json())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
