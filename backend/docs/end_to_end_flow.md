# End-to-end: enroll → face data → camera attendance

This document describes how to run CrowdMuse from **creating a student** through **marking attendance from a camera**. It ties together the API, on-disk face encodings, the timetable, and the long-running attendance clients.

**Step-by-step reference for streams, classes (timetable), cameras, students, enrollment, and attendance—each with REST (`curl`) and command-line options:** **`end_to_end_complete_guide.md`**.

## What you are wiring together

| Piece | Role |
|--------|------|
| **`students` table** | Who is in which program (`stream_id`) and cohort (`batch_year`). Created via **`POST /students`** (or helpers that call it). |
| **`data/face_encodings/<roll_number>.json`** | Face **encodings** the server and `mark_attendance.py` use to recognize someone. **This is what attendance matching uses**, not a URL in the database. |
| **`data/face_encodings/<roll_number>.jpg`** (optional) | Cropped reference photo for humans and debugging. Helpful but not required for recognition if `.json` exists. |
| **`class_schedule` rows** | Which class is “active” for a **room** at **server local** time (used by scheduled face marking). |
| **`cameras` table** (optional) | Room ↔ RTSP device; used by **`scripts/room_camera_attendance.py`** to pick a stream and optionally tag **`camera_id`** on marks. |
| **FastAPI process** | Loads encodings, serves timetable checks, and receives **`POST /attendance/mark-by-face-scheduled`** (and related endpoints). A background thread also runs session/absent housekeeping—**keep Uvicorn running** while you test cameras. |
| **`mark_attendance.py`** or **`scripts/room_camera_attendance.py`** | Long-running **client** that reads video (USB or RTSP), recognizes faces locally, and when a class is in session posts face crops to the API to mark attendance. |

Recognition flow at mark time: **camera frame → face encoding → match against `*.json` files → roll number → timetable + cohort check → `attendance` row.** The enrollment JPEG path is not read back for matching; ensure the **JSON encoding** exists and matches the person in front of the camera.

---

## Prerequisites

- Python **virtualenv** with **`pip install -r requirements.txt`** (from **`backend/`**).
- Default database file: **`backend/data/crowdmuse.sqlite3`** (same file the API uses when you start Uvicorn from **`backend/`**). If you use another path, point scripts and env consistently.
- For network cameras, a working **RTSP URL** on your LAN (test with **`scripts/test_rtsp_camera_preview.py`** if needed).

---

## 1. Start the API (leave it running)

From **`backend/`**:

```bash
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

- Open **`http://127.0.0.1:8000/docs`** to confirm the app is up.
- **Keep this process running** for all enrollment and attendance steps below. The app’s lifespan starts background work (e.g. absent/session helpers); attendance marking is handled when the **camera client** calls the HTTP API.

---

## 2. Enroll the student (database row first)

A face cannot be “official” until there is a **`Student`** row whose **`roll_number`** matches the files under **`data/face_encodings/`**.

**Option A — `enroll_student.py` (creates student + face in one go when you use camera/photo):**

```bash
cd backend
python enroll_student.py --roll-number 98104ME102 --name "Asha Menon" \
  --batch-year 2025 --stream "Mechanical Engineering" --camera 0
```

**Option B — API only (student first, face later):**

```bash
curl -s -X POST http://127.0.0.1:8000/students \
  -H "Content-Type: application/json" \
  -d '{"roll_number":"98104ME102","name":"Asha Menon","stream_id":1,"batch_year":2025}'
```

(Use a real **`stream_id`** from **`GET /streams`**.)

If the student **already exists** (`409`), enrollment scripts still continue to add or refresh encodings.

---

## 3. Add face data (same day or later)

You need at least **`data/face_encodings/<roll>.json`**. The API and scripts also write **`<roll>.jpg`** next to it for a clear reference image.

**Ways to populate:**

| Method | When to use |
|--------|----------------|
| **`enroll_student.py`** with **`--photo`**, **`--camera`**, or **`--rtsp`** | One-shot from laptop or IP camera. |
| **`POST /students/enrollment-image`** | Upload a single image (e.g. phone or browser multipart). Form fields: **`roll_number`**, file **`image`**, optional **`replace_encoding`**. |
| **`POST /students/enrollment-images`** | Several files field **`images`**; gallery under **`data/enrollment_gallery/<roll>/`**; first good face can update primary encoding. |
| **`scripts/capture_and_upload_enrollment.py`** | Mac/USB webcam → **`POST /students/enrollment-image`**. |

