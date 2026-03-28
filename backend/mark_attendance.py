#!/usr/bin/env python3
"""
Mark Attendance Script

Two modes:
- Hybrid (recommended for RTSP / Tapo C200): grabber thread keeps stream drained;
  worker processes every Nth frame at lower resolution; crops faces and sends
  to server (mark-by-face) for matching against passport photos.
- Live: single-thread; recognize locally, mark by roll via API (needs encodings).
"""
import argparse
import io
import sys
import threading
import time
from pathlib import Path

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
# Cooldown: don't mark same person again within this many seconds
AUTO_MARK_COOLDOWN_SEC = 10.0
# Hybrid: padding around face crop before sending to API
FACE_CROP_PADDING = 0.25
# Hybrid: default process every N frames and downscale size
DEFAULT_SAMPLE_EVERY = 8
DEFAULT_SCALE_WIDTH = 640

def get_attendance_status(schedule):

    now = datetime.now()

    start = datetime.strptime(schedule.start_time, "%H:%M")

    minutes = (now.hour * 60 + now.minute) - (start.hour * 60 + start.minute)

    if minutes <= schedule.attendance_window:
        return "present"

    elif minutes <= schedule.late_window:
        return "late"

    return "absent"

def mark_attendance_via_api(
    roll_number: str,
    room: str,
    class_name: str,
    api_url: str = "http://localhost:8000",
    lat: str = None,
    lng: str = None,
):
    """Mark attendance by roll_number (JSON API). Returns (success, roll_number)."""
    url = f"{api_url}/attendance/mark"
    status = get_attendance_status(schedule)

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

def get_active_schedule(room):

    now = datetime.now().strftime("%H:%M")

    with session_scope() as db:

        schedules = db.query(ClassSchedule).filter(
            ClassSchedule.room == room
        ).all()

        for s in schedules:

            if s.start_time <= now <= s.end_time:
                return s

    return None


