# CrowdMuse: end-to-end guide (API and command line)

This document explains how to run the system from **empty setup** through **enrolling students**, **configuring classes (timetable), cameras, and streams**, and **marking attendance**—using either the **HTTP API** (Swagger or `curl`) or **command-line scripts** under **`backend/`**.

For a shorter narrative focused on face data and camera clients, see **`end_to_end_flow.md`**. For demo scripts and troubleshooting, see **`how_to_run_demo.md`** and **`what_all_tables.md`**.

---

## Concepts (read once)

| Piece | Purpose |
|--------|---------|
| **`streams`** | Academic program / branch (e.g. Mechanical Engineering). |
| **`students`** | A person with **`roll_number`**, **`stream_id`**, and **`batch_year`** (cohort). |
| **`class_schedule`** | Weekly **slots**: room, weekday, time window, **`class_name`**, and which **`stream_id` + `batch_year`** the slot applies to. **Scheduled** attendance only works if the student’s cohort matches the active slot. |
| **`cameras`** | Optional RTSP device tied to a **room**; used by attendance clients and optional **`camera_id`** on marks. |
| **`data/face_encodings/<roll>.json`** | Face vectors used for recognition. **Attendance matching uses these files**, not a photo URL in the database. |
| **Server time** | **`GET /timetable/active`** and scheduled marks use the **machine running Uvicorn** local clock. |

**`day_of_week` in the API:** `0` = Monday … `6` = Sunday.

Set a base URL for examples:

```bash
export API=http://127.0.0.1:8000
```

Run all commands from **`backend/`** unless noted. Keep **Uvicorn running** while calling the API:

```bash
cd backend
python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

Open **`http://127.0.0.1:8000/docs`** to try the same operations interactively (**Swagger UI**).

---

## Quick map: “I want to …”

| Goal | API (summary) | Command line (scripts) |
|------|----------------|-------------------------|
| Add a **stream** | `POST /streams` | `curl` below; or DB helpers like **`room102_sample_data.py`** create “Mechanical Engineering” |
| Add **weekly class slots** | `POST /timetable/slots` | **`python scripts/room102_sample_data.py`** (room 102 sample + student) |
| Add a **camera** | `POST /cameras` | **`python scripts/upsert_camera001.py`**, **`add_sample_camera_to_existing_db.py`** |
| Add a **student** | `POST /students` | **`python enroll_student.py …`** (calls API) |
| Add **face encodings** | `POST /students/enrollment-image` | **`enroll_student.py`**, **`python scripts/capture_and_upload_enrollment.py …`** |
| **Mark attendance** (timetable-aware) | `POST /attendance/mark-scheduled` or `…/mark-by-face-scheduled` | **`python mark_attendance.py …`**, **`python scripts/room_camera_attendance.py …`** |
| **List attendance** | `GET /attendance?room=…&date_key=…` | `curl` or Swagger |

---

## 1. Streams (programs / branches)

### Option A — REST API

Create (409 if the name already exists):

```bash
curl -s -X POST "$API/streams" -H "Content-Type: application/json" \
  -d '{"name":"Mechanical Engineering"}'
```

List IDs and names:

```bash
curl -s "$API/streams"
```

Note the returned **`id`** (e.g. `1`) for **`stream_id`** when creating students and timetable rows.

### Option B — Command line

- Same as Option A using **`curl`** from the shell (no separate binary).
- **`python scripts/room102_sample_data.py`** ensures a stream named **“Mechanical Engineering”** exists in **`data/crowdmuse.sqlite3`** (and adds sample slots/student—see section 2).
- **`enroll_student.py`** can create the stream via **`GET/POST /streams`** if you pass **`--stream "…"`** and the stream is missing.

---

## 2. Weekly classes (timetable slots)

Each row is one recurring weekly window for a **room** and cohort (**`stream_id` + `batch_year`**).

### Option A — REST API

Create one slot (adjust **`stream_id`**, **`day_of_week`**, and times to match when you will test):

```bash
curl -s -X POST "$API/timetable/slots" -H "Content-Type: application/json" -d '{
  "stream_id": 1,
  "batch_year": 2025,
  "room": "102",
  "course_code": "M3101",
  "class_name": "Fluid Mechanics",
  "day_of_week": 0,
  "start_time": "09:00",
  "end_time": "10:00",
  "attendance_window": 10,
  "late_window": 20
}'
```

List and inspect:

```bash
curl -s "$API/timetable/slots?room=102"
curl -s "$API/timetable/active?room=102"
```

**`GET /timetable/active`** tells you whether **right now** (server clock) falls inside any slot for that **room** and shows **`class_name`** if active.

### Option B — Command line (bulk sample for room 102)

This merges into the default DB (**`data/crowdmuse.sqlite3`**) unless you pass **`--db`**:

```bash
cd backend
python scripts/room102_sample_data.py
# or: python scripts/room102_sample_data.py --db data/sample_crowdmuse.sqlite3
```

It ensures **Mechanical Engineering**, student **`98104ME102`**, and **Mon–Fri 09:00–10:00** slots in room **`102`** (see script source for exact course labels).

**Restart Uvicorn** after editing the DB with scripts if the API already had the file open and you need a clean read (usually not required for SQLite, but safe if counts look stale).

---

## 3. Cameras (optional, for RTSP room clients)

### Option A — REST API

```bash
curl -s -X POST "$API/cameras" -H "Content-Type: application/json" -d '{
  "name": "Front",
  "ip_address": "192.168.4.28",
  "room": "102",
  "username": "admin",
  "password": "your-secret",
  "rtsp_url": "rtsp://192.168.4.28/stream1",
  "is_active": true
}'
```

