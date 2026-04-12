from __future__ import annotations
import logging
import threading
import time
from contextlib import asynccontextmanager
from datetime import date, datetime

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import RedirectResponse
from sqlalchemy.orm import Session

from .attendance_excel import schedule_attendance_excel_export
from .db import DATA_DIR, SessionLocal, engine, session_scope
from .face_recognition_service import FaceRecognitionService
from .models import Attendance, Base, ClassSchedule, Stream, Student
from .session_absent import apply_absent_processed_keys, run_absent_sweeps
from .schemas import (
    AttendanceMarkRequest,
    AttendanceMarkScheduledRequest,
    AttendanceOut,
    ClassScheduleCreate,
    ClassScheduleOut,
    StreamCreate,
    StreamOut,
    StudentCreate,
    StudentOut,
)
from .timetable import get_active_schedule_for_room, resolve_student_scheduled_attendance

logger = logging.getLogger(__name__)

# Face recognition: encodings live next to DB (passport photos → encodings stored here)
ENCODINGS_DIR = DATA_DIR / "face_encodings"
_face_service: FaceRecognitionService | None = None

BACKGROUND_POLL_SEC = 45.0


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    t = threading.Thread(target=_background_attendance_worker, daemon=True, name="attendance-bg")
    t.start()
    schedule_attendance_excel_export()
    yield


app = FastAPI(title="CrowdMuse Backend", version="0.1.0", lifespan=lifespan)


@app.get("/", include_in_schema=False)
def root():
    """OpenAPI UI lives under `/docs` and `/redoc`; `/` redirects for convenience."""
    return RedirectResponse(url="/docs")


def get_face_service() -> FaceRecognitionService:
    global _face_service
    if _face_service is None:
        _face_service = FaceRecognitionService(encodings_dir=str(ENCODINGS_DIR))
    return _face_service


def _background_attendance_worker() -> None:
    """Session-end absent sweeps; Excel refresh when new absent rows are inserted."""
    while True:
        time.sleep(BACKGROUND_POLL_SEC)
        try:
            with session_scope() as db:
                inserted, keys = run_absent_sweeps(db)
            apply_absent_processed_keys(keys)
            if inserted > 0:
                schedule_attendance_excel_export()
        except Exception:
            logger.exception("Background attendance worker failed")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@app.get("/health", tags=["system"])
def health():
    return {"status": "ok"}


# Streams (programs / branches)
@app.post("/streams", response_model=StreamOut, tags=["streams"])
def create_stream(payload: StreamCreate, db: Session = Depends(get_db)):
    name = payload.name.strip()
    existing = db.query(Stream).filter_by(name=name).first()
    if existing:
        raise HTTPException(status_code=409, detail="Stream already exists")
    row = Stream(name=name)
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


@app.get("/streams", response_model=list[StreamOut], tags=["streams"])
def list_streams(db: Session = Depends(get_db)):
    return db.query(Stream).order_by(Stream.name).all()


# Students (cohort = stream_id + batch_year)
@app.post("/students", response_model=StudentOut, tags=["students"])
def create_student(payload: StudentCreate, db: Session = Depends(get_db)):
    existing = db.query(Student).filter_by(roll_number=payload.roll_number).first()
    if existing:
        raise HTTPException(status_code=409, detail="Student already exists")
    stream = db.query(Stream).filter_by(id=payload.stream_id).first()
    if not stream:
        raise HTTPException(status_code=404, detail="Stream not found")

    student = Student(
        roll_number=payload.roll_number,
        name=payload.name,
        stream_id=payload.stream_id,
        batch_year=payload.batch_year,
        photo_path=None,
    )
    db.add(student)
    db.commit()
    db.refresh(student)
    return student


@app.get("/students", response_model=list[StudentOut], tags=["students"])
def list_students(db: Session = Depends(get_db)):
    return db.query(Student).order_by(Student.created_at.desc()).all()


# Timetable (weekly rows per stream + batch_year cohort)
@app.post("/timetable/slots", response_model=ClassScheduleOut, tags=["timetable"])
def create_schedule_slot(payload: ClassScheduleCreate, db: Session = Depends(get_db)):
    stream = db.query(Stream).filter_by(id=payload.stream_id).first()
    if not stream:
        raise HTTPException(status_code=404, detail="Stream not found")
    slot = ClassSchedule(
        stream_id=payload.stream_id,
        batch_year=payload.batch_year,
        room=payload.room.strip(),
        course_code=payload.course_code.strip(),
        class_name=payload.class_name.strip(),
        day_of_week=payload.day_of_week,
        start_time=payload.start_time.strip(),
        end_time=payload.end_time.strip(),
        attendance_window=payload.attendance_window,
        late_window=payload.late_window,
    )
    db.add(slot)
    db.commit()
    db.refresh(slot)
    return slot


