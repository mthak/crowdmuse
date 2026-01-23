from __future__ import annotations

from datetime import date

from fastapi import Depends, FastAPI, HTTPException
from sqlalchemy.orm import Session

from .db import SessionLocal, engine
from .models import Attendance, Base, Student
from .schemas import (
    AttendanceMarkRequest,
    AttendanceOut,
    StudentCreate,
    StudentOut,
)

app = FastAPI(title="CrowdMuse Backend", version="0.1.0")


# Create tables at startup (SQLite local dev)
@app.on_event("startup")
def on_startup() -> None:
    Base.metadata.create_all(bind=engine)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok"}


# Students
@app.post("/students", response_model=StudentOut, tags=["students"])
def create_student(payload: StudentCreate, db: Session = Depends(get_db)):
    existing = db.query(Student).filter_by(roll_number=payload.roll_number).first()
    if existing:
        raise HTTPException(status_code=409, detail="Student already exists")

    student = Student(
        roll_number=payload.roll_number,
        name=payload.name,
        year=payload.year,
        stream=payload.stream,
        photo_path=None,
    )
    db.add(student)
    db.commit()
    db.refresh(student)
    return student


@app.get("/students", response_model=list[StudentOut], tags=["students"])
def list_students(db: Session = Depends(get_db)):
    return db.query(Student).order_by(Student.created_at.desc()).all()


# Attendance
@app.post("/attendance/mark", response_model=AttendanceOut, tags=["attendance"])
def mark_attendance(payload: AttendanceMarkRequest, db: Session = Depends(get_db)):
    student = db.query(Student).filter_by(roll_number=payload.roll_number).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    today_key = date.today().isoformat()

    existing = (
        db.query(Attendance)
        .filter_by(
            student_id=student.id,
            date_key=today_key,
            room=payload.room,
            class_name=payload.class_name,
        )
        .first()
    )

    if existing:
        # Idempotent: return the existing record
        return _to_out(existing, student)

    record = Attendance(
        student_id=student.id,
        room=payload.room,
        class_name=payload.class_name,
        status=payload.status,
        date_key=today_key,
        lat=payload.lat,
        lng=payload.lng,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return _to_out(record, student)


@app.get("/attendance", response_model=list[AttendanceOut], tags=["attendance"])
def list_attendance(db: Session = Depends(get_db)):
    records = (
        db.query(Attendance, Student)
        .join(Student, Attendance.student_id == Student.id)
        .order_by(Attendance.marked_at.desc())
        .all()
    )
    return [_to_out(att, stu) for att, stu in records]


def _to_out(att: Attendance, student: Student) -> AttendanceOut:
    return AttendanceOut(
        id=att.id,
        student_id=att.student_id,
        student_roll=student.roll_number,
        student_name=student.name,
        room=att.room,
        class_name=att.class_name,
        status=att.status,
        date_key=att.date_key,
        marked_at=att.marked_at,
        lat=att.lat,
        lng=att.lng,
    )

