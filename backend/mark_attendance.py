#!/usr/bin/env python3
"""
Timetable-driven attendance (continuous camera).

The camera runs continuously (CCTV-style). Face detection and recognition always run.
Attendance is marked only when the current time falls within a scheduled class for
the configured room. Each student is marked at most once per class session; session
state resets when the active schedule slot changes.

Modes:
- Hybrid (RTSP): grabber thread + sampled face crops; mark-by-face API when active.
- Live: local encodings + mark-by-roll API when active.

Stop with Ctrl+C (no attendance keypress required).
"""
from __future__ import annotations

import argparse
import sys
import threading
import time
from pathlib import Path
from typing import Optional

import cv2
import face_recognition
import requests
from datetime import datetime
from app.db import session_scope
from app.models import ClassSchedule


# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent))

from app.face_recognition_service import FaceRecognitionService

# RTSP
RTSP_RECONNECT_AFTER_FAILURES = 30
RTSP_RECONNECT_DELAY_SEC = 2.0
# Cooldown: don't hit mark API for same face position too often (hybrid grid)
AUTO_MARK_COOLDOWN_SEC = 10.0
# Re-query DB for active class on this interval (seconds)
SCHEDULE_POLL_SEC = 3.0
# Hybrid: padding around face crop before sending to API
FACE_CROP_PADDING = 0.25
# Hybrid: default process every N frames and downscale size
DEFAULT_SAMPLE_EVERY = 8
DEFAULT_SCALE_WIDTH = 640

from datetime import datetime

def get_attendance_status(schedule):
    now = datetime.now()
    start = datetime.strptime(schedule.start_time, "%H:%M")

    # handle case where current time is before class start
    diff_minutes = (now - start).total_seconds() / 60

    if diff_minutes < 0:
        return None  # don't mark attendance before class starts

    if diff_minutes <= schedule.attendance_window:
        return "present"
    elif diff_minutes <= schedule.late_window:
        return "late"
    else:
        return "absent"


def session_key_for(schedule: Optional[ClassSchedule]) -> Optional[tuple]:
    """One mark per student per schedule row per calendar day."""
    if schedule is None:
        return None
    return (schedule.id, datetime.now().date().isoformat())


