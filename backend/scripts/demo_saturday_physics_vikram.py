#!/usr/bin/env python3
"""
End-to-end demo: Vikram Singh (ME 2025) has **Physics** Saturday **19:00–20:00** in **PhysicsLab**.

**Attendance date/time on the server**
-------------------------------
All marks go through the API, which stores:
- **`date_key`**: `date.today()` on the **server** (local calendar day of the API process).
- **`marked_at`**: `datetime.now()` on the **server** (local wall time when the row is inserted).

So the DB row reflects **the machine running uvicorn**, not your laptop clock, unless they are the same host (or same `TZ`).

**Which endpoint**
------------------
- Slot **active** (server says class is on now) **and no `--image`**: **`POST /attendance/mark-scheduled`** (roll + room only — class from timetable, cohort checked).
- Slot **active** **and `--image`**: **`POST /attendance/mark-by-face-scheduled`** (face + room).
- **`--force-mark`** when slot is **inactive**: **`POST /attendance/mark`** with fixed class name (dev only; bypasses timetable).

**Client banner**
-----------------
Prints **this script’s** `datetime.now()` so you can compare to the server if both run on the same Mac.

Usage (from `backend/`, venv active, API on 8000):

  python scripts/demo_saturday_physics_vikram.py
  python scripts/demo_saturday_physics_vikram.py --api-url http://127.0.0.1:8000
  python scripts/demo_saturday_physics_vikram.py --force-mark   # dev: mark even off-schedule
  python scripts/demo_saturday_physics_vikram.py --image ~/face.jpg   # needs active slot + encoding
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

import requests

# Aligned with sample DB / tests
STREAM_NAME = "Mechanical Engineering"
BATCH_YEAR = 2025
ROLL = "98104ME003"
STUDENT_NAME = "Vikram Singh"
ROOM = "PhysicsLab"
CLASS_NAME = "Physics"
COURSE_CODE = "PHY101"
# Python datetime.weekday(): Monday=0 .. Sunday=6 → Saturday=5
SATURDAY = 5
START = "19:00"
END = "20:00"


def _weekday_name(dow: int) -> str:
    return ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"][dow]


def print_local_clock_banner() -> datetime:
    """Wall clock on **this** OS (the machine running this script)."""
    now_naive = datetime.now()
    now_local = datetime.now().astimezone()
    tz_name = str(now_local.tzinfo) if now_local.tzinfo else "local (naive)"
    print("--- Clock on this machine (client running this script) ---")
    print(f"  Local (naive) datetime.now():  {now_naive.isoformat(sep=' ', timespec='seconds')}")
    print(f"  Local with offset:             {now_local.isoformat(timespec='seconds')}")
    print(f"  Weekday:                       {_weekday_name(now_naive.weekday())} (weekday()={now_naive.weekday()}, 0=Mon .. 6=Sun)")
    print(f"  Timezone info:                 {tz_name}")
    print()
    return now_naive


def _print_recorded_times(out: dict) -> None:
    """Echo API response fields (server-local semantics)."""
    dk = out.get("date_key")
    ma = out.get("marked_at")
    print()
    print("--- Stored on server (from API response) ---")
    print(f"  date_key:   {dk!r}  ← server local calendar day for this attendance session")
    print(f"  marked_at:  {ma!r}  ← server local time when the row was written")
    print("  (If client and server are the same machine, these should match ‘today’ on the banner above.)")
    print()


def ensure_stream(base: str) -> int:
    r = requests.get(f"{base}/streams", timeout=30)
    r.raise_for_status()
    for row in r.json():
        if row["name"] == STREAM_NAME:
            return int(row["id"])
    c = requests.post(f"{base}/streams", json={"name": STREAM_NAME}, timeout=30)
    c.raise_for_status()
    return int(c.json()["id"])


def ensure_student(base: str, stream_id: int) -> None:
    payload = {
        "roll_number": ROLL,
        "name": STUDENT_NAME,
        "stream_id": stream_id,
        "batch_year": BATCH_YEAR,
    }
    r = requests.post(f"{base}/students", json=payload, timeout=30)
    if r.status_code == 409:
        return
    r.raise_for_status()


def ensure_saturday_physics_slot(base: str, stream_id: int) -> None:
    r = requests.get(f"{base}/timetable/slots", params={"room": ROOM}, timeout=30)
    r.raise_for_status()
    for slot in r.json():
        if (
            slot.get("stream_id") == stream_id
            and slot.get("batch_year") == BATCH_YEAR
            and slot.get("day_of_week") == SATURDAY
            and slot.get("start_time") == START
            and slot.get("class_name") == CLASS_NAME
        ):
            return
    body = {
        "stream_id": stream_id,
        "batch_year": BATCH_YEAR,
        "room": ROOM,
        "course_code": COURSE_CODE,
        "class_name": CLASS_NAME,
        "day_of_week": SATURDAY,
        "start_time": START,
        "end_time": END,
    }
    c = requests.post(f"{base}/timetable/slots", json=body, timeout=30)
    c.raise_for_status()


def main() -> int:
    parser = argparse.ArgumentParser(description="Demo Saturday Physics attendance for Vikram Singh")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000", help="FastAPI base URL")
    parser.add_argument(
        "--force-mark",
        action="store_true",
        help="If no active slot: still mark via POST /attendance/mark (dev; client supplies class name)",
    )
    parser.add_argument(
        "--image",
        type=Path,
        default=None,
        help="If set: POST /attendance/mark-by-face-scheduled (needs active slot + face encoding)",
    )
    args = parser.parse_args()
    base = args.api_url.rstrip("/")

    print_local_clock_banner()

    try:
        requests.get(f"{base}/health", timeout=5).raise_for_status()
    except requests.RequestException as e:
        print(f"API not reachable at {base}: {e}", file=sys.stderr)
        return 1

    stream_id = ensure_stream(base)
    ensure_student(base, stream_id)
    ensure_saturday_physics_slot(base, stream_id)
    print(f"Ensured stream={STREAM_NAME!r} (id={stream_id}), student {ROLL} / {STUDENT_NAME}, slot Sat {START}-{END} {CLASS_NAME!r} in {ROOM!r}.")
    print()

    active = requests.get(f"{base}/timetable/active", params={"room": ROOM}, timeout=30)
    active.raise_for_status()
    body = active.json()
    print("--- Server: GET /timetable/active (uses server process local datetime.now()) ---")
    print(body)
    print()

    slot_active = body.get("active") is True
    server_class = body.get("class_name")

    if not slot_active and not args.force_mark:
        print(
            "No active class in this room **right now** on the server clock.\n"
            f"Expected: Saturday between {START} and {END} local server time, room {ROOM!r}.\n"
            "Run this script during that window, use `demo_face_scheduled_e2e.py --setup` for a “now” slot,\n"
            "or pass --force-mark to test POST /attendance/mark (manual class name; still uses server local date_key/marked_at)."
        )
        return 0

    if args.force_mark and not slot_active:
        print("** --force-mark: no active slot; using POST /attendance/mark (manual class name). **\n")

    if slot_active and server_class and server_class != CLASS_NAME:
        print(f"Warning: active class is {server_class!r}, expected {CLASS_NAME!r}.", file=sys.stderr)

    class_for_mark = (body.get("class_name") or CLASS_NAME) if slot_active else CLASS_NAME

    if args.image:
        if not slot_active:
            print(
                "mark-by-face-scheduled needs an **active** timetable slot for this room.\n"
                "Run on Saturday 19:00–20:00 server time, or use demo_face_scheduled_e2e.py --setup, or omit --image and use --force-mark.",
                file=sys.stderr,
            )
            return 1
        if not args.image.is_file():
            print(f"Image not found: {args.image}", file=sys.stderr)
            return 1
        with open(args.image, "rb") as f:
            files = {"image": (args.image.name, f, "image/jpeg")}
            data = {"room": ROOM}
            mr = requests.post(f"{base}/attendance/mark-by-face-scheduled", files=files, data=data, timeout=60)
        if mr.status_code != 200:
            print(mr.text, file=sys.stderr)
            mr.raise_for_status()
        out = mr.json()
        print("Marked via POST /attendance/mark-by-face-scheduled:", out)
        _print_recorded_times(out)
        return 0

    if slot_active:
        mr = requests.post(
            f"{base}/attendance/mark-scheduled",
            json={"roll_number": ROLL, "room": ROOM, "status": "present"},
            timeout=30,
        )
        used_fallback = False
        if mr.status_code == 404:
            # Old API process (before this route existed). Same server local date_key/marked_at via /attendance/mark.
            print(
                "Note: POST /attendance/mark-scheduled not found (404). "
                "Restart uvicorn with the latest code (or use --reload). "
                "Falling back to POST /attendance/mark with class from /timetable/active.\n",
                file=sys.stderr,
            )
            used_fallback = True
            mr = requests.post(
                f"{base}/attendance/mark",
                json={
                    "roll_number": ROLL,
                    "room": ROOM,
                    "class_name": class_for_mark,
                    "status": "present",
                },
                timeout=30,
            )
        if mr.status_code != 200:
            print(mr.text, file=sys.stderr)
            mr.raise_for_status()
        out = mr.json()
        label = (
            "POST /attendance/mark (fallback; restart API for mark-scheduled)"
            if used_fallback
            else "POST /attendance/mark-scheduled"
        )
        print(f"Marked via {label}:", out)
        _print_recorded_times(out)
        return 0

    # force-mark, no image, no active slot
    mark_payload = {
        "roll_number": ROLL,
        "room": ROOM,
        "class_name": class_for_mark,
        "status": "present",
    }
    mr = requests.post(f"{base}/attendance/mark", json=mark_payload, timeout=30)
    if mr.status_code != 200:
        print(mr.text, file=sys.stderr)
        mr.raise_for_status()
    out = mr.json()
    print("Marked via POST /attendance/mark:", out)
    _print_recorded_times(out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
