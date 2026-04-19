# How to run demos

These scripts live under **`backend/scripts/`**. They talk to a **running** FastAPI process over HTTP (`requests`). Run them from **`backend/`** with dependencies installed (`pip install -r requirements.txt`) and a virtual environment active if you use one.

## Prerequisites

1. **Start the API** (in a separate terminal):

   ```bash
   cd backend
   python -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
   ```

2. **Health check:** [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health) (or open `/docs` for Swagger).

3. **Face demos** need a matching encoding file:

   - Path: **`backend/data/face_encodings/<roll_number>.json`**
   - The stem must match **`students.roll_number`** in the database.

   Enroll examples (API must be running; **`enroll_student.py`** creates the student if missing, or continues if the roll already exists — e.g. sample **`98104ME102`**):

   ```bash
   cd backend
   # From a JPG on disk
   python enroll_student.py --roll-number 98104ME102 --name "Asha Menon (Room 102 demo)" \
     --batch-year 2025 --stream "Mechanical Engineering" --photo path/to/your_face.jpg

   # From your network camera (full RTSP URL with credentials — same as OpenCV would use)
   python enroll_student.py --roll-number 98104ME102 --name "Asha Menon (Room 102 demo)" \
     --batch-year 2025 --stream "Mechanical Engineering" --rtsp 'rtsp://USER:PASS@192.168.4.28/stream1'

   # USB webcam
   python enroll_student.py --roll-number 98104ME003 --name "Vikram Singh" --batch-year 2025 \
     --stream "Mechanical Engineering" --camera 0
   ```

   **After the student exists** (you enrolled without a face, or you want a new reference photo), capture from the laptop webcam and upload via **`POST /students/enrollment-image`**:

   ```bash
   cd backend
   python scripts/capture_and_upload_enrollment.py --roll-number 98104ME102 --api-url http://127.0.0.1:8000
   ```

   The roll must match an existing **`students.roll_number`**. For a live picker (or if **`--camera 0`** is the wrong device on macOS), use **`--preview`**; optional **`--camera 1`**, **`--warmup N`**. Multi-file uploads: **`POST /students/enrollment-images`** in **`/docs`**.

   This writes **`data/face_encodings/<roll_number>.json`** (used for matching) and, by default, **`data/face_encodings/<roll_number>.jpg`** (cropped face, resized for a clear reference — use **`--no-save-jpeg`** to skip the image). Only **`*.json`** files are loaded as encodings.

4. **Optional sample data:** `python scripts/seed_sample_db.py --force` creates **`data/sample_crowdmuse.sqlite3`**. If that file **already exists** and you only need the **`cameras`** table plus the sample **`camera001`** row (no full reseed), run **`python scripts/add_sample_camera_to_existing_db.py`** (defaults to the sample DB path). The running API uses **`data/crowdmuse.sqlite3`** by default (`app/db.py`); use **`--db data/crowdmuse.sqlite3`** on that script to patch the live file instead.

5. **Room 102 sample timetable:** **`scripts/seed_sample_db.py`** also adds student **`98104ME102`** (ME 2025) and five **`class_schedule`** rows in room **`102`** (Mon–Fri 09:00–10:00) so that student is cohort-eligible for **every** class in that room. To add the same rows into an existing DB without wiping it: **`python scripts/room102_sample_data.py`** (default **`data/crowdmuse.sqlite3`**). Enroll a face for **`98104ME102`** before testing **`room_camera_attendance.py`**.

For table relationships and endpoints, see **`what_all_tables.md`**.

---

## Demo 1: `demo_face_scheduled_e2e.py`

**Purpose:** Exercise **`POST /attendance/mark-by-face-scheduled`** — upload a face image + room; the server picks the active timetable slot and checks cohort.

**Typical flow with auto-setup** (creates stream, student, and a slot that **includes server local “now”**):

```bash
cd backend
# optional: source ../.cmuse/bin/activate

python scripts/demo_face_scheduled_e2e.py --setup --image ~/Pictures/your_face.jpg --room DemoRoom
```

- **`--setup`:** Ensures “Mechanical Engineering”, student **`98104ME003`** (default), and a **`class_schedule`** row for **today’s weekday** with a window from **`now - minutes_back`** to **`now + minutes_forward`** (defaults: 10 minutes ago → 2 hours ahead).
- **`--image`:** Required; JPEG/PNG of the person whose encoding exists under **`data/face_encodings/`** (default roll **`98104ME003`**).
- **`--room`:** Must match the timetable row (default **`DemoRoom`**).

Useful options:

- **`--api-url`** — default `http://127.0.0.1:8000`
- **`--roll`**, **`--student-name`**, **`--stream-name`**, **`--batch-year`** — must align with the encoding file and slot cohort
- **`--class-name`**, **`--course-code`**, **`--minutes-back`**, **`--minutes-forward`** — slot content and width