Passwords are stored **encrypted**; responses expose **`has_password`**, never the secret.

```bash
curl -s "$API/cameras?room=102&active_only=true"
```

### Option B — Command line

```bash
cd backend
python scripts/upsert_camera001.py
# or merge only cameras into an existing DB:
python scripts/add_sample_camera_to_existing_db.py --db data/crowdmuse.sqlite3
```

Test RTSP locally:

```bash
python scripts/test_rtsp_camera_preview.py --rtsp 'rtsp://USER:PASS@192.168.4.28/stream1' --no-display --frames 30
```

---

## 4. Students

### Option A — REST API

```bash
curl -s -X POST "$API/students" -H "Content-Type: application/json" -d '{
  "roll_number": "98104ME102",
  "name": "Asha Menon",
  "stream_id": 1,
  "batch_year": 2025
}'
```

`409` means the roll already exists; use **`GET /students`** to confirm.

### Option B — Command line

**`enroll_student.py`** creates the student via **`POST /students`** (and then writes face files locally):

```bash
cd backend
python enroll_student.py --roll-number 98104ME102 --name "Asha Menon" \
  --batch-year 2025 --stream "Mechanical Engineering" --camera 0
```

---

## 5. Face enrollment (required before face-based attendance)

Recognition uses **`backend/data/face_encodings/<roll_number>.json`**.

### Option A — REST API

Single image (**student must already exist**):

```bash
curl -s -X POST "$API/students/enrollment-image" \
  -F "roll_number=98104ME102" \
  -F "replace_encoding=true" \
  -F "image=@/path/to/face.jpg"
```

Multiple images: **`POST /students/enrollment-images`** with form field **`images`** repeated (see **`/docs`**).

### Option B — Command line

```bash
cd backend
python enroll_student.py --roll-number 98104ME102 --name "Asha Menon" \
  --batch-year 2025 --stream "Mechanical Engineering" --photo path/to/face.jpg

# Or webcam → API
python scripts/capture_and_upload_enrollment.py \
  --roll-number 98104ME102 --api-url http://127.0.0.1:8000
```

If you only add files with **`enroll_student.py`** on disk and not via **`POST /students/enrollment-image`**, **restart Uvicorn** so the API’s face service reloads encodings from disk.

---

## 6. Mark attendance

### Scheduled (uses timetable + cohort)

**Roll + room** (no image):

```bash
curl -s -X POST "$API/attendance/mark-scheduled" -H "Content-Type: application/json" -d '{
  "roll_number": "98104ME102",
  "room": "102"
}'
```

**Face + room** (multipart; requires encodings for that roll):

```bash
curl -s -X POST "$API/attendance/mark-by-face-scheduled" \
  -F "room=102" \
  -F "image=@/path/to/face.jpg"
```

Optional **`camera_id`** must match an active **`cameras`** row for that **room** (see **`/docs`** field descriptions).

### Command line (continuous camera)

Timetable-driven client (USB example):

```bash
cd backend
python mark_attendance.py --room 102 --camera 0 --api-url http://127.0.0.1:8000
```

RTSP from DB for room **102**:

```bash
python scripts/room_camera_attendance.py --room 102 --api-url http://127.0.0.1:8000
```

Stop with **Ctrl+C**. These scripts call **`GET /timetable/active`** and **`POST /attendance/mark-by-face-scheduled`** when a class is in session.

### Manual class name (no timetable check)

**`POST /attendance/mark`** — supplies **`class_name`** yourself; **`date_key`** is server **today**. Prefer scheduled endpoints for real classrooms.

---

## 7. Query attendance

```bash
curl -s "$API/attendance?room=102"
curl -s "$API/attendance?room=102&date_key=2026-04-11"
curl -s "$API/attendance/by-room/102"
```

---

## 8. Copy-paste sequences

### A — Mostly API (curl)

Assumes **`stream_id` `1`** exists or you create it first.

1. `POST /streams` (if needed) → `GET /streams` for **`id`**
2. `POST /timetable/slots` with matching **`stream_id`**, **`batch_year`**, **`room`**, and a **`day_of_week` / time** that includes **now** (or test at the right time)
3. `POST /cameras` (optional)
4. `POST /students`
5. `POST /students/enrollment-image` (or enroll via script)
6. `GET /timetable/active?room=…` → should show **`active": true`** when testing
7. `POST /attendance/mark-scheduled` or `…/mark-by-face-scheduled`
8. `GET /attendance?room=…`

### B — Mostly command line (scripts)

1. `python scripts/room102_sample_data.py` — stream, student **`98104ME102`**, Mon–Fri slots in **`102`**
2. `python scripts/upsert_camera001.py` (optional)
3. `python enroll_student.py … --photo …` **or** `python scripts/capture_and_upload_enrollment.py --roll-number 98104ME102 --api-url http://127.0.0.1:8000`
4. With API running: `python scripts/room_camera_attendance.py --room 102` **or** `python mark_attendance.py --room 102 --camera 0`
5. `curl "$API/attendance?room=102"` to verify rows

---

## Troubleshooting

- **`400` / `403` on scheduled marks:** No active slot for **room** at **server now**, or student **stream/batch** does not match the slot (**cohort**). Fix timetable or test time; check **`GET /timetable/active?room=…`**.
- **`404` on face mark:** Missing **`data/face_encodings/<roll>.json`** or face not recognized—re-enroll, improve lighting, or use **`--preview`** on **`capture_and_upload_enrollment.py`**.
- **Wrong SQLite file:** API defaults to **`data/crowdmuse.sqlite3`**. Scripts accept **`--db`**—use the same file the API uses.
- More: **`how_to_run_demo.md`** (Troubleshooting section).
