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


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow)
    class_name: Mapped[str] = mapped_column(String(64))
    class_location: Mapped[str] = mapped_column(String(64))
    calsss_code:
    class_days: 
    attendance: Mapped[list["Attendance"]] = relationship(

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
    attendence_time: Mapped[datetime] = mapped_column(DateTime(timezone=False), default=datetime.utcnow)
    attendeance_class: <chemistry>
    

    student: Mapped["Student"] = relationship(back_populates="attendance")

