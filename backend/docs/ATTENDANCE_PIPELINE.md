# CrowdMuse Attendance Pipeline – Design & Implementation

This document describes the attendance pipeline we built: **why** we chose a hybrid, frame-based approach, **what** it does, and **how** the team can run and tune it.

---

## 1. Goal

- **Input:** Video from a classroom camera (e.g. Tapo C200) over RTSP.
- **Output:** Mark student attendance when a face is recognized **and** the student is enrolled in the class that is **scheduled in that room at the current server time**.
- **Constraint:** Do this reliably without overloading the machine or the RTSP stream.

### Timetable + enrollment (server)

- **`class_schedule`**: recurring weekly rows — `room`, `day_of_week` (0=Mon…6=Sun), `start_time` / `end_time` (e.g. `09:00`–`10:00`), `class_name` (e.g. `Social Studies - s103`).
- **`enrollments`**: links `student_id` ↔ `class_schedule_id` (who is allowed in that slot).
- **`POST /attendance/mark-by-face-scheduled`**: image + `room` only → server finds active slot from **local time**, checks enrollment, then marks with that slot’s `class_name`.
- **`GET /timetable/active?room=...`**: debug which slot is active now.
- The **hybrid** `mark_attendance.py` polls `timetable/active` and calls `mark-by-face-scheduled` when a class is in session (no `class_name` on the wire from the client).

---

## 2. Why Not “Live Video” Only?

A naive approach is: read each frame, run face recognition on it, and mark attendance.

Problems:

1. **RTSP buffer overflow**  
   The stream delivers frames at a fixed rate (e.g. 25 fps). If we process every frame (detect + encode + match), we read slower than the stream. The RTSP buffer fills → lag, freezes, or dropped connection.

2. **Flaky matching**  
   Doing recognition on every live frame is noisy: lighting, angle, and motion change every frame. Matching directly “live frame vs passport photo” is less reliable than “one good crop vs passport photo.”

3. **Where to match?**  
   If we match on the client, we need all passport encodings on the client and must keep them in sync. If we match on the server, we need to send something from the client—either the **image** (frame-based) or an **encoding**. Sending a **single good face crop** and matching on the server is more accurate and keeps one source of truth (passport encodings) on the server.

So we moved to: **frame-based flow** (extract frames → detect face → crop → send image to server → server matches against DB/passport encodings).

---

## 3. Frame-Based vs “Video Encodings”

We considered:

| Approach | Description | Accuracy | Notes |
|----------|-------------|----------|--------|
| **Frame-based** | Send a **cropped face image** from a frame to the server; server encodes it and matches against passport encodings. | **Better** | Same “photo vs photo” pipeline on server; one clear crop per attempt. |
| **Video encodings** | Encode the face on the client from live frames, compare locally (or send encoding), then send roll_number to API. | Weaker | Each frame is different; encoding is noisier; passport vs live is a harder match. |

**Conclusion:** For accuracy with passport photos in the DB, **frame-based** is better: discrete frames, one crop per attempt, server does encoding + matching with the same pipeline used for passport photos.

---

## 4. Hybrid Pipeline (What We Implemented)

We use a **hybrid** design so that:

- The RTSP stream never stalls (threading).
- We don’t process every frame (sampling).
- We don’t run heavy work on full resolution (downscale for detection, full-res crop for API).

### 4.1 Three Ideas

1. **Threading (decoupling)**  
   - **Grabber thread:** Only reads from the RTSP stream and stores the “latest” frame.  
   - **Main/worker thread:** Takes frames when ready, runs face detection, crops, and sends to the API.  
   So the stream is always being read (buffer drained), while processing runs at its own, slower pace.

2. **Strategic sampling**  
   We don’t analyse every frame. For attendance, processing **1 in every 5–10 frames** is enough to see everyone, and we add a **cooldown** so we don’t mark the same person repeatedly.  
   Configurable via `--sample-every` (default: 8).

3. **Preprocessing (downscale)**  
   Before face detection we **downscale** the frame (e.g. to 640×360). Detection runs on this smaller image; when we find a face we map the box back to the **original resolution** and crop from the full-res frame for the API.  
   So: fast detection on small image, high-quality crop for matching.  
   Configurable via `--scale-width` (default: 640).

### 4.2 End-to-End Flow

```
┌─────────────────────────────────────────────────────────────────────────┐
│  RTSP stream (e.g. Tapo C200)                                            │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  GRABBER THREAD                                                          │
│  • Continuously cap.read()                                               │
│  • Store latest frame in shared variable (with lock)                     │
│  • On many read failures → reconnect RTSP                                │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  MAIN / WORKER THREAD                                                    │
│  • Every Nth frame (sample_every):                                       │
│    1. Copy latest frame → downscale (e.g. 640×360)                       │
│    2. Face detection on downscaled frame (face_locations)                │
│    3. For each face:                                                     │
│       - Map bbox back to full resolution                                 │
│       - Crop face with padding (full-res) → encode JPEG                  │
│       - POST to API /attendance/mark-by-face                             │
│    4. Position cooldown: don’t re-send same face area for 10s            │
└──────────────────────────────┬──────────────────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────────────────┐
│  BACKEND API                                                             │
│  • Receives image (multipart form)                                       │
│  • Encodes face from image bytes                                         │
│  • Compares to stored encodings (from passport photos)                   │
│  • If match → mark attendance (idempotent per student/day/room/class)   │
│  • Returns 200 + attendance record or 404                                 │
└─────────────────────────────────────────────────────────────────────────┘
```

