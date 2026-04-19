#!/usr/bin/env python3
"""
Live RTSP preview (OpenCV). Verifies the camera answers at the given URL.

From `backend/` with venv active:

  python scripts/test_rtsp_camera_preview.py
  python scripts/test_rtsp_camera_preview.py --rtsp rtsp://192.168.4.21/stream1
  python scripts/test_rtsp_camera_preview.py --no-display --frames 60   # headless smoke test

Press **q** in the window to quit (unless --no-display).
"""
from __future__ import annotations

import argparse
import sys
import time

import cv2

DEFAULT_RTSP = "rtsp://192.168.4.21/stream1"


def main() -> int:
    p = argparse.ArgumentParser(description="Preview RTSP camera feed (OpenCV)")
    p.add_argument("--rtsp", default=DEFAULT_RTSP, help="Stream URL")
    p.add_argument(
        "--frames",
        type=int,
        default=0,
        help="With --no-display: read this many frames then exit (default 30). Ignored when window is shown.",
    )
    p.add_argument(
        "--seconds",
        type=float,
        default=0.0,
        help="Stop after N seconds (0 = run until 'q' or Ctrl+C). Works with or without window.",
    )
    p.add_argument(
        "--no-display",
        action="store_true",
        help="Do not open a window; read frames until --frames or --seconds (for SSH / CI smoke test).",
    )
    args = p.parse_args()
    url = args.rtsp.strip()

    print(f"Opening: {url}")
    cap = cv2.VideoCapture(url, cv2.CAP_FFMPEG)
    if not cap.isOpened():
        print("ERROR: VideoCapture could not open stream (wrong URL, firewall, or codec).", file=sys.stderr)
        return 1
    try:
        cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
    except cv2.error:
        pass

    n_ok = 0
    n_fail = 0
    t0 = time.monotonic()
    max_frames = args.frames if args.no_display and args.frames > 0 else (args.frames or 30)
    if args.no_display and args.frames <= 0:
        max_frames = 30

    try:
        while True:
            ok, frame = cap.read()
            if not ok or frame is None:
                n_fail += 1
                if n_fail > 50:
                    print("ERROR: Too many read failures.", file=sys.stderr)
                    return 1
                time.sleep(0.05)
                continue
            n_fail = 0
            n_ok += 1
            h, w = frame.shape[:2]
            if n_ok == 1:
                print(f"First frame OK: {w}x{h} (BGR)")

            if not args.no_display:
                cv2.putText(
                    frame,
                    f"{n_ok} frames | {url[:48]}",
                    (8, 24),
                    cv2.FONT_HERSHEY_SIMPLEX,
                    0.5,
                    (0, 255, 0),
                    1,
                )
                cv2.imshow("RTSP preview (q to quit)", frame)
                key = cv2.waitKey(1) & 0xFF
                if key == ord("q"):
                    break
            if args.no_display and n_ok >= max_frames:
                break
            if args.seconds > 0 and (time.monotonic() - t0) >= args.seconds:
                break
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        cap.release()
        if not args.no_display:
            cv2.destroyAllWindows()

    print(f"Done. Decoded frames: {n_ok}")
    return 0 if n_ok > 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
