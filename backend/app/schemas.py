from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class StudentCreate(BaseModel):
    roll_number: str = Field(min_length=1, max_length=64)
    name: str = Field(min_length=1, max_length=128)
    year: int = Field(ge=1, le=10)
    stream: str = Field(min_length=1, max_length=128)


class StudentOut(BaseModel):
    id: int
    roll_number: str
    name: str
    year: int
    stream: str
    photo_path: str | None
    created_at: datetime


class AttendanceCreate(BaseModel):
    room: str = Field(min_length=1, max_length=64)
    class_name: str = Field(min_length=1, max_length=64)
    status: str = Field(default="present")
    lat: str | None = None
    lng: str | None = None


class AttendanceMarkRequest(AttendanceCreate):
    roll_number: str = Field(min_length=1, max_length=64)


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