Without **`--setup`**, you must already have an active slot: **same room**, **server local weekday**, time inside **`[start_time, end_time)`**, and **stream + batch_year** matching the student.

**Inspect active slot:**

```bash
curl -s "http://127.0.0.1:8000/timetable/active?room=DemoRoom"
```

---

## Demo 2: `demo_saturday_physics_vikram.py`

**Purpose:** Fixed story — **Vikram Singh** (`98104ME003`), **Mechanical Engineering**, batch **2025**, **Saturday 19:00–20:00**, room **`PhysicsLab`**, class **Physics** (`PHY101`). The script ensures stream, student, and that timetable row exist via the API, then marks attendance depending on **whether that slot is active on the server clock**.

```bash
cd backend
python scripts/demo_saturday_physics_vikram.py
python scripts/demo_saturday_physics_vikram.py --api-url http://127.0.0.1:8000
```

**Behavior:**

| Server state | Flags | What runs |
|--------------|--------|-----------|
| Slot active (Sat 19:00–20:00, `PhysicsLab`) | no `--image` | **`POST /attendance/mark-scheduled`** (roll + room) |
| Same + `--image path.jpg` | | **`POST /attendance/mark-by-face-scheduled`** (needs encoding) |
| Slot **not** active | `--force-mark` | **`POST /attendance/mark`** with client-supplied class name (bypasses timetable; dev only) |
| Slot not active | (none) | Prints help text and exits **0** without marking |

**`date_key` / timetable:** For **`mark-scheduled`** and **`mark-by-face-scheduled`**, the API uses one **server-local instant** for both “which slot” and **`date_key`** (calendar date of that instant). For **`mark`**, **`date_key`** is server **`date.today()`** when the handler runs.

The script prints a **client** clock banner so you can compare with the machine running **uvicorn** (they must agree for “is it Saturday 19:00?” to match).

---

## Troubleshooting

- **`404` on `/attendance/mark-scheduled`:** Restart the API so it loads the current `app/main.py` (use **`--reload`** in development).
- **`403` / `400` on scheduled marks:** Cohort mismatch (student **stream_id** / **batch_year** vs slot) or no row for **room + weekday + time**.
- **Face mark fails:** Missing or wrong **`data/face_encodings/<roll>.json`**, or image does not match the enrolled face.

---

## Network camera `camera001` (room 102)

Default demo row: IP **`192.168.4.28`**, room **`102`**, RTSP path **`rtsp://192.168.4.28/stream1`** (no password in URL string), username/password stored with **password encrypted** in SQLite.

- Set **`CROWDMUSE_CAMERA_KEY`** in production (any strong string; used to derive the Fernet key). Tests set a fixed key in `conftest.py`.
- **`GET /cameras`** returns **`has_password`** but **never** the plaintext password.

1. **Insert into the live API database** (`data/crowdmuse.sqlite3`) — API can be stopped:

   ```bash
   cd backend
   python scripts/upsert_camera001.py
   ```

   The script prints **`effective_rtsp_url`** (with credentials) for **local use only**. Or use **`POST /cameras`** with `username` / `password` in JSON (stored encrypted).

2. **Sample-only DB** (`seed_sample_db.py`) also inserts this camera into **`data/sample_crowdmuse.sqlite3`**.

3. **Preview the RTSP feed** — use a URL that works on your LAN (from `upsert` output or built manually):

   ```bash
   cd backend
   python scripts/test_rtsp_camera_preview.py --rtsp 'rtsp://USER:PASS@192.168.4.28/stream1' --no-display --frames 45
   ```

4. **Attendance client** — **`scripts/room_camera_attendance.py`** reads **`cameras`** from SQLite (RTSP + encrypted password), then runs the same loop as **`mark_attendance.py`** (face → **`mark-by-face-scheduled`** when the timetable has an active class for that room). Example: `python scripts/room_camera_attendance.py --room 102`.

   Alternatively, call **`mark_attendance.py`** yourself with **`--room`**, **`--rtsp`**, and **`--camera-id`**.

---

## Related

- **`end_to_end_complete_guide.md`** — end-to-end setup: **streams, timetable slots, cameras, students, face upload, marking attendance** with **`curl`/Swagger** and **shell scripts** side by side.
- **`end_to_end_flow.md`** — narrative: create student → add face → timetable → run **`mark_attendance.py`** / **`room_camera_attendance.py`** with the API up.
- **`how_to_run_tests.md`** — pytest; **`scripts/run_api_and_tests.sh`** starts Uvicorn then runs tests.
- **`what_all_tables.md`** — schema, cohort rules, and endpoint summary.
