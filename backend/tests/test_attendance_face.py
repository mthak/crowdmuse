from __future__ import annotations

from datetime import datetime
from io import BytesIO
from unittest.mock import MagicMock, patch

from sqlalchemy.orm import sessionmaker

from app.main import app, get_face_service
from app.models import Attendance, Student


def test_mark_by_face_mocks_recognition_as_vikram_creates_attendance(
    client_with_vikram_face, test_engine
):
    """
    Face pipeline is mocked to return Vikram's roll_number (simulating existing encodings).
    POST /attendance/mark-by-face should insert an attendance row for that student.
    """
    files = {"image": ("face.jpg", BytesIO(b"fake-jpeg-bytes"), "image/jpeg")}
    data = {"room": "321", "class_name": "Fluid Mechanics"}

    r = client_with_vikram_face.post("/attendance/mark-by-face", files=files, data=data)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["student_roll"] == "98104ME003"
    assert body["student_name"] == "Vikram Singh"
    assert body["room"] == "321"
    assert body["class_name"] == "Fluid Mechanics"
    assert body["status"] == "present"

    SessionLocal = sessionmaker(bind=test_engine)
    db = SessionLocal()
    try:
        stu = db.query(Student).filter_by(roll_number="98104ME003").one()
        rows = db.query(Attendance).filter_by(student_id=stu.id).all()
        assert len(rows) == 1
        assert rows[0].class_name == "Fluid Mechanics"
    finally:
        db.close()


def test_mark_by_face_scheduled_resolves_slot_from_timetable(
    client_with_vikram_face, test_engine
):
    """
    Same mocked face → Vikram; frozen time falls in Tue 09:00–10:00 Fluid Mechanics in room 321.
    class_name on the attendance row must come from class_schedule, not the client.
    """
    files = {"image": ("face.jpg", BytesIO(b"fake"), "image/jpeg")}
    data = {"room": "321"}

    frozen_now = datetime(2026, 4, 7, 9, 30, 0)  # Tuesday, weekday() == 1
    assert frozen_now.weekday() == 1

    with (
        patch("app.timetable.datetime") as m_timetable_dt,
        patch("app.main.datetime") as m_main_dt,
    ):
        m_timetable_dt.now.return_value = frozen_now
        m_main_dt.now.return_value = frozen_now

        r = client_with_vikram_face.post(
            "/attendance/mark-by-face-scheduled", files=files, data=data
        )

    assert r.status_code == 200, r.text
    body = r.json()
    assert body["student_name"] == "Vikram Singh"
    assert body["room"] == "321"
    assert body["class_name"] == "Fluid Mechanics"
    assert body["date_key"] == "2026-04-07"

    SessionLocal = sessionmaker(bind=test_engine)
    db = SessionLocal()
    try:
        stu = db.query(Student).filter_by(roll_number="98104ME003").one()
        row = db.query(Attendance).filter_by(student_id=stu.id).one()
        assert row.class_name == "Fluid Mechanics"
    finally:
        db.close()


def test_mark_scheduled_roll_only_uses_timetable_and_local_date(
    client, seed_me_2025_vikram, test_engine
):
    """POST /attendance/mark-scheduled: roll + room; class_name and date_key from server local logic."""
    frozen_now = datetime(2026, 4, 7, 9, 30, 0)
    with (
        patch("app.timetable.datetime") as m_timetable_dt,
        patch("app.main.datetime") as m_main_dt,
    ):
        m_timetable_dt.now.return_value = frozen_now
        m_main_dt.now.return_value = frozen_now
        r = client.post(
            "/attendance/mark-scheduled",
            json={"roll_number": "98104ME003", "room": "321"},
        )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["class_name"] == "Fluid Mechanics"
    assert body["date_key"] == "2026-04-07"
    assert body["room"] == "321"


def test_mark_by_face_no_match_returns_404(client, seed_me_2025_vikram):
    mock = MagicMock()
    mock.recognize_face_from_image_bytes.return_value = None
    app.dependency_overrides[get_face_service] = lambda: mock
    try:
        files = {"image": ("x.jpg", BytesIO(b"x"), "image/jpeg")}
        r = client.post("/attendance/mark-by-face", files=files, data={"room": "321", "class_name": "X"})
        assert r.status_code == 404
        assert "No matching face" in r.json()["detail"]
    finally:
        del app.dependency_overrides[get_face_service]
