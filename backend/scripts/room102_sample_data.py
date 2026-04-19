"""
Room **102** sample timetable + one **Mechanical Engineering 2025** student eligible for every slot.

Cohort rule: all `class_schedule` rows use the same `stream_id` + `batch_year` as the student, so
that user can be marked present in **any** class held in room 102 (no per-class enrollment table).

Use **`seed_sample_db.py`** for a full fresh **`sample_crowdmuse.sqlite3`**, or run this script to
**merge** into an existing DB (default **`data/crowdmuse.sqlite3`**):

  cd backend
  python scripts/room102_sample_data.py

  python scripts/room102_sample_data.py --db data/sample_crowdmuse.sqlite3
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import create_engine  # noqa: E402
from sqlalchemy.orm import sessionmaker  # noqa: E402

from app.db import DATA_DIR, migrate_sqlite_schema  # noqa: E402
from app.models import Base, ClassSchedule, Stream, Student  # noqa: E402

STREAM_NAME = "Mechanical Engineering"
BATCH_YEAR = 2025
SAMPLE_ROLL = "98104ME102"
SAMPLE_NAME = "Asha Menon (Room 102 demo)"

# All classes in room 102 — same cohort; one slot per weekday (non-overlapping).
ROOM_102_SLOTS: list[tuple[int, str, str, str, str]] = [
    (0, "09:00", "10:00", "PHY102A", "Physics — Mechanics"),
    (1, "09:00", "10:00", "PHY102B", "Physics — Waves"),
    (2, "09:00", "10:00", "LAB102", "Measurements Lab"),
    (3, "09:00", "10:00", "TUT102", "Problem Solving Tutorial"),
    (4, "09:00", "10:00", "REV102", "Weekly Review"),
]
ROOM = "102"


def _ensure_stream(session) -> Stream:
    s = session.query(Stream).filter_by(name=STREAM_NAME).first()
    if s:
        return s
    s = Stream(name=STREAM_NAME)
    session.add(s)
    session.flush()
    return s


def _ensure_student(session, stream_id: int) -> Student:
    st = session.query(Student).filter_by(roll_number=SAMPLE_ROLL).first()
    if st:
        st.stream_id = stream_id
        st.batch_year = BATCH_YEAR
        st.name = SAMPLE_NAME
        return st
    st = Student(
        roll_number=SAMPLE_ROLL,
        name=SAMPLE_NAME,
        stream_id=stream_id,
        batch_year=BATCH_YEAR,
        photo_path=None,
    )
    session.add(st)
    session.flush()
    return st


def _slot_exists(session, stream_id: int, dow: int, start: str, room: str) -> bool:
    return (
        session.query(ClassSchedule)
        .filter_by(
            stream_id=stream_id,
            batch_year=BATCH_YEAR,
            room=room,
            day_of_week=dow,
            start_time=start,
        )
        .first()
        is not None
    )


def seed_room102(session) -> tuple[int, int]:
    """Returns (stream_id, count of new schedule rows inserted)."""
    me = _ensure_stream(session)
    _ensure_student(session, me.id)
    added = 0
    for dow, start, end, code, title in ROOM_102_SLOTS:
        if _slot_exists(session, me.id, dow, start, ROOM):
            continue
        session.add(
            ClassSchedule(
                stream_id=me.id,
                batch_year=BATCH_YEAR,
                room=ROOM,
                course_code=code,
                class_name=title,
                day_of_week=dow,
                start_time=start,
                end_time=end,
                attendance_window=10,
                late_window=20,
            )
        )
        added += 1
    session.flush()
    return me.id, added


def main() -> int:
    p = argparse.ArgumentParser(description="Add room 102 sample timetable + ME2025 demo student to SQLite.")
    p.add_argument("--db", type=Path, default=DATA_DIR / "crowdmuse.sqlite3", help="SQLite file to update")
    args = p.parse_args()
    path = args.db.resolve()
    path.parent.mkdir(parents=True, exist_ok=True)

    engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    migrate_sqlite_schema(engine)

    Session = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)
    db = Session()
    try:
        _, n = seed_room102(db)
        db.commit()
        print(f"Updated {path}")
        print(f"  Student: {SAMPLE_ROLL} / {SAMPLE_NAME} — {STREAM_NAME}, batch {BATCH_YEAR}")
        print(f"  New class_schedule rows inserted: {n} (room {ROOM!r}, Mon–Fri 09:00–10:00)")
        print("  sqlite3 peek:")
        print(
            f'    sqlite3 "{path}" '
            f'"SELECT day_of_week, start_time, end_time, course_code, class_name FROM class_schedule WHERE room=\'{ROOM}\' ORDER BY day_of_week;"'
        )
        return 0
    except Exception as e:
        db.rollback()
        print(e, file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
