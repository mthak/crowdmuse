"""
Symmetric encryption for `cameras.password` at rest (Fernet).

Set **`CROWDMUSE_CAMERA_KEY`** to a strong secret (any string; it is hashed), or to a full
Fernet key from `python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"`.

Passwords are **never** returned from the HTTP API — only `has_password`. Decrypted values exist
in memory on the server when loading a `Camera` row (e.g. to build an RTSP URL via
`build_rtsp_playback_url`).
"""
from __future__ import annotations

import base64
import hashlib
import logging
import os
from urllib.parse import quote

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import String, Text, TypeDecorator

logger = logging.getLogger(__name__)


def _fernet() -> Fernet:
    raw = os.environ.get("CROWDMUSE_CAMERA_KEY", "").strip()
    if raw:
        try:
            return Fernet(raw.encode("ascii"))
        except Exception:
            key_material = hashlib.sha256(raw.encode("utf-8")).digest()
            return Fernet(base64.urlsafe_b64encode(key_material))
    # Dev / tests only — change `CROWDMUSE_CAMERA_KEY` in production.
    key_material = hashlib.sha256(b"crowdmuse-dev-only-camera-secret-change-me").digest()
    return Fernet(base64.urlsafe_b64encode(key_material))


def encrypt_password_for_storage(plain: str | None) -> str | None:
    if plain is None or plain == "":
        return None
    return _fernet().encrypt(plain.encode("utf-8")).decode("ascii")


def decrypt_password_from_storage(stored: str | None) -> str | None:
    if stored is None or stored == "":
        return None
    tok = stored.encode("utf-8")
    try:
        return _fernet().decrypt(tok).decode("utf-8")
    except (InvalidToken, ValueError, UnicodeDecodeError):
        pass
    except Exception as e:
        logger.debug("Unexpected decrypt error: %s", e)
    # Legacy row: plaintext before encryption, or key rotation — surface as-is; re-save encrypts.
    logger.warning(
        "Camera password not valid Fernet ciphertext; using stored value as plaintext (re-save via API to encrypt)"
    )
    return stored


class EncryptedPassword(TypeDecorator):
    """Persist Fernet ciphertext in SQLite; map to decrypted `str` in Python."""

    impl = Text
    cache_ok = True

    def process_bind_param(self, value, dialect):
        return encrypt_password_for_storage(value)

    def process_result_value(self, value, dialect):
        return decrypt_password_from_storage(value)


def build_rtsp_playback_url(
    *,
    rtsp_url: str | None,
    username: str | None,
    password: str | None,
) -> str | None:
    """
    Build an RTSP URL with credentials for **local use** (OpenCV, scripts).
    `rtsp_url` should **not** embed the password — e.g. `rtsp://192.168.1.10/stream1` — so secrets
    stay only in the encrypted password column.
    """
    if not rtsp_url or not rtsp_url.strip():
        return None
    url = rtsp_url.strip()
    if not url.startswith("rtsp://"):
        return url
    rest = url[7:]
    if "@" in rest.split("/")[0]:
        return url
    if username and password:
        return f"rtsp://{quote(username, safe='')}:{quote(password, safe='')}@{rest}"
    return url

