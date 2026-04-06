"""
Rolling 3-day attendance export to Excel (overwrite on each run).
"""
from __future__ import annotations

import logging
import threading
from datetime import date, timedelta
from pathlib import Path

from openpyxl import Workbook
from sqlalchemy.orm import Session

from .db import session_scope
from .models import Attendance, Student

logger = logging.getLogger(__name__)


def write_attendance_excel(db: Session, output_path: Path | None = None) -> Path:
    """
    Query attendance for today and the previous 2 calendar days; write one sheet,
    overwriting the file. Columns: Name, Roll Number, Class, Room, Status, Date, Time.
    """
    cutoff = date.today() - timedelta(days=2)
    cutoff_str = cutoff.isoformat()

    rows = (
        db.query(Attendance, Student)
        .join(Student, Attendance.student_id == Student.id)
        .filter(Attendance.date_key >= cutoff_str)
        .order_by(Attendance.date_key.desc(), Attendance.marked_at.desc())
        .all()
    )

    wb = Workbook()
    ws = wb.active
    ws.title = "Attendance"
    ws.append(["Name", "Roll Number", "Class", "Room", "Status", "Date", "Time"])
    for att, stu in rows:
        t = att.marked_at
        time_str = t.strftime("%H:%M:%S") if t else ""
        ws.append(
            [
                stu.name,
                stu.roll_number,
                att.class_name,
                att.room,
                att.status,
                att.date_key,
                time_str,
            ]
        )

    if output_path is None:
        from .db import DATA_DIR

        output_path = DATA_DIR / "attendance_last_3_days.xlsx"
    wb.save(output_path)
    logger.debug("Wrote attendance Excel: %s (%s rows)", output_path, len(rows))
    return output_path


def schedule_attendance_excel_export() -> None:
    """Regenerate the Excel file in a daemon thread (does not block requests)."""

    def _run() -> None:
        try:
            with session_scope() as db:
                write_attendance_excel(db)
        except Exception:
            logger.exception("Attendance Excel export failed")

    threading.Thread(target=_run, daemon=True).start()
