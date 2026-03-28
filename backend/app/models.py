from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Student(Base):
    __tablename__ = "students"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    roll_number: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(128))
    year: Mapped[int] = mapped_column(Integer)
    stream: Mapped[str] = mapped_column(String(128))

    # Path to a representative photo (optional)
    photo_path: Mapped[str | None] = mapped_column(Text, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow)

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
    # e.g. "Class1"
    class_name: Mapped[str] = mapped_column(String(64))

    status: Mapped[str] = mapped_column(String(16), default="present")  # present/absent

    # ISO date key "YYYY-MM-DD" for easier querying/uniqueness
    date_key: Mapped[str] = mapped_column(String(10), index=True)
    marked_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow)

    # optional geotag
    lat: Mapped[str | None] = mapped_column(String(32), nullable=True)
    lng: Mapped[str | None] = mapped_column(String(32), nullable=True)

    student: Mapped["Student"] = relationship(back_populates="attendance")

class ClassSchedule(Base):
    __tablename__ = "class_schedule"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    room: Mapped[str] = mapped_column(String(64))
    class_name: Mapped[str] = mapped_column(String(64))
    batch: Mapped[str] = mapped_column(String(64))

    start_time: Mapped[str] = mapped_column(String(16))   # "09:00"
    end_time: Mapped[str] = mapped_column(String(16))     # "10:00"

    attendance_window: Mapped[int] = mapped_column(Integer, default=10)
    late_window: Mapped[int] = mapped_column(Integer, default=20)


