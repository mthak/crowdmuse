from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Stream(Base):
    """Academic program / branch, e.g. Mechanical Engineering."""

    __tablename__ = "streams"
    __table_args__ = (UniqueConstraint("name", name="uq_streams_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(128), index=True)

    students: Mapped[list["Student"]] = relationship(back_populates="stream")
    class_schedules: Mapped[list["ClassSchedule"]] = relationship(back_populates="stream")


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    roll_number: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    # Cohort: which program and intake/graduation batch (e.g. Mechanical Engineering, 2025)
    stream_id: Mapped[int] = mapped_column(ForeignKey("streams.id"), index=True)
    batch_year: Mapped[int] = mapped_column(Integer, index=True)

    # Path to a representative photo (optional)
    photo_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Naive local wall clock (same interpretation as date.today() / timetable datetime.now() — set TZ on the server).
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=lambda: datetime.now(),
    )

    stream: Mapped["Stream"] = relationship(back_populates="students")
    attendance: Mapped[list["Attendance"]] = relationship(
        back_populates="student",
        cascade="all, delete-orphan",
    )


class Attendance(Base):
    __tablename__ = "attendance"
    __table_args__ = (
        UniqueConstraint("student_id", "date_key", "room", "class_name", name="uq_attendance_student_date_room_class"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    student_id: Mapped[int] = mapped_column(ForeignKey("students.id"), index=True)

    # e.g. "Room512"
    room: Mapped[str] = mapped_column(String(64))
    # e.g. course display / slot label (matches timetable class_name)
    class_name: Mapped[str] = mapped_column(String(128))

    status: Mapped[str] = mapped_column(String(16), default="present")  # present/absent

    # ISO date key "YYYY-MM-DD" for easier querying/uniqueness
    date_key: Mapped[str] = mapped_column(String(10), index=True)
    marked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=False),
        default=lambda: datetime.now(),
    )

    # optional geotag
    lat: Mapped[str | None] = mapped_column(String(32), nullable=True)
    lng: Mapped[str | None] = mapped_column(String(32), nullable=True)

    student: Mapped["Student"] = relationship(back_populates="attendance")


class ClassSchedule(Base):
    """
    Weekly recurring slot for a cohort: stream + batch_year, day/time, room, course.
    day_of_week: 0=Monday ... 6=Sunday (datetime.weekday()).
    All students in that stream and batch_year are eligible (no per-slot enrollment rows).
    """

    __tablename__ = "class_schedule"
    __table_args__ = (
        Index("ix_class_schedule_room_day", "room", "day_of_week"),
        Index("ix_class_schedule_stream_batch_dow", "stream_id", "batch_year", "day_of_week"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    stream_id: Mapped[int] = mapped_column(ForeignKey("streams.id"), index=True)
    batch_year: Mapped[int] = mapped_column(Integer, index=True)

    room: Mapped[str] = mapped_column(String(64), index=True)
    course_code: Mapped[str] = mapped_column(String(32), default="")
    class_name: Mapped[str] = mapped_column(String(128))

    day_of_week: Mapped[int] = mapped_column(Integer)  # 0 Mon .. 6 Sun
    start_time: Mapped[str] = mapped_column(String(16))  # "09:00"
    end_time: Mapped[str] = mapped_column(String(16))  # "10:00"

    attendance_window: Mapped[int] = mapped_column(Integer, default=10)
    late_window: Mapped[int] = mapped_column(Integer, default=20)

    stream: Mapped["Stream"] = relationship(back_populates="class_schedules")
