#!/usr/bin/env python3
"""
Create a standalone SQLite file with the CrowdMuse schema + sample rows.

Output: backend/data/sample_crowdmuse.sqlite3 (does not touch crowdmuse.sqlite3).

Before running, activate the project venv (from the directory that contains `.cmuse`):

  source .cmuse/bin/activate

Then, from the `backend/` directory:

  python scripts/seed_sample_db.py --force

Or from the repo root:

  python backend/scripts/seed_sample_db.py --force
"""
from __future__ import annotations

import argparse
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.models import Attendance, Base, ClassSchedule, Stream, Student  # noqa: E402

SAMPLE_DB_PATH = BACKEND_ROOT / "data" / "sample_crowdmuse.sqlite3"


def build_engine(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    url = f"sqlite:///{path}"
    return create_engine(url, connect_args={"check_same_thread": False})


def seed(session: Session) -> None:
    """Insert illustrative streams, students, weekly timetable, and a few attendance rows."""

    # --- Programs (streams) ---
    me = Stream(name="Mechanical Engineering")
    cs = Stream(name="Computer Science")
    session.add_all([me, cs])
    session.flush()  # assign ids

    # --- Students: cohort = stream_id + batch_year ---
    students_me_2025 = [
        Student(roll_number="98104ME001", name="Arjun Patel", stream_id=me.id, batch_year=2025),
        Student(roll_number="98104ME002", name="Sneha Rao", stream_id=me.id, batch_year=2025),
        Student(roll_number="98104ME003", name="Vikram Singh", stream_id=me.id, batch_year=2025),
    ]
    students_me_2026 = [
        Student(roll_number="98104ME101", name="New Admit One", stream_id=me.id, batch_year=2026),
    ]
    students_cs_2025 = [
        Student(roll_number="98204CS001", name="Priya Nair", stream_id=cs.id, batch_year=2025),
    ]
    session.add_all(students_me_2025 + students_me_2026 + students_cs_2025)
    session.flush()

    # --- Weekly timetable: Mechanical Engineering, batch 2025 (Mon–Fri) ---
    # day_of_week: 0=Monday .. 4=Friday
    me25_slots: list[tuple] = [
        # Mon
        (0, "09:00", "10:00", "321", "M3101", "Engineering Thermodynamics"),
        (0, "10:00", "11:00", "213", "S1234", "Applied Mathematics"),
        # Tue
        (1, "09:00", "10:00", "321", "M3102", "Fluid Mechanics"),
        (1, "10:00", "11:00", "501", "M3102L", "Fluid Mechanics Lab"),
        # Wed
        (2, "09:00", "10:00", "210", "HU201", "Technical Communication"),
        (2, "11:00", "12:00", "321", "M3103", "Machine Drawing"),
        # Thu
        (3, "09:00", "10:00", "213", "S1234", "Applied Mathematics"),
        (3, "10:00", "11:00", "321", "M3101", "Engineering Thermodynamics"),
        # Fri
        (4, "09:00", "11:00", "501", "M3102L", "Fluid Mechanics Lab (double)"),
    ]
    for dow, start, end, room, code, title in me25_slots:
        session.add(
            ClassSchedule(
                stream_id=me.id,
                batch_year=2025,
                room=room,
                course_code=code,
                class_name=title,
                day_of_week=dow,
                start_time=start,
                end_time=end,
                attendance_window=10,
                late_window=20,
            )
        )

    # One slot for ME 2026 same room Monday 9am — different cohort, same physical room possible in data model
    session.add(
        ClassSchedule(
            stream_id=me.id,
            batch_year=2026,
            room="321",
            course_code="M2101",
            class_name="Intro to Mechanical Design",
            day_of_week=0,
            start_time="09:00",
            end_time="10:00",
        )
    )

    # CS 2025 Tuesday slot (different stream)
    session.add(
        ClassSchedule(
            stream_id=cs.id,
            batch_year=2025,
            room="412",
            course_code="CS301",
            class_name="Data Structures",
            day_of_week=1,
            start_time="14:00",
            end_time="15:00",
        )
    )

    session.flush()

    # --- Sample attendance (same student, different classes same day) ---
    arjun = students_me_2025[0]
    today = datetime(2026, 4, 7, 9, 15, 0)  # fixed sample date (a Tuesday in 2026)
    date_key = today.date().isoformat()
    session.add_all(
        [
            Attendance(
                student_id=arjun.id,
                room="321",
                class_name="Fluid Mechanics",
                status="present",
                date_key=date_key,
                marked_at=today,
            ),
            Attendance(
                student_id=arjun.id,
                room="501",
                class_name="Fluid Mechanics Lab",
                status="late",
                date_key=date_key,
                marked_at=datetime(2026, 4, 7, 10, 12, 0),
            ),
        ]
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Create sample CrowdMuse SQLite DB with demo data.")
    parser.add_argument(
        "--output",
        type=Path,
        default=SAMPLE_DB_PATH,
        help=f"SQLite file path (default: {SAMPLE_DB_PATH})",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Remove existing DB file before creating.",
    )
    args = parser.parse_args()
    out: Path = args.output.resolve()

    if out.exists():
        if not args.force:
            print(f"File exists: {out}\nUse --force to overwrite.", file=sys.stderr)
            return 1
        out.unlink()

    engine = build_engine(out)
    Base.metadata.create_all(bind=engine)
    SessionLocal = sessionmaker(bind=engine)
    with SessionLocal() as session:
        seed(session)
        session.commit()

    print(f"Created {out}")
    print()
    print("Quick peek (sqlite3 CLI):")
    print(f"  sqlite3 {out} \".tables\"")
    print(f"  sqlite3 {out} \"SELECT * FROM streams;\"")
    print(f"  sqlite3 {out} \"SELECT roll_number, name, stream_id, batch_year FROM students;\"")
    print(f"  sqlite3 {out} \"SELECT id, stream_id, batch_year, day_of_week, start_time, room, course_code FROM class_schedule ORDER BY stream_id, batch_year, day_of_week, start_time;\"")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
