from __future__ import annotations

import os

# Stable Fernet material for camera password encryption in tests (must be set before `app` import).
os.environ.setdefault("CROWDMUSE_CAMERA_KEY", "pytest-crowdmuse-camera-encryption-key")

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.main import app, get_db, get_face_service
from app.models import Base, ClassSchedule, Stream, Student


@pytest.fixture
def test_engine():
    # StaticPool: SQLite :memory: is per-connection otherwise — seed session and API session saw different DBs.
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(bind=engine)
    return engine


@pytest.fixture
def client(test_engine):
    SessionLocal = sessionmaker(
        bind=test_engine, autoflush=False, autocommit=False, expire_on_commit=False
    )

    def override_get_db():
        db = SessionLocal()
        try:
            yield db
        finally:
            db.close()

    app.dependency_overrides[get_db] = override_get_db

    with patch("app.main.schedule_attendance_excel_export"):
        yield TestClient(app)

    app.dependency_overrides.clear()


@pytest.fixture
def seed_me_2025_vikram(test_engine):
    """Mechanical Engineering 2025 + Vikram Singh (roll 98104ME003) + Tue 9:30 slot room 321."""
    SessionLocal = sessionmaker(
        bind=test_engine, autoflush=False, autocommit=False, expire_on_commit=False
    )
    db = SessionLocal()
    me = Stream(name="Mechanical Engineering")
    db.add(me)
    db.commit()
    db.refresh(me)

    vikram = Student(
        roll_number="98104ME003",
        name="Vikram Singh",
        stream_id=me.id,
        batch_year=2025,
        photo_path=None,
    )
    db.add(vikram)
    db.commit()
    db.refresh(vikram)

    # Tuesday 09:00–10:00, room 321 — matches frozen clock in scheduled test
    slot = ClassSchedule(
        stream_id=me.id,
        batch_year=2025,
        room="321",
        course_code="M3102",
        class_name="Fluid Mechanics",
        day_of_week=1,
        start_time="09:00",
        end_time="10:00",
    )
    db.add(slot)
    db.commit()
    db.close()


@pytest.fixture
def mock_face_vikram():
    """Pretend face recognition matched Vikram Singh's roll (as if encodings existed)."""
    mock = MagicMock(spec_set=["recognize_face_from_image_bytes"])
    mock.recognize_face_from_image_bytes.return_value = ("98104ME003", 0.92)
    return mock


@pytest.fixture
def client_with_vikram_face(client, mock_face_vikram, seed_me_2025_vikram):
    """Test client + in-memory DB seeded with Vikram + ME 2025 timetable + mocked face → Vikram's roll."""
    app.dependency_overrides[get_face_service] = lambda: mock_face_vikram
    yield client
    del app.dependency_overrides[get_face_service]
