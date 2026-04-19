from __future__ import annotations

from app.camera_crypto import decrypt_password_from_storage, encrypt_password_for_storage


def test_password_encrypt_roundtrip():
    plain = "Smart5253"
    enc = encrypt_password_for_storage(plain)
    assert enc != plain
    assert decrypt_password_from_storage(enc) == plain


def test_create_list_patch_camera(client):
    r = client.post(
        "/cameras",
        json={
            "name": "Front",
            "ip_address": "192.168.1.50",
            "room": "102",
            "username": "u1",
            "password": "secret-pass",
            "rtsp_url": "rtsp://192.168.1.50/stream1",
            "is_active": True,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["room"] == "102"
    assert body["ip_address"] == "192.168.1.50"
    assert body["username"] == "u1"
    assert body["has_password"] is True
    assert "password" not in body
    cid = body["id"]

    r2 = client.get("/cameras", params={"room": "102", "active_only": "true"})
    assert r2.status_code == 200
    rows = r2.json()
    assert len(rows) == 1
    assert rows[0]["has_password"] is True
    assert "password" not in rows[0]

    r3 = client.patch(f"/cameras/{cid}", json={"is_active": False})
    assert r3.status_code == 200
    assert r3.json()["is_active"] is False
    assert "password" not in r3.json()

    r4 = client.get(f"/cameras/{cid}")
    assert r4.status_code == 200
    assert r4.json()["is_active"] is False
    assert r4.json()["has_password"] is True
