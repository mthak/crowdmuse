#!/usr/bin/env python3
"""
Capture one frame from the default webcam and POST it to **`POST /students/enrollment-image`**.

The student must already exist (`POST /students` or 409 continue). Requires the API running
(e.g. `uvicorn app.main:app --reload`).

**Mac / Continuity Camera:** OpenCV index `0` is not always the device you expect. If you see
`400 No face detected`, try **`--camera 1`** or **`--preview`** to pick a good frame. The first
frame from a camera is often black or underexposed — this script discards warmup frames by default.

Example (Mac built-in camera):

  python scripts/capture_and_upload_enrollment.py --roll-number 98104ME102 --api-url http://127.0.0.1:8000
"""
from __future__ import annotations

import argparse
import sys
from io import BytesIO
from pathlib import Path

import cv2
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


def main() -> int:
    p = argparse.ArgumentParser(description="Capture webcam frame → enrollment image API")
    p.add_argument("--roll-number", required=True, help="Existing student roll number")
    p.add_argument("--api-url", default="http://127.0.0.1:8000", help="CrowdMuse API base URL")
    p.add_argument("--camera", type=int, default=0, help="OpenCV camera index (default 0)")
    p.add_argument(
        "--warmup",
        type=int,
        default=20,
        metavar="N",
        help="Discard the first N frames so the sensor can expose (default 20). Set 0 to skip.",
    )
    p.add_argument(
        "--preview",
        action="store_true",
        help="Show a live window; press C to capture, Q to quit (helps Continuity / wrong camera index).",
    )
    p.add_argument(
        "--no-replace-encoding",
        action="store_true",
        help="Append encoding instead of replacing (default: replace)",
    )
    args = p.parse_args()

    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        print(f"❌ Could not open camera index {args.camera}", file=sys.stderr)
        return 1

    frame = None
    try:
        if args.preview:
            print("Preview: press C to capture, Q to quit.")
            while True:
                ok, fr = cap.read()
                if not ok or fr is None:
                    print("❌ Failed to read from camera.", file=sys.stderr)
                    return 1
                vis = fr.copy()
                cv2.putText(
                    vis,
                    "C = capture  Q = quit",
                    (8, 24),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.6,
                    (0, 220, 0),
                    2,
                )
                cv2.imshow("enrollment capture", vis)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    print("Quit without capture.", file=sys.stderr)
                    return 1
                if key == ord("c"):
                    frame = fr
                    break
        else:
            for _ in range(max(0, args.warmup)):
                cap.read()
            ok, frame = cap.read()
            if not ok or frame is None:
                print("❌ Failed to read a frame from the camera.", file=sys.stderr)
                return 1
    finally:
        cap.release()
        if args.preview:
            cv2.destroyWindow("enrollment capture")

    if frame is None:
        print("❌ No frame captured.", file=sys.stderr)
        return 1

    ok, buf = cv2.imencode(".jpg", frame, [int(cv2.IMWRITE_JPEG_QUALITY), 90])
    if not ok:
        print("❌ Failed to encode frame as JPEG.", file=sys.stderr)
        return 1

    bio = BytesIO(buf.tobytes())
    base = args.api_url.rstrip("/")
    url = f"{base}/students/enrollment-image"
    files = {"image": ("enrollment.jpg", bio, "image/jpeg")}
    data = {
        "roll_number": args.roll_number.strip(),
        "replace_encoding": "false" if args.no_replace_encoding else "true",
    }

    try:
        r = requests.post(url, files=files, data=data, timeout=60)
    except requests.exceptions.RequestException as e:
        print(f"❌ Request failed: {e}", file=sys.stderr)
        return 1

    if r.status_code != 200:
        print(f"❌ {r.status_code}: {r.text}", file=sys.stderr)
        return 1

    body = r.json()
    print("✅ Enrollment image uploaded.")
    print(f"   JPEG: {body.get('jpeg_path')}")
    print(f"   Encoding updated: {body.get('encoding_updated')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