### 4.3 Cooldown

- **By position:** We round each face’s centre to a grid (e.g. 50 px). If we already sent a crop from that grid cell in the last 10 seconds, we skip (avoids spamming the same person).
- **By roll (server):** The mark endpoint is idempotent: same student, same day, same room/class → one record. Duplicate requests just return the existing record.

### 4.4 Person passing through (e.g. entering the room in ~5 seconds)

When someone walks past the camera and is only in view for a few seconds:

- The **grabber** keeps reading frames; the **worker** still processes every **Nth** frame (e.g. every 8th). So in 5 seconds at 25 fps you get on the order of **15 sampled frames** where the person might be visible.
- On each sampled frame we run face detection. The **first time** we see a face we send that crop to the server. If the server matches (passport encodings), attendance is marked. One successful send is enough.
- **Position cooldown** applies per grid cell (50 px). As the person moves, their face centre moves to different cells, so we might send again from a “new” cell. The server is **idempotent**, so we still only get one attendance record. The cooldown mainly stops us from sending many times from the *same* spot.
- So in practice: we get **multiple chances** (several sampled frames) while they’re in view; we only need **one** good detection and one successful API match to mark them. If people cross very quickly, you can use a **smaller** `--sample-every` (e.g. 5) so more frames are processed and there are more chances to catch them.

---

## 5. Modes in the Script

The script `mark_attendance.py` supports three ways to run:

| Mode | When | Description |
|------|------|-------------|
| **Hybrid** | `--rtsp <URL>` (default for RTSP) | Grabber thread, sample every N frames, downscale, send crops to `/attendance/mark-by-face`. No local encodings. |
| **RTSP + Live** | `--rtsp <URL>` **and** `--rtsp-live` | Same RTSP stream but **single thread**, minimal buffer, **local encodings** in `data/face_encodings`, mark by roll via JSON API. Use to compare performance/reliability vs hybrid. |
| **Live (camera)** | No `--rtsp` (e.g. built-in webcam `--camera 0`) | Single thread, local encodings, mark by roll. |

### Comparing hybrid vs RTSP-live

To compare the two approaches on the **same** Tapo RTSP feed:

- **Hybrid (recommended):**  
  `python mark_attendance.py --rtsp "rtsp://..." --room "Room512" --class "Class1"`
- **RTSP + live (comparison):**  
  `python mark_attendance.py --rtsp "rtsp://..." --rtsp-live --room "Room512" --class "Class1"`  
  Requires encodings in `data/face_encodings`. Uses a single thread and minimal RTSP buffer (no grabber, no sampling, no downscale). You can then compare lag, recognition rate, and stability.

### Tapo / RTSP-only cameras

**Tapo C200 (and similar) only expose video over RTSP.** There is no “direct” camera device for Tapo. So:

- **To use Tapo:** you always pass `--rtsp "rtsp://..."`. The script then uses the **hybrid** pipeline (grabber thread, sampling, downscale, send crop to server). You do **not** need encodings in `data/face_encodings` on the machine running the script; matching is done on the server from passport encodings.
- **“Live” mode** (single thread, local encodings) is only used when you **do not** pass `--rtsp`—e.g. when using the machine’s built-in webcam or a USB camera with `--camera 0`.

So: **camera feed over RTSP = use `--rtsp` = hybrid pipeline.** There is no separate “RTSP in live mode”; if the source is RTSP, you use `--rtsp` and get hybrid.

---

## 6. How to Test: RTSP Hybrid vs RTSP Live

Use the **same RTSP URL** and **same room/class** to compare both modes. Run from the `backend` directory; ensure the API is running (`uvicorn app.main:app --reload --port 8000`).

### RTSP Hybrid (default)

- Grabber thread, sampling, downscale, send crop to server.
- **No** local encodings needed on this machine (matching on server).

```bash
cd backend

python mark_attendance.py \
  --rtsp "rtsp://192.168.4.21/strea1" \
  --room "Room512" \
  --class "Class1"
```

Optional: `--sample-every 5` `--scale-width 640` `--no-display`

### RTSP Live (comparison)

- Single thread, minimal buffer, **local** face recognition.
- **Requires** encodings in `data/face_encodings/` (e.g. from `enroll_student.py`).

```bash
cd backend

python mark_attendance.py \
  --rtsp "rtsp://192.168.4.21/strea1" \
  --rtsp-live \
  --room "Room512" \
  --class "Class1" \
  --auto-mark
```

Optional: omit `--auto-mark` and press **m** to mark when a face is recognized.

### Quick reference