def run_hybrid(
    rtsp_url: str,
    room: str,
    class_name: str,
    api_url: str,
    sample_every: int,
    scale_width: int,
    tolerance: float,
    lat: str,
    lng: str,
    show_window: bool,
    stop_event: threading.Event,
):
    """
    Hybrid pipeline: one thread grabs frames, main thread processes every Nth frame
    at reduced resolution and sends face crops to mark-by-face API.
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

    
    last_marked = {}
    already_marked = set()

    last_sent_positions = {}  # (gx, gy) -> time; cooldown by face position
    frame_count = 0
    scale_height = int(scale_width * 9 / 16)  # 640x360 default
    grid = 50  # pixels for position cooldown

    while not stop_event.is_set():
        with frame_lock:
            if latest_frame is None:
                time.sleep(0.05)
                continue
            work = latest_frame.copy()

        frame_count += 1
        if frame_count % sample_every != 0:
            if show_window:
                # Show live view (optional overlay)
                disp = cv2.resize(work, (scale_width, scale_height))
                cv2.putText(
                    disp,
                    f"Hybrid | sample 1/{sample_every} | q=quit",
                    (10, 25),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 255, 255),
                    2,
                )
                cv2.imshow("Attendance (Hybrid)", disp)
                cv2.waitKey(1)

            else:
                time.sleep(0.02)
            continue

        # Downscale for detection
        small = cv2.resize(work, (scale_width, scale_height))
        rgb = cv2.cvtColor(small, cv2.COLOR_BGR2RGB)
        face_service = FaceRecognitionService()
        face_locations = face_recognition.face_locations(rgb)

        display_frame = small.copy()
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
            encoding = face_service.encode_face_from_frame(crop)
            result = None

            if encoding is not None:
                result = face_service.recognize_face(crop)
            
            if result:
                roll_number, confidence = result

            if confidence > 0.75:
                count = face_service.get_encoding_count(roll_number)

            if count < 20:
                face_service.add_encoding(roll_number, encoding)
                print(f"Self-trained new encoding for {roll_number}")


            if crop.size == 0:
                continue
            _, jpeg = cv2.imencode(".jpg", crop)
            image_bytes = jpeg.tobytes()

            ok, roll = mark_attendance_by_face_image(
                image_bytes, room, class_name, api_url, tolerance, lat, lng
            )

            if ok and roll:
                if roll not in already_marked:
                    already_marked.add(roll)
                    last_marked[roll] = time.time()
                else:
                    continue

            last_sent_positions[(gx, gy)] = time.time()
            if ok and roll:
                last_marked[roll] = time.time()

            # Draw on display
            cv2.rectangle(display_frame, (left, top), (right, bottom), (0, 255, 0), 2)
            cv2.putText(
                display_frame,
                "Sent" if ok else "No match",
                (left, top - 8),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
                (0, 255, 0) if ok else (0, 0, 255),
                1,
            )

        if not face_locations and display_frame is not None:
            cv2.putText(
                display_frame,
                "No face",
                (10, 25),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.6,
                (128, 128, 128),
                2,
            )

        if show_window:
            cv2.putText(
                display_frame,
                f"1/{sample_every} | {scale_width}x{scale_height} | q=quit",
                (10, scale_height - 10),
                cv2.FONT_HERSHEY_SIMPLEX,
                0.5,
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
        description="Mark attendance (hybrid RTSP or live camera)",
    )
    parser.add_argument("--room", type=str, required=True, help="Room number (e.g. Room512)")
    parser.add_argument(
        "--class",
        type=str,
        dest="class_name",
        required=True,
        help="Class name (e.g. Class1)",
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
        help="Use RTSP with live pipeline: single thread, local encodings, minimal buffer. Use to compare performance vs hybrid.",
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
    parser.add_argument("--auto-mark", action="store_true", help="Auto-mark when face recognized (live mode)")
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
        print("Hybrid pipeline: grabber thread + sample every {} + downscale {}px".format(args.sample_every, args.scale_width))
        print("Room: {}  Class: {}  RTSP: {}".format(args.room, args.class_name, args.rtsp))
        print("Press 'q' to quit.\n")
        stop = threading.Event()
        try:
            run_hybrid(
                rtsp_url=args.rtsp,
                room=args.room,
                class_name=args.class_name,
                api_url=args.api_url,
                sample_every=args.sample_every,
                scale_width=args.scale_width,
                tolerance=args.tolerance,
                lat=args.lat,
                lng=args.lng,
                show_window=show_window,
                stop_event=stop,
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
    
    schedule = get_active_schedule(args.room)

    if schedule is None:
        print("❌ No scheduled class running right now")
        return 1

    print("Room: {}  Class: {}".format(args.room, args.class_name))
    if args.rtsp:
        print("Source: RTSP (live mode, no buffering) {}".format(args.rtsp))
    else:
        print("Source: camera {}".format(args.camera))
    print("Press 'm' to mark, 'q' to quit.\n")

    cap = open_video_source(rtsp_url=args.rtsp, camera_index=args.camera)
    if not cap.isOpened():
        print("❌ Could not open source.")
        return 1

    last_marked = {}
    read_failures = 0

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
                        return 1
                    read_failures = 0
                else:
                    if not args.rtsp:
                        break
                    time.sleep(0.1)
                continue
            read_failures = 0

            result = face_service.recognize_face(frame, tolerance=args.tolerance)
            display_frame = frame.copy()
            rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            face_locations = face_recognition.face_locations(rgb)

            if result:
                roll_number, confidence = result
                name = face_service._known_roll_numbers.get(roll_number, "Unknown")
                if face_locations:
                    top, right, bottom, left = face_locations[0]
                    cv2.rectangle(display_frame, (left, top), (right, bottom), (0, 255, 0), 2)
                    cv2.putText(display_frame, "{} ({})".format(name, roll_number), (left, top - 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    cv2.putText(display_frame, "{:.0%}".format(confidence), (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                    if args.auto_mark:
                        cooldown_ok = (time.time() - last_marked.get(roll_number, 0)) >= AUTO_MARK_COOLDOWN_SEC
                        if cooldown_ok:
                            ok, _ = mark_attendance_via_api(roll_number, args.room, args.class_name, args.api_url, args.lat, args.lng)
                            if ok:
                                last_marked[roll_number] = time.time()
                        cv2.putText(display_frame, "Auto-mark" if cooldown_ok else "Cooldown", (left, bottom + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
                    else:
                        cv2.putText(display_frame, "Press 'm' to mark", (left, bottom + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
            else:
                if face_locations:
                    top, right, bottom, left = face_locations[0]
                    cv2.rectangle(display_frame, (left, top), (right, bottom), (0, 0, 255), 2)
                    cv2.putText(display_frame, "Not recognized", (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                else:
                    cv2.putText(display_frame, "No face", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

            if show_window:
                cv2.imshow("Attendance", display_frame)
                cv2.waitKey(1)

            else:
                if args.auto_mark and result:
                    roll_number, _ = result
                    cooldown_ok = (time.time() - last_marked.get(roll_number, 0)) >= AUTO_MARK_COOLDOWN_SEC
                    if cooldown_ok:
                        ok, _ = mark_attendance_via_api(roll_number, args.room, args.class_name, args.api_url, args.lat, args.lng)
                        if ok:
                            last_marked[roll_number] = time.time()
                time.sleep(0.03)
    finally:
        cap.release()
        if show_window:
            cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    sys.exit(main())
