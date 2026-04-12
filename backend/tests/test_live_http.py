"""
HTTP calls against a **running** uvicorn process (real TCP).

Start the API first, then from `backend/`:

  uvicorn app.main:app --host 127.0.0.1 --port 8000

  LIVE_API_URL=http://127.0.0.1:8000 python -m pytest tests/test_live_http.py -v

If nothing is listening, tests are skipped (so `pytest tests/` still passes without a server).
"""
from __future__ import annotations

import os

import httpx
import pytest

_DEFAULT = "http://127.0.0.1:8000"


@pytest.fixture(scope="module")
def live_base():
    base = os.environ.get("LIVE_API_URL", _DEFAULT).rstrip("/")
    try:
        r = httpx.get(f"{base}/health", timeout=2.0)
        r.raise_for_status()
    except Exception as e:
        pytest.skip(f"Live API not reachable at {base}: {e}")
    return base


def test_health_over_http(live_base: str):
    r = httpx.get(f"{live_base}/health")
    assert r.status_code == 200
    assert r.json() == {"status": "ok"}
