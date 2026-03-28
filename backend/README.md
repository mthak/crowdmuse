## Backend (FastAPI + SQLite + OpenCV)

This backend provides:
- Student registry (name, roll number, year, stream, photo(s))
- Face recognition (local OpenCV Haar + LBPH model)
- Attendance records (room + optional geotag)

### Setup

Create a virtualenv and install deps:

```bash
cd /Users/manu/crowdmuse/backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### Run the API

```bash
cd /Users/manu/crowdmuse/backend
source .venv/bin/activate
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open docs at `http://127.0.0.1:8000/docs`

### Enroll a student from Mac camera (demo)

```bash
cd /Users/manu/crowdmuse/backend
source .venv/bin/activate
python scripts/enroll_from_camera.py --name "Asha" --roll "CS23-001" --year 2 --stream "Computer Science"
```

### Mark attendance from camera (demo)

```bash
cd /Users/manu/crowdmuse/backend
source .venv/bin/activate
python scripts/mark_from_camera.py --room "Room512" --class-name "Class1"
```