@app.get("/timetable/slots", response_model=list[ClassScheduleOut], tags=["timetable"])
def list_schedule_slots(
    room: str | None = None,
    stream_id: int | None = None,
    batch_year: int | None = None,
    db: Session = Depends(get_db),
):
    q = db.query(ClassSchedule).order_by(
        ClassSchedule.stream_id,
        ClassSchedule.batch_year,
        ClassSchedule.day_of_week,
        ClassSchedule.start_time,
    )
    if room:
        q = q.filter(ClassSchedule.room == room.strip())
    if stream_id is not None:
        q = q.filter(ClassSchedule.stream_id == stream_id)
    if batch_year is not None:
        q = q.filter(ClassSchedule.batch_year == batch_year)
    return q.all()


@app.delete("/timetable/slots/{slot_id}", tags=["timetable"])
def delete_schedule_slot(slot_id: int, db: Session = Depends(get_db)):
    slot = db.query(ClassSchedule).filter_by(id=slot_id).first()
    if not slot:
        raise HTTPException(status_code=404, detail="Slot not found")
    db.delete(slot)
    db.commit()
    return {"ok": True}


@app.get("/timetable/active", tags=["timetable"])
def get_active_slot(room: str, db: Session = Depends(get_db)):
    """Which timetable slot is active for this room right now (server local time)?"""
    slot = get_active_schedule_for_room(db, room.strip(), datetime.now())
    if not slot:
        return {"active": False, "room": room.strip(), "message": "No matching slot"}
    return {
        "active": True,
        "room": slot.room,
        "stream_id": slot.stream_id,
        "batch_year": slot.batch_year,
        "course_code": slot.course_code,
        "class_name": slot.class_name,
        "slot_id": slot.id,
        "start_time": slot.start_time,
        "end_time": slot.end_time,
        "day_of_week": slot.day_of_week,
        "attendance_window": slot.attendance_window,
        "late_window": slot.late_window,
    }


