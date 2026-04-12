# How to run tests

Tests live under `backend/tests/` and use **pytest**. Run commands from the **`backend/`** directory so imports and `pytest.ini` resolve correctly.

## Prerequisites

- Python 3 with a virtual environment (recommended).
- Dependencies installed:

```bash
cd backend
pip install -r requirements.txt
```

`pytest` and `httpx` are listed under tests in `requirements.txt`.

## Run all tests

```bash
cd backend
python -m pytest tests/ -v
```

Shorter output:

```bash
python -m pytest tests/ -q
```

## API + tests in one shot

`scripts/run_api_and_tests.sh` starts Uvicorn on `127.0.0.1`, waits briefly, runs the full test suite, then stops the server. That lets **live HTTP** tests hit a real process instead of skipping.

```bash
cd backend
bash scripts/run_api_and_tests.sh
```

Optional: set `PORT` (default `8000`):

```bash
PORT=8001 bash scripts/run_api_and_tests.sh
```

The script may activate a venv at `../.cmuse/bin/activate` if present and `VIRTUAL_ENV` is unset.

## Live HTTP tests (`test_live_http.py`)

These call `GET /health` against a **running** API. If nothing is listening, they **skip** so `pytest tests/` still passes.

Start the API in another terminal:

```bash
cd backend
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
```

Then:

```bash
cd backend
python -m pytest tests/test_live_http.py -v
```

Override the base URL:

```bash
LIVE_API_URL=http://127.0.0.1:8000 python -m pytest tests/test_live_http.py -v
```

## Run a single file or test

```bash
cd backend
python -m pytest tests/test_attendance_face.py -v
python -m pytest tests/test_attendance_face.py::test_mark_scheduled_roll_only_uses_timetable_and_local_date -v
```

## Configuration

- `backend/pytest.ini` sets `pythonpath = .` and `testpaths = tests`.
- `backend/tests/conftest.py` sets up the in-memory DB and shared fixtures used by API tests.
