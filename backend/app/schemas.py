from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class StreamCreate(BaseModel):
    name: str = Field(min_length=1, max_length=128)


class StreamOut(BaseModel):
    id: int
    name: str


class StudentCreate(BaseModel):
    roll_number: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    stream_id: int = Field(ge=1, description="FK to streams (e.g. Mechanical Engineering)")
    batch_year: int = Field(
        ge=1990,
        le=2100,
        description="Cohort year, e.g. 2025 for the 2025 batch",
    )


class StudentOut(BaseModel):
    id: int
    roll_number: str
    name: str
    stream_id: int
    batch_year: int
    photo_path: str | None
    created_at: datetime


class EnrollmentImageUploadOut(BaseModel):
    """Response after storing an enrollment photo + optional face encoding update."""

    roll_number: str
    student_name: str
    jpeg_path: str
    encoding_updated: bool
    message: str = ""


class EnrollmentGalleryItemOut(BaseModel):
    path: str
    face_detected: bool


class EnrollmentGalleryUploadOut(BaseModel):
    roll_number: str
    student_name: str
    items: list[EnrollmentGalleryItemOut]
    encoding_updated: bool


class AttendanceCreate(BaseModel):
    room: str = Field(min_length=1, max_length=64)
    class_name: str = Field(min_length=1, max_length=128)
    status: str = Field(default="present")
    lat: str | None = None
    lng: str | None = None
    camera_id: int | None = Field(
        default=None,
        description="Optional FK to `cameras.id`; must match `room` and be active.",
    )


class AttendanceMarkRequest(AttendanceCreate):
    roll_number: str = Field(min_length=1, max_length=64)


class AttendanceMarkScheduledRequest(BaseModel):
    """
    Mark present only if this roll has an active timetable row for `room` at the checked time
    (weekday + clock time) and the student's stream/batch matches that slot.
    """

    roll_number: str = Field(min_length=1, max_length=64)
    room: str = Field(min_length=1, max_length=64)
    at: datetime | None = Field(
        default=None,
        description=(
            "Instant to compare against the schedule (naive = server local wall clock). "
            "Default: server `datetime.now()`. `date_key` on the row is this instant's calendar date."
        ),
    )
    status: str = Field(default="present")
    lat: str | None = None
    lng: str | None = None
    camera_id: int | None = Field(
        default=None,
        description="Optional FK to `cameras.id`; must match `room` and be active.",
    )


class ClassScheduleCreate(BaseModel):
    stream_id: int = Field(ge=1)
    batch_year: int = Field(ge=1990, le=2100, description="Cohort this weekly row applies to")
    room: str = Field(min_length=1, max_length=64)
    course_code: str = Field(default="", max_length=32, description='e.g. "M3101"')
    class_name: str = Field(min_length=1, max_length=128, description="Display title for attendance row")
    day_of_week: int = Field(ge=0, le=6, description="0=Monday .. 6=Sunday")
    start_time: str = Field(min_length=4, max_length=16, description='e.g. "09:00"')
    end_time: str = Field(min_length=4, max_length=16, description='e.g. "10:00"')
    attendance_window: int = Field(default=10, ge=0, le=120)
    late_window: int = Field(default=20, ge=0, le=120)


class ClassScheduleOut(BaseModel):
    id: int
    stream_id: int
    batch_year: int
    room: str
    course_code: str
    class_name: str
    day_of_week: int
    start_time: str
    end_time: str
    attendance_window: int
    late_window: int


class AttendanceOut(BaseModel):
    id: int
    student_id: int
    student_roll: str
    student_name: str
    room: str
    class_name: str
    status: str
    date_key: str
    marked_at: datetime
    lat: str | None
    lng: str | None
    camera_id: int | None = None


class CameraCreate(BaseModel):
    name: str = Field(default="", max_length=128)
    ip_address: str = Field(min_length=1, max_length=256, description="IPv4/IPv6 or hostname")
    room: str = Field(min_length=1, max_length=64, description="Same label as timetable/attendance room, e.g. 102")
    username: str | None = Field(default=None, max_length=128, description="RTSP login (optional)")
    password: str | None = Field(default=None, description="RTSP password (optional; sensitive)")
    rtsp_url: str | None = Field(
        default=None,
        description="Full RTSP URL for OpenCV; optional if clients build from IP + username/password",
    )
    is_active: bool = True
    notes: str | None = None


class CameraUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=128)
    ip_address: str | None = Field(default=None, min_length=1, max_length=256)
    room: str | None = Field(default=None, min_length=1, max_length=64)
    username: str | None = None
    password: str | None = None
    rtsp_url: str | None = None
    is_active: bool | None = None
    notes: str | None = None


class CameraOut(BaseModel):
    """Public camera record — **password is never serialized** (use `has_password`)."""

    id: int
    name: str
    ip_address: str
    room: str
    username: str | None
    has_password: bool = False
    rtsp_url: str | None
    is_active: bool
    notes: str | None
    created_at: datetime

    model_config = {"from_attributes": True}