| What you want        | Example args |
|----------------------|--------------|
| **RTSP hybrid**      | `--rtsp "rtsp://192.168.4.21/strea1" --room "Room512" --class "Class1"` |
| **RTSP live**       | `--rtsp "rtsp://192.168.4.21/strea1" --rtsp-live --room "Room512" --class "Class1" --auto-mark` |

Replace `rtsp://192.168.4.21/strea1` with your Tapo RTSP URL, and `Room512` / `Class1` with your room and class names.

---

## 7. Passport Photos and Encodings

- **Enrollment:** Students can be enrolled with a **passport-size photo** (e.g. `enroll_student.py --photo path/to/photo.jpg`). The server (or enrollment script) produces a **face encoding** and stores it under `data/face_encodings/<roll_number>.json`.
- **Matching:** When the API receives a face image (crop from the stream), it encodes that image and compares it to all stored encodings. If the distance is below a **tolerance** (default 0.6), we treat it as a match and mark attendance.
- **Same pipeline:** Passport photos and uploaded crops are encoded the same way on the server, which keeps “photo vs photo” matching consistent and accurate.

---

## 8. How the Team Runs It

### 8.1 Prerequisites

- Backend API running (with DB and face encodings):  
  `uvicorn app.main:app --reload --port 8000`
- Students enrolled (passport photo or camera) so `data/face_encodings/` has `.json` files.
- RTSP URL for the camera (e.g. Tapo C200: `rtsp://...`).

### 8.2 Hybrid (RTSP) – use this for Tapo C200

Tapo and similar IP cameras only provide video over RTSP. Always use `--rtsp`; that runs the hybrid pipeline (no local encodings needed).

```bash
# Default: sample every 8, scale width 640
python mark_attendance.py --rtsp "rtsp://192.168.4.21/strea1" --room "Room512" --class "Class1"

# Tune: process every 5th frame
python mark_attendance.py --rtsp "rtsp://192.168.4.21/strea1" --room "Room512" --class "Class1" --sample-every 5

# Tune: different resolution for detection
python mark_attendance.py --rtsp "rtsp://..." --room "Room512" --class "Class1" --scale-width 640

# No preview window (e.g. server/headless)
python mark_attendance.py --rtsp "rtsp://..." --room "Room512" --class "Class1" --no-display
```

### 8.3 RTSP + live (compare with hybrid)

Same RTSP URL as hybrid but single-thread, local encodings, minimal buffer. Needs encodings in `data/face_encodings`.

```bash
python mark_attendance.py --rtsp "rtsp://192.168.4.21/strea1" --rtsp-live --room "Room512" --class "Class1" [--auto-mark]
```

### 8.4 Live mode (built-in or USB camera only, not RTSP)

Only when you are **not** using RTSP (e.g. laptop webcam or USB camera). Tapo cannot be used in this mode.

```bash
# Needs encodings in data/face_encodings
python mark_attendance.py --room "Room512" --class "Class1" --camera 0 [--auto-mark]
```

### 8.5 What `--auto-mark` does (live only)

`--auto-mark` only applies in **live** mode (RTSP + `--rtsp-live`, or camera with `--camera`). It does **not** exist in the hybrid pipeline.

| Mode    | Marking behaviour |
|---------|-------------------|
| **Hybrid** | Always automatic. Every sampled frame we detect faces, send crops to the server; when the server matches a face it marks attendance. No “press m”. Throttle is by **position cooldown** (same face area not re-sent for 10 s). |
| **Live (without `--auto-mark`)** | Manual. When a face is recognized you must press **m** to mark attendance. |
| **Live (with `--auto-mark`)** | Automatic. When a face is recognized we call the API to mark immediately, with a **per-roll cooldown** (same person not marked again for 10 s). |

So: in **hybrid** there is no `--auto-mark` flag — marking is always driven by sending face crops and server matches. In **live**, use `--auto-mark` if you want marking to happen without pressing m.

---

## 9. Main Files

| File / Path | Role |
|-------------|------|
| `mark_attendance.py` | Entrypoint; hybrid (grabber + worker + sampling + downscale) and live mode. |
| `app/main.py` | FastAPI app; `POST /attendance/mark-by-face` accepts image, encodes, matches, marks. |
| `app/face_recognition_service.py` | Loads encodings, encodes from image bytes/frame, compares (e.g. `recognize_face_from_image_bytes`). |
| `data/face_encodings/*.json` | Stored encodings (from passport/camera enrollment). |
| `backend/README_MARK_ATTENDANCE.md` | Detailed run/debug guide for the script. |

---

## 10. Summary for the Team

- We use a **frame-based** flow: **frames → detect face → crop → send image to server → server matches to passport encodings and marks attendance.**
- For RTSP (e.g. Tapo C200) we use a **hybrid pipeline**: **grabber thread** (keeps stream healthy), **sample every N frames**, **downscale for detection**, **full-res crop for API**, and **position cooldown** to avoid duplicate sends.
- This gives better accuracy and stability than “live video encoding” alone and avoids RTSP buffer and overload issues. Passport photos stay the single source of truth on the server.

For step-by-step running and debugging, see **README_MARK_ATTENDANCE.md** in the backend folder.