Example (laptop webcam → API):

```bash
cd backend
python scripts/capture_and_upload_enrollment.py \
  --roll-number 98104ME102 --api-url http://127.0.0.1:8000 --camera 0
```

**Restart the API** after adding encodings **if** the running process cached an old `FaceRecognitionService` instance without your new roll (during development, **`--reload`** after file changes often picks up new JSON files on the next request; if marks fail with “no match”, restart Uvicorn once).

---

## 4. Timetable and room (so “scheduled” marking works)

**`POST /attendance/mark-by-face-scheduled`** (used by the camera clients) requires:

- An **active** schedule row for the **`room`** at **server `datetime.now()`**, and  
- The student’s **`stream_id`** + **`batch_year`** matching that slot’s cohort.

For room **102** sample data (Mon–Fri 09:00–10:00) and student **98104ME102**:

```bash
cd backend
python scripts/room102_sample_data.py
```

Point **`--db`** at your real SQLite file if it is not the default **`data/crowdmuse.sqlite3`**.

Verify the slot the server will see:

```bash
curl -s "http://127.0.0.1:8000/timetable/active?room=102"
```

Adjust your test time or add a slot that brackets “now”, or use **`scripts/demo_face_scheduled_e2e.py --setup`** (see **`how_to_run_demo.md`**) for a temporary window around the current clock.

---

## 5. Camera in the database (for `room_camera_attendance.py`)

**`scripts/room_camera_attendance.py`** loads the first **active** **`cameras`** row for **`--room`** and opens **`Camera.effective_rtsp_url()`**.

Insert or upsert a camera (example helpers):

```bash
cd backend
python scripts/upsert_camera001.py
# or: python scripts/add_sample_camera_to_existing_db.py --db data/crowdmuse.sqlite3
```

Use **`POST /cameras`** in Swagger if you prefer. For USB-only tests without RTSP, use **`--no-db-camera --camera 0`** (see below).

---

## 6. Run the attendance / camera client

This is the **separate process** that captures video and calls the mark API when a class is active.

### A. Generic: `mark_attendance.py` (explicit RTSP or USB)

From **`backend/`**:

```bash
# USB webcam, room must match timetable + camera optional
python mark_attendance.py --room 102 --camera 0 --api-url http://127.0.0.1:8000

# RTSP (hybrid pipeline by default)
python mark_attendance.py --room 102 --rtsp 'rtsp://USER:PASS@192.168.x.x/stream1' \
  --api-url http://127.0.0.1:8000
```

Optional: **`--camera-id <id>`** if you registered a **`cameras`** row and want it stored on attendance rows. Stop with **Ctrl+C**.

### B. Room helper: `scripts/room_camera_attendance.py` (RTSP from SQLite)

Uses the **database camera** for the room unless you override:

```bash
cd backend
python scripts/room_camera_attendance.py --room 102 --api-url http://127.0.0.1:8000
```

USB without DB camera:

```bash
python scripts/room_camera_attendance.py --room 102 --no-db-camera --camera 0
```

The loop: poll **`GET /timetable/active`**, when a class is in session send crops to **`POST /attendance/mark-by-face-scheduled`**.

---

## 7. Confirm marks

- **Swagger:** **`GET /attendance/by-room/{room}`** with optional **`date_key`**.
- Or SQL / DB browser on **`attendance`** for **`student_id`**, **`room`**, **`class_name`**, **`date_key`**.

---

## Quick checklist

1. [ ] Uvicorn running on the URL your scripts use.  
2. [ ] **`Student`** row exists for the roll you encode.  
3. [ ] **`data/face_encodings/<roll>.json`** present (and optional **`.jpg`**).  
4. [ ] **Timetable** includes an active slot for **`room`** at the **server’s** current time; cohort matches the student.  
5. [ ] **Camera client** (`mark_attendance.py` or **`room_camera_attendance.py`**) running; person visible; lighting acceptable.  
6. [ ] If recognition fails, restart API after adding encodings and re-test.

---

## Related docs

- **`how_to_run_demo.md`** — scripted demos (`demo_face_scheduled_e2e.py`, room **102** camera, troubleshooting).  
- **`what_all_tables.md`** — tables, cohort rules, endpoint summary.  
- **`how_to_run_tests.md`** — pytest.