# Attendance
def _persist_attendance_mark(
    db: Session,
    *,
    student: Student,
    room: str,
    class_name: str,
    status: str,
    date_key: str,
    lat: str | None,
    lng: str | None,
) -> AttendanceOut:
    """Insert or return existing row for (student, date_key, room, class_name). `marked_at` = insert time."""
    room_s = room.strip()
    existing = (
        db.query(Attendance)
        .filter_by(
            student_id=student.id,
            date_key=date_key,
            room=room_s,
            class_name=class_name,
        )
        .first()
    )
    if existing:
        out = _to_out(existing, student)
        schedule_attendance_excel_export()
        return out
    record = Attendance(
        student_id=student.id,
        room=room_s,
        class_name=class_name,
        status=status,
        date_key=date_key,
        marked_at=datetime.now(),
        lat=lat,
        lng=lng,
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    schedule_attendance_excel_export()
    return _to_out(record, student)


@app.post("/attendance/mark", response_model=AttendanceOut, tags=["attendance"])
def mark_attendance(payload: AttendanceMarkRequest, db: Session = Depends(get_db)):
    """
    Manual mark: client supplies `class_name` (no timetable check). `date_key` = server **local today**
    (`date.today()`). Prefer **`POST /attendance/mark-scheduled`**: same roll + room, class and session
    date come from the timetable at **server now** (or optional `at` in body).
    """
    student = db.query(Student).filter_by(roll_number=payload.roll_number).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")
    today_key = date.today().isoformat()
    return _persist_attendance_mark(
        db,
        student=student,
        room=payload.room,
        class_name=payload.class_name,
        status=payload.status,
        date_key=today_key,
        lat=payload.lat,
        lng=payload.lng,
    )


@app.post("/attendance/mark-scheduled", response_model=AttendanceOut, tags=["attendance"])
def mark_attendance_scheduled(payload: AttendanceMarkScheduledRequest, db: Session = Depends(get_db)):
    """
    **Verified mark:** `roll_number` + `room`, optional `at` (default **server `datetime.now()`**).
    Finds the active `class_schedule` for that **room** at **that instant** (weekday + time window).
    Marks **present** only if the student's **stream_id / batch_year** match the slot. Stores
    **`date_key`** = calendar date of **`at`** (or of now), **`class_name`** from the slot.
    """
    student = db.query(Student).filter_by(roll_number=payload.roll_number.strip()).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    when = payload.at if payload.at is not None else datetime.now()
    if when.tzinfo is not None:
        when = when.astimezone().replace(tzinfo=None)

    slot, err = resolve_student_scheduled_attendance(db, student, payload.room.strip(), when=when)
    if slot is None:
        code = 403 if err.startswith("Student's stream") else 400
        raise HTTPException(status_code=code, detail=err)

    session_date_key = when.date().isoformat()
    return _persist_attendance_mark(
        db,
        student=student,
        room=payload.room.strip(),
        class_name=slot.class_name,
        status=payload.status,
        date_key=session_date_key,
        lat=payload.lat,
        lng=payload.lng,
    )


def _list_attendance_filtered(
    db: Session,
    *,
    roll_number: str | None = None,
    room: str | None = None,
    date_key: str | None = None,
    class_name: str | None = None,
) -> list[AttendanceOut]:
    q = db.query(Attendance, Student).join(Student, Attendance.student_id == Student.id)
    if roll_number:
        q = q.filter(Student.roll_number == roll_number.strip())
    if room:
        q = q.filter(Attendance.room == room.strip())
    if date_key:
        q = q.filter(Attendance.date_key == date_key.strip())
    if class_name:
        q = q.filter(Attendance.class_name == class_name.strip())
    records = q.order_by(Attendance.marked_at.desc()).all()
    return [_to_out(att, stu) for att, stu in records]


@app.get("/attendance", response_model=list[AttendanceOut], tags=["attendance"])
def list_attendance(
    db: Session = Depends(get_db),
    roll_number: str | None = None,
    room: str | None = None,
    date_key: str | None = None,
    class_name: str | None = None,
):
    """
    List attendance rows (newest first). Optional query filters combine with AND:
    `roll_number`, `room`, `date_key` (YYYY-MM-DD), `class_name` (exact match).
    """
    return _list_attendance_filtered(
        db,
        roll_number=roll_number,
        room=room,
        date_key=date_key,
        class_name=class_name,
    )


@app.get(
    "/attendance/by-roll/{roll_number}",
    response_model=list[AttendanceOut],
    tags=["attendance"],
)
def list_attendance_by_roll(
    roll_number: str,
    db: Session = Depends(get_db),
    date_key: str | None = None,
):
    """GET attendance for one student by roll number; optional `date_key` (YYYY-MM-DD)."""
    return _list_attendance_filtered(db, roll_number=roll_number, date_key=date_key)


@app.get(
    "/attendance/by-room/{room}",
    response_model=list[AttendanceOut],
    tags=["attendance"],
)
def list_attendance_by_room(
    room: str,
    db: Session = Depends(get_db),
    date_key: str | None = None,
    class_name: str | None = None,
):
    """GET attendance in one room; optional `date_key`, `class_name` (exact)."""
    return _list_attendance_filtered(db, room=room, date_key=date_key, class_name=class_name)


@app.post("/attendance/mark-by-face", response_model=AttendanceOut, tags=["attendance"])
async def mark_attendance_by_face(
    image: UploadFile = File(...),
    room: str = Form(...),
    class_name: str = Form(...),
    lat: str | None = Form(None),
    lng: str | None = Form(None),
    tolerance: float = Form(0.6),
    db: Session = Depends(get_db),
    face_svc: FaceRecognitionService = Depends(get_face_service),
):
    """
    Face → roll number, then mark with **client-supplied** `class_name` (no timetable check).
    For classroom cameras, prefer **`POST /attendance/mark-by-face-scheduled`** (room only):
    server picks the active class from the timetable and checks stream/batch cohort.
    """
    contents = await image.read()
    result = face_svc.recognize_face_from_image_bytes(contents, tolerance=tolerance)
    if not result:
        raise HTTPException(status_code=404, detail="No matching face found")
    roll_number, _ = result
    payload = AttendanceMarkRequest(
        roll_number=roll_number,
        room=room,
        class_name=class_name,
        status="present",
        lat=lat,
        lng=lng,
    )
    return mark_attendance(payload, db)


@app.post("/attendance/mark-by-face-scheduled", response_model=AttendanceOut, tags=["attendance"])
async def mark_attendance_by_face_scheduled(
    image: UploadFile = File(...),
    room: str = Form(...),
    lat: str | None = Form(None),
    lng: str | None = Form(None),
    tolerance: float = Form(0.6),
    db: Session = Depends(get_db),
    face_svc: FaceRecognitionService = Depends(get_face_service),
):
    """
    Same rules as **`POST /attendance/mark-scheduled`**, but `roll_number` comes from face match.
    Schedule is evaluated at **server `datetime.now()`** right after recognition; `date_key` is that
    instant's calendar date (aligned with the timetable check).
    """
    contents = await image.read()
    result = face_svc.recognize_face_from_image_bytes(contents, tolerance=tolerance)
    if not result:
        raise HTTPException(status_code=404, detail="No matching face found")
    roll_number, _ = result
    student = db.query(Student).filter_by(roll_number=roll_number).first()
    if not student:
        raise HTTPException(status_code=404, detail="Student not found")

    when = datetime.now()
    slot, err = resolve_student_scheduled_attendance(db, student, room.strip(), when=when)
    if slot is None:
        code = 403 if err.startswith("Student's stream") else 400
        raise HTTPException(status_code=code, detail=err)

    return _persist_attendance_mark(
        db,
        student=student,
        room=room.strip(),
        class_name=slot.class_name,
        status="present",
        date_key=when.date().isoformat(),
        lat=lat,
        lng=lng,
    )


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

