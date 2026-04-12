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

   Enroll example (adjust paths and stream name as needed):

   ```bash
   cd backend
   python enroll_student.py --roll-number 98104ME003 --name "Vikram Singh" --batch-year 2025 \
     --stream "Mechanical Engineering" --photo path/to/photo.jpg
   ```

4. **Optional sample data:** `python scripts/seed_sample_db.py --force` creates **`data/sample_crowdmuse.sqlite3`**. The running API uses **`data/crowdmuse.sqlite3`** by default (`app/db.py`), so seed data does **not** apply unless you point the app at the sample file. The demo scripts **create rows via the API**, so an empty default DB is fine.

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

## Related

- **`how_to_run_tests.md`** — pytest; **`scripts/run_api_and_tests.sh`** starts Uvicorn then runs tests.
- **`what_all_tables.md`** — schema, cohort rules, and endpoint summary.
