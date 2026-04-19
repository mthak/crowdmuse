from __future__ import annotations

from io import BytesIO
from pathlib import Path
from unittest.mock import MagicMock

import cv2
import numpy as np
import pytest

from app.main import app, get_face_service


@pytest.fixture
def tiny_jpeg_bytes():
    img = np.zeros((80, 80, 3), dtype=np.uint8)
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    assert ok
    return buf.tobytes()


def test_enrollment_image_404_unknown_roll(client, tiny_jpeg_bytes):
    files = {"image": ("e.jpg", BytesIO(tiny_jpeg_bytes), "image/jpeg")}
    data = {"roll_number": "UNKNOWN999"}
    r = client.post("/students/enrollment-image", files=files, data=data)
    assert r.status_code == 404


def test_enrollment_image_success_mocked_face(client, seed_me_2025_vikram, tiny_jpeg_bytes):
    mock_svc = MagicMock()
    mock_svc.encode_face_from_frame.return_value = np.ones(128, dtype=np.float64)
    mock_svc.save_enrollment_jpeg.return_value = Path("/tmp/mock_enroll.jpg")
    mock_svc.delete_encoding = MagicMock()
    mock_svc.save_encoding = MagicMock()

    app.dependency_overrides[get_face_service] = lambda: mock_svc
    try:
        files = {"image": ("e.jpg", BytesIO(tiny_jpeg_bytes), "image/jpeg")}
        data = {"roll_number": "98104ME003", "replace_encoding": "true"}
        r = client.post("/students/enrollment-image", files=files, data=data)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["roll_number"] == "98104ME003"
        assert body["student_name"] == "Vikram Singh"
        assert body["encoding_updated"] is True
        mock_svc.delete_encoding.assert_called_once_with("98104ME003")
        mock_svc.save_encoding.assert_called_once()
    finally:
        del app.dependency_overrides[get_face_service]


def test_enrollment_image_no_face_returns_400(client, seed_me_2025_vikram, tiny_jpeg_bytes):
    mock_svc = MagicMock()
    mock_svc.encode_face_from_frame.return_value = None
    app.dependency_overrides[get_face_service] = lambda: mock_svc
    try:
        files = {"image": ("e.jpg", BytesIO(tiny_jpeg_bytes), "image/jpeg")}
        r = client.post(
            "/students/enrollment-image",
            files=files,
            data={"roll_number": "98104ME003"},
        )
        assert r.status_code == 400
        assert "No face" in r.json()["detail"]
    finally:
        del app.dependency_overrides[get_face_service]


def test_enrollment_gallery_first_face_updates_encoding(
    client, seed_me_2025_vikram, tiny_jpeg_bytes
):
    mock_svc = MagicMock()
    mock_svc.encode_face_from_frame.side_effect = [np.ones(128), None]
    mock_svc.save_enrollment_jpeg.return_value = Path("/tmp/mock.jpg")
    mock_svc.delete_encoding = MagicMock()
    mock_svc.save_encoding = MagicMock()

    app.dependency_overrides[get_face_service] = lambda: mock_svc
    try:
        files = [
            ("images", ("a.jpg", BytesIO(tiny_jpeg_bytes), "image/jpeg")),
            ("images", ("b.jpg", BytesIO(tiny_jpeg_bytes), "image/jpeg")),
        ]
        r = client.post(
            "/students/enrollment-images",
            files=files,
            data={"roll_number": "98104ME003"},
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["encoding_updated"] is True
        assert len(body["items"]) == 2
        assert body["items"][0]["face_detected"] is True
        assert body["items"][1]["face_detected"] is False
        mock_svc.save_encoding.assert_called_once()
    finally:
        del app.dependency_overrides[get_face_service]