def draw_system_status_overlay(
    frame_bgr,
    attendance_active: bool,
    class_label: str,
) -> None:
    """Banner at top: attendance state and current class (if any)."""
    h, w = frame_bgr.shape[:2]
    bar_h = min(56, max(40, h // 14))
    cv2.rectangle(frame_bgr, (0, 0), (w, bar_h), (32, 32, 32), -1)
    state = "ATTENDANCE: ACTIVE" if attendance_active else "ATTENDANCE: INACTIVE"
    color = (0, 220, 0) if attendance_active else (160, 160, 160)
    cv2.putText(
        frame_bgr,
        state,
        (8, bar_h // 2 + 2),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.55,
        color,
        2,
    )
    sub = class_label if class_label else ("No class in session" if not attendance_active else "")
    cv2.putText(
        frame_bgr,
        sub[:80],
        (8, bar_h - 6),
        cv2.FONT_HERSHEY_SIMPLEX,
        0.45,
        (210, 210, 210),
        1,
    )


def mark_attendance_via_api(
    roll_number: str,
    room: str,
    class_name: str,
    api_url: str = "http://localhost:8000",
    lat: str = None,
    lng: str = None,
    schedule: Optional[ClassSchedule] = None,
):
    """Mark attendance by roll_number (JSON API). Returns (success, roll_number)."""
    if schedule is None:
        schedule = get_active_schedule(room)
    if schedule is None:
        print("❌ No active class schedule for this room.")
        return False, None
    url = f"{api_url}/attendance/mark"
    status = get_attendance_status(schedule)

    if status is None:
        return False, None

    payload = {
    "roll_number": roll_number,
    "room": room,
    "class_name": class_name,
    "status": status,
    }

    if lat:
        payload["lat"] = lat
    if lng:
        payload["lng"] = lng
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        print(f"✅ Marked: {data.get('student_name')} ({data.get('student_roll')})")
        return True, data.get("student_roll")
    except requests.exceptions.RequestException as e:
        err = getattr(e, "response", None)
        text = err.text if err else str(e)
        print(f"❌ Error: {text}")
        return False, None


def mark_attendance_by_face_image(
    image_bytes: bytes,
    room: str,
    class_name: str,
    api_url: str = "http://localhost:8000",
    tolerance: float = 0.6,
    lat: str = None,
    lng: str = None,
):
    """
    Send a single face image to the API. Server matches against passport encodings.
    Returns (success, roll_number or None).
    """
    url = f"{api_url}/attendance/mark-by-face"
    data = {
        "room": room,
        "class_name": class_name,
        "tolerance": tolerance,
    }
    if lat:
        data["lat"] = lat
    if lng:
        data["lng"] = lng
    files = {"image": ("face.jpg", image_bytes, "image/jpeg")}
    try:
        response = requests.post(url, data=data, files=files)
        if response.status_code == 404:
            return False, None
        response.raise_for_status()
        out = response.json()
        roll = out.get("student_roll")
        print(f"✅ Marked: {out.get('student_name')} ({roll})")
        return True, roll
    except requests.exceptions.RequestException as e:
        err = getattr(e, "response", None)
        text = err.text if err else str(e)
        print(f"❌ API: {text}")
        return False, None


def open_video_source(rtsp_url=None, camera_index=0):
    """Open VideoCapture from RTSP URL or camera index. For RTSP, set small buffer."""
    if rtsp_url:
        cap = cv2.VideoCapture(rtsp_url, cv2.CAP_FFMPEG)
        if cap.isOpened():
            try:
                cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
            except Exception:
                pass
        return cap
    return cv2.VideoCapture(camera_index)


def crop_face_with_padding(frame_bgr, top, right, bottom, left, padding_frac=FACE_CROP_PADDING):
    """Return cropped BGR image with padding."""
    h, w = frame_bgr.shape[:2]
    hb, wb = bottom - top, right - left
    pad_y = int(hb * padding_frac)
    pad_x = int(wb * padding_frac)
    y1 = max(0, top - pad_y)
    y2 = min(h, bottom + pad_y)
    x1 = max(0, left - pad_x)
    x2 = min(w, right + pad_x)
    return frame_bgr[y1:y2, x1:x2]

def get_active_schedule(room: str) -> Optional[ClassSchedule]:
    """Return the schedule row whose time window contains now, or None."""
    now = datetime.now().strftime("%H:%M")
    try:
        with session_scope() as db:
            schedules = (
                db.query(ClassSchedule)
                .filter(ClassSchedule.room == room)
                .all()
            )
            for s in schedules:
                if s.start_time <= now <= s.end_time:
                    return s
    except Exception as e:
        print(f"Schedule query error (continuing): {e}")
    return None


def poll_schedule_state(
    room: str,
    last_poll_t: float,
    last_schedule: Optional[ClassSchedule],
    poll_interval: float,
) -> tuple[float, Optional[ClassSchedule], bool, str]:
    """
    Refresh active schedule from DB every `poll_interval` seconds.
    Returns (new_last_poll_t, schedule, attendance_active, status_subtitle).
    """
    t = time.monotonic()
    if last_poll_t > 0 and (t - last_poll_t) < poll_interval:
        sch = last_schedule
    else:
        sch = get_active_schedule(room)
        last_poll_t = t
    active = sch is not None
    if active:
        subtitle = f"Class: {sch.class_name} | {sch.start_time}-{sch.end_time} | {sch.room}"
    else:
        subtitle = "No class in session (monitoring)"
    return last_poll_t, sch, active, subtitle


def run_hybrid(
    rtsp_url: str,
    room: str,
    api_url: str,
    sample_every: int,
    scale_width: int,
    tolerance: float,
    lat: str,
    lng: str,
    show_window: bool,
    stop_event: threading.Event,
    schedule_poll_sec: float = SCHEDULE_POLL_SEC,
):
    """
    Hybrid pipeline: one thread grabs frames, main thread processes every Nth frame
    at reduced resolution. Face recognition always runs; mark-by-face only when a
    class is active for this room (from DB schedule).
    """
    latest_frame = None
    frame_lock = threading.Lock()
    read_failures = [0]  # list so grabber can mutate
    cap_ref = [None]  # so we can replace on reconnect

    def grabber():
        nonlocal cap_ref, latest_frame
        cap = open_video_source(rtsp_url=rtsp_url)
        cap_ref[0] = cap
        if not cap.isOpened():
            print(" Grabber: could not open RTSP stream")
            return
        while not stop_event.is_set():
            try:
                ret, frame = cap.read()
            except cv2.error:
                continue
            if not ret or frame is None:
                read_failures[0] += 1
                if read_failures[0] >= RTSP_RECONNECT_AFTER_FAILURES:
                    print("RTSP stream lost; reconnecting...")
                    cap.release()
                    time.sleep(RTSP_RECONNECT_DELAY_SEC)
                    cap = open_video_source(rtsp_url=rtsp_url)
                    if not cap.isOpened():
                        print(" Reconnect failed.")
                        return
                    cap_ref[0] = cap
                    read_failures[0] = 0
                else:
                    time.sleep(0.02)
                continue
            read_failures[0] = 0
            with frame_lock:
                latest_frame = frame.copy()

    t = threading.Thread(target=grabber, daemon=True)
    t.start()
    # Allow a few frames to fill
    time.sleep(0.5)

    already_marked: set[str] = set()
    last_session_key = None
    last_poll_t = 0.0
    cached_schedule: Optional[ClassSchedule] = None

    last_sent_positions = {}  # (gx, gy) -> time; cooldown by face position
    frame_count = 0
    scale_height = int(scale_width * 9 / 16)  # 640x360 default
    grid = 50  # pixels for position cooldown
    face_service = FaceRecognitionService()

    while not stop_event.is_set():
        with frame_lock:
            if latest_frame is None:
                time.sleep(0.05)
                continue
            work = latest_frame.copy()

        last_poll_t, cached_schedule, attendance_active, subtitle = poll_schedule_state(
            room, last_poll_t, cached_schedule, schedule_poll_sec
        )
        sk = session_key_for(cached_schedule)
        if sk != last_session_key:
            already_marked.clear()
            last_session_key = sk

        frame_count += 1
        if frame_count % sample_every != 0:
            if show_window:
                disp = cv2.resize(work, (scale_width, scale_height))
                draw_system_status_overlay(disp, attendance_active, subtitle)
                cv2.putText(
                    disp,
                    f"Hybrid | 1/{sample_every} | Ctrl+C to stop",
                    (8, scale_height - 8),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.45,
                    (0, 255, 255),
                    1,
                )
                cv2.imshow("Attendance (Hybrid)", disp)
                cv2.waitKey(1)

            else:
                time.sleep(0.02)
            continue

        # Downscale for detection
        small = cv2.resize(work, (scale_width, scale_height))
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        face_locations = face_recognition.face_locations(rgb)

        display_frame = small.copy()
        draw_system_status_overlay(display_frame, attendance_active, subtitle)
        now = time.time()
        last_sent_positions = {k: v for k, v in last_sent_positions.items() if now - v < AUTO_MARK_COOLDOWN_SEC}

        for (top, right, bottom, left) in face_locations:
            cx = (left + right) // 2
            cy = (top + bottom) // 2
            gx, gy = cx // grid * grid, cy // grid * grid
            if (gx, gy) in last_sent_positions:
                cv2.rectangle(display_frame, (left, top), (right, bottom), (128, 128, 128), 2)
                cv2.putText(display_frame, "Cooldown", (left, top - 8), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (128, 128, 128), 1)
                continue

            # Map back to full-res frame for a better crop to send
            sx = work.shape[1] / scale_width
            sy = work.shape[0] / scale_height
            t0, r0, b0, l0 = (
                int(top * sy),
                int(right * sx),
                int(bottom * sy),
                int(left * sx),
            )
            crop = crop_face_with_padding(work, t0, r0, b0, l0)
            if crop.size == 0:
                continue
            encoding = face_service.encode_face_from_frame(crop)
            result = None
            if encoding is not None:
                result = face_service.match_encoding(encoding, tolerance)
            if result:
                roll_number, confidence = result
                face_service.self_learn_from_recognition(roll_number, encoding, confidence)

            ok, roll = False, None
            if attendance_active and cached_schedule and result:
                roll_number, _conf = result
                if roll_number not in already_marked:
                    _, jpeg = cv2.imencode(".jpg", crop)
                    image_bytes = jpeg.tobytes()
                    ok, roll = mark_attendance_by_face_image(
                        image_bytes,
                        room,
                        cached_schedule.class_name,
                        api_url,
                        tolerance,
                        lat,
                        lng,
                    )
                    if ok and roll:
                        already_marked.add(roll)

            last_sent_positions[(gx, gy)] = time.time()

            if result:
                rn, _conf = result
                if not attendance_active:
                    tag, rect_c = "Recognized", (0, 200, 255)
                elif rn in already_marked:
                    tag, rect_c = "Marked", (0, 255, 0)
                elif ok and roll:
                    tag, rect_c = "Marked", (0, 255, 0)
                else:
                    tag, rect_c = "No match", (0, 0, 255)
            else:
                tag, rect_c = "No match", (0, 0, 255)

            cv2.rectangle(display_frame, (left, top), (right, bottom), rect_c, 2)
            cv2.putText(
                display_frame,
                tag,
                (left, max(top - 8, 60)),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                rect_c,
                1,
            )

        if not face_locations and display_frame is not None:
            cv2.putText(
                display_frame,
                "No face",
                (8, 70),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (128, 128, 128),
                2,
            )

        if show_window:
            cv2.putText(
                display_frame,
                f"1/{sample_every} | {scale_width}x{scale_height} | Ctrl+C to stop",
                (8, scale_height - 8),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.45,
                (0, 255, 255),
                1,
            )
            cv2.imshow("Attendance (Hybrid)", display_frame)
            cv2.waitKey(1)

        else:
            time.sleep(0.03)

    if cap_ref[0]:
        cap_ref[0].release()
    if show_window:
        cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(
        description="Timetable-driven attendance (continuous camera; stop with Ctrl+C)",
    )
    parser.add_argument("--room", type=str, required=True, help="Room number (e.g. Room512)")
    parser.add_argument(
        "--class",
        type=str,
        dest="class_name",
        default=None,
        help="Deprecated: ignored. Active class name comes from the database schedule.",
    )
    parser.add_argument(
        "--api-url",
        type=str,
        default="http://localhost:8000",
        help="API base URL",
    )
    parser.add_argument("--camera", type=int, default=0, help="Camera index when not using --rtsp")
    parser.add_argument(
        "--rtsp",
        type=str,
        default=None,
        help="RTSP URL (e.g. rtsp://192.168.4.21/strea1). By default enables hybrid pipeline.",
    )
    parser.add_argument(
        "--rtsp-live",
        action="store_true",
        help="Use RTSP with live pipeline: single thread, local encodings, minimal buffer.",
    )
    parser.add_argument(
        "--hybrid",
        action="store_true",
        help="Use hybrid pipeline (grabber thread + sample + downscale + mark-by-face). Default when --rtsp is set and not --rtsp-live.",
    )
    parser.add_argument(
        "--sample-every",
        type=int,
        default=DEFAULT_SAMPLE_EVERY,
        help=f"Process every Nth frame in hybrid mode (default {DEFAULT_SAMPLE_EVERY})",
    )
    parser.add_argument(
        "--scale-width",
        type=int,
        default=DEFAULT_SCALE_WIDTH,
        help=f"Width for downscaling in hybrid mode (default {DEFAULT_SCALE_WIDTH})",
    )
    parser.add_argument("--tolerance", type=float, default=0.6, help="Face match tolerance")
    parser.add_argument(
        "--schedule-poll-sec",
        type=float,
        default=SCHEDULE_POLL_SEC,
        help=f"How often to refresh active class from DB (default {SCHEDULE_POLL_SEC})",
    )
    parser.add_argument("--lat", type=str, default=None)
    parser.add_argument("--lng", type=str, default=None)
    parser.add_argument("--no-display", action="store_true", help="No preview window")

    args = parser.parse_args()

    # RTSP + no --rtsp-live → hybrid. RTSP + --rtsp-live → live (single thread, local encodings).
    use_hybrid = args.rtsp is not None and not args.rtsp_live
    show_window = not args.no_display

    if use_hybrid:
        if not args.rtsp:
            print("❌ Hybrid mode requires --rtsp URL.")
            return 1
        print(
            "Hybrid: continuous RTSP + sample 1/{} + downscale {}px | schedule poll {}s".format(
                args.sample_every, args.scale_width, args.schedule_poll_sec
            )
        )
        print("Room: {}  RTSP: {}  (class names from DB when active)".format(args.room, args.rtsp))
        print("Stop with Ctrl+C.\n")
        stop = threading.Event()
        try:
            run_hybrid(
                rtsp_url=args.rtsp,
                room=args.room,
                api_url=args.api_url,
                sample_every=args.sample_every,
                scale_width=args.scale_width,
                tolerance=args.tolerance,
                lat=args.lat,
                lng=args.lng,
                show_window=show_window,
                stop_event=stop,
                schedule_poll_sec=args.schedule_poll_sec,
            )
        except KeyboardInterrupt:
            stop.set()
        return 0

    # ---------- Live mode (single-thread, local recognition) ----------
    print("Loading face recognition service...")
    face_service = FaceRecognitionService()
    if not face_service._known_encodings:
        print("❌ No face encodings. Enroll students first (enroll_student.py).")
        return 1

    print("Timetable-driven live mode | room {} | schedule poll {}s".format(args.room, args.schedule_poll_sec))
    if args.rtsp:
        print("Source: RTSP {}".format(args.rtsp))
    else:
        print("Source: camera {}".format(args.camera))
    print("Recognition runs always; marking only during scheduled class. Stop with Ctrl+C.\n")

    cap = open_video_source(rtsp_url=args.rtsp, camera_index=args.camera)
    if not cap.isOpened():
        print("❌ Could not open source.")
        return 1

    read_failures = 0
    last_poll_t = 0.0
    cached_schedule: Optional[ClassSchedule] = None
    last_session_key = None
    already_marked: set[str] = set()

    try:
        while True:
            ret, frame = cap.read()
            if not ret or frame is None:
                read_failures += 1
                if args.rtsp and read_failures >= RTSP_RECONNECT_AFTER_FAILURES:
                    cap.release()
                    time.sleep(RTSP_RECONNECT_DELAY_SEC)
                    cap = open_video_source(rtsp_url=args.rtsp, camera_index=args.camera)
                    if not cap.isOpened():
                        time.sleep(1.0)
                        continue
                    read_failures = 0
                else:
                    time.sleep(0.05)
                continue
            read_failures = 0

            last_poll_t, cached_schedule, attendance_active, subtitle = poll_schedule_state(
                args.room, last_poll_t, cached_schedule, args.schedule_poll_sec
            )
            sk = session_key_for(cached_schedule)
            if sk != last_session_key:
                already_marked.clear()
                last_session_key = sk

            display_frame = frame.copy()
            draw_system_status_overlay(display_frame, attendance_active, subtitle)

            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            face_locations = face_recognition.face_locations(rgb)
            encoding = face_service.encode_face_from_frame(frame)
            result = (
                face_service.match_encoding(encoding, args.tolerance)
                if encoding is not None
                else None
            )
            if result:
                roll_number, confidence = result
                if encoding is not None:
                    face_service.self_learn_from_recognition(roll_number, encoding, confidence)

                if attendance_active and cached_schedule:
                    cn = cached_schedule.class_name
                    if roll_number not in already_marked:
                        ok, _ = mark_attendance_via_api(
                            roll_number,
                            args.room,
                            cn,
                            args.api_url,
                            args.lat,
                            args.lng,
                            schedule=cached_schedule,
                        )
                        if ok:
                            already_marked.add(roll_number)

                name = face_service._known_roll_numbers.get(roll_number, "Unknown")
                if face_locations:
                    top, right, bottom, left = face_locations[0]
                    if not attendance_active:
                        rect_c = (0, 200, 255)
                        foot = "Recognized (monitoring)"
                    elif roll_number in already_marked:
                        rect_c = (0, 255, 0)
                        foot = "Marked for this session"
                    else:
                        rect_c = (0, 255, 0)
                        foot = "Recognized"
                    cv2.rectangle(display_frame, (left, top), (right, bottom), rect_c, 2)
                    cv2.putText(
                        display_frame,
                        "{} ({})".format(name, roll_number),
                        (left, max(top - 28, 62)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.65,
                        rect_c,
                        2,
                    )
                    cv2.putText(
                        display_frame,
                        "{:.0%}".format(confidence),
                        (left, max(top - 8, 82)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.55,
                        rect_c,
                        2,
                    )
                    cv2.putText(
                        display_frame,
                        foot,
                        (left, bottom + 18),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.55,
                        (255, 255, 0),
                        2,
                    )
            else:
                if face_locations:
                    top, right, bottom, left = face_locations[0]
                    cv2.rectangle(display_frame, (left, top), (right, bottom), (0, 0, 255), 2)
                    cv2.putText(
                        display_frame,
                        "Not recognized",
                        (left, max(top - 8, 62)),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.65,
                        (0, 0, 255),
                        2,
                    )
                else:
                    cv2.putText(
                        display_frame,
                        "No face",
                        (8, 70),
                        cv2.FONT_HERSHEY_SIMPLEX,
                        0.8,
                        (128, 128, 128),
                        2,
                    )

            if show_window:
                cv2.putText(
                    display_frame,
                    "Ctrl+C to stop",
                    (8, frame.shape[0] - 12),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 255, 255),
                    1,
                )
                cv2.imshow("Attendance (Live)", display_frame)
                cv2.waitKey(1)
            else:
                time.sleep(0.03)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        cap.release()
        if show_window:
            cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    sys.exit(main())
