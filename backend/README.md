## Backend (FastAPI + SQLite + OpenCV)

This backend provides:
- Student registry (name, roll number, year, stream, photo(s))
- Face recognition (passport encodings + `mark-by-face` APIs)
- Attendance records (room + class name + optional geotag)
- **Room timetable** (weekly slots: room, day, time range, class label) and **enrollment** (which students are in which slot)
- **`POST /attendance/mark-by-face-scheduled`**: recognize face, resolve active class from **server local time** + room, verify enrollment, then mark

See `docs/ATTENDANCE_PIPELINE.md` for the camera pipeline.

### Timetable and enrollment (quick)

1. **Create slots** (example: Room123, Monday 9–10, Social Studies):

   `POST /timetable/slots` with JSON body:
   `{"room":"Room123","class_name":"Social Studies - s103","day_of_week":0,"start_time":"09:00","end_time":"10:00"}`  
   (`day_of_week`: 0=Monday … 6=Sunday)

2. **Enroll a student** in that slot:

   `POST /timetable/enroll` with `{"roll_number":"CS23-001","class_schedule_id":1}`

3. **Check active class now** (server clock):

   `GET /timetable/active?room=Room123`

4. **Hybrid camera script** calls `mark-by-face-scheduled` when a class is active (only **room** + image; class and enrollment are enforced on the server).

**DB migration:** If you had an older `class_schedule` table without `day_of_week`, delete `data/crowdmuse.sqlite3` and restart the API so tables are recreated, or add the column manually.

### Setup

Use **Python 3.12 or 3.13** if anything fails to install; **3.14** needs a current **pydantic** (see `requirements.txt`: `pydantic>=2.7.4`). Older pydantic builds break on 3.14 with `ForwardRef._evaluate ... recursive_guard`.

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

