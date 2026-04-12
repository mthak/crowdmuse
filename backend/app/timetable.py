"""
Resolve which class is in session for a room at a given local time,
and whether a student belongs to that slot's cohort (stream + batch year).
"""
from __future__ import annotations

from datetime import datetime, time

from sqlalchemy.orm import Session

from .models import ClassSchedule, Student


def _parse_hhmm(s: str) -> time:
    parts = s.strip().split(":")
    h = int(parts[0])
    m = int(parts[1]) if len(parts) > 1 else 0
    return time(hour=h, minute=m)


def get_active_schedule_for_room(
    db: Session,
    room: str,
    when: datetime | None = None,
) -> ClassSchedule | None:
    """
    Find the timetable row for `room` whose day_of_week and time range
    match `when` (default: server's local now).

    day_of_week: 0=Monday ... 6=Sunday (same as datetime.weekday()).
    Times are compared in local wall-clock (set server TZ to campus).
    """
    if when is None:
        when = datetime.now()
    dow = when.weekday()
    now_t = when.time()

    # Normalize room for match (strip)
    room_norm = room.strip()

    slots = (
        db.query(ClassSchedule)
        .filter(
            ClassSchedule.room == room_norm,
            ClassSchedule.day_of_week == dow,
        )
        .all()
    )

    for slot in slots:
        start = _parse_hhmm(slot.start_time)
        end = _parse_hhmm(slot.end_time)
        if start <= now_t < end:
            return slot
    return None


def is_student_eligible_for_slot(student: Student, slot: ClassSchedule) -> bool:
    """True if the student's program and batch match this weekly slot's cohort."""
    return student.stream_id == slot.stream_id and student.batch_year == slot.batch_year


def resolve_student_scheduled_attendance(
    db: Session,
    student: Student,
    room: str,
    when: datetime | None = None,
) -> tuple[ClassSchedule, str] | tuple[None, str]:
    """
    Returns (slot, "") if student may be marked, or (None, error_message).
    """
    slot = get_active_schedule_for_room(db, room, when)
    if slot is None:
        return None, "No class scheduled in this room at the current time"

    if not is_student_eligible_for_slot(student, slot):
        return None, (
            "Student's stream/batch does not match this class "
            f"({slot.class_name} / {slot.course_code or 'no code'})"
        )

    return slot, ""
