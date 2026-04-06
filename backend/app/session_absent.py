"""
End-of-session absent marking: once per schedule slot per day, mark unmarked students absent.
"""
from __future__ import annotations

import json
import logging
import threading
from datetime import date, datetime

from sqlalchemy.orm import Session

from .db import DATA_DIR
from .models import Attendance, ClassSchedule, Student

logger = logging.getLogger(__name__)

PROCESSED_FILE = DATA_DIR / "session_absent_processed.json"
_processed_lock = threading.Lock()


def _parse_hhmm_to_minutes(s: str) -> int:
    s = s.strip()
    parts = s.split(":")
    h = int(parts[0])
    m = int(parts[1]) if len(parts) > 1 else 0
    return h * 60 + m


def _session_has_ended(schedule: ClassSchedule) -> bool:
    """True if local time is at or past schedule end_time today."""
    now = datetime.now()
    now_m = now.hour * 60 + now.minute
    end_m = _parse_hhmm_to_minutes(schedule.end_time)
    return now_m >= end_m


def _load_processed() -> set[str]:
    if not PROCESSED_FILE.exists():
        return set()
    try:
        with open(PROCESSED_FILE, encoding="utf-8") as f:
            data = json.load(f)
        return set(data.get("keys", []))
    except (json.JSONDecodeError, OSError) as e:
        logger.warning("Could not read %s: %s", PROCESSED_FILE, e)
        return set()


def _prune_processed(keys: set[str]) -> set[str]:
    """Drop keys older than ~14 days to keep file small."""
    today = date.today()
    out: set[str] = set()
    for k in keys:
        if ":" not in k:
            continue
        try:
            _, dstr = k.split(":", 1)
            kd = date.fromisoformat(dstr)
            if (today - kd).days <= 14:
                out.add(k)
        except ValueError:
            continue
    return out


def _save_processed(keys: set[str]) -> None:
    keys = _prune_processed(keys)
    try:
        with open(PROCESSED_FILE, "w", encoding="utf-8") as f:
            json.dump({"keys": list(keys)}, f)
    except OSError as e:
        logger.error("Could not write %s: %s", PROCESSED_FILE, e)


def apply_absent_processed_keys(keys_completed: list[str]) -> None:
    """Persist session keys after a successful DB commit."""
    if not keys_completed:
        return
    with _processed_lock:
        processed = _load_processed()
        for k in keys_completed:
            processed.add(k)
        _save_processed(processed)


def run_absent_sweeps(db: Session) -> tuple[int, list[str]]:
    """
    Stage absent rows for ended sessions today. Caller must commit the session.
    Returns (inserted_count, keys_to_mark_processed).
    """
    today_key = date.today().isoformat()

    with _processed_lock:
        processed = _load_processed()

    schedules = db.query(ClassSchedule).all()
    all_students = db.query(Student).all()
    inserted = 0
    keys_completed: list[str] = []

    for schedule in schedules:
        if not _session_has_ended(schedule):
            continue

        key = f"{schedule.id}:{today_key}"
        if key in processed:
            continue

        for student in all_students:
            existing = (
                db.query(Attendance)
                .filter_by(
                    student_id=student.id,
                    date_key=today_key,
                    room=schedule.room,
                    class_name=schedule.class_name,
                )
                .first()
            )
            if existing:
                if existing.status in ("present", "late"):
                    continue
                continue

            db.add(
                Attendance(
                    student_id=student.id,
                    room=schedule.room,
                    class_name=schedule.class_name,
                    status="absent",
                    date_key=today_key,
                )
            )
            inserted += 1

        keys_completed.append(key)

    return inserted, keys_completed
