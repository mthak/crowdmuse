#!/usr/bin/env python3
"""
Enroll Student Script
Captures face from camera and registers student in database.

Writes under **`data/face_encodings/`**:
- **`<roll>.json`** — face encoding(s) used for recognition (required).
- **`<roll>.jpg`** — optional cropped, upscaled reference photo (unless **`--no-save-jpeg`**).

Example (Mac built-in camera, sample user Asha):

  python enroll_student.py --roll-number 98104ME102 --name "Asha Menon (Room 102 demo)" \\
    --batch-year 2025 --stream "Mechanical Engineering" --camera 0
"""
import argparse
import sys
from pathlib import Path

import cv2
import requests

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent))

from app.face_recognition_service import FaceRecognitionService


def ensure_stream_id(api_url: str, stream_name: str) -> int | None:
    """Return stream id for `stream_name`, creating the stream via API if needed."""
    base = api_url.rstrip("/")
    name = stream_name.strip()
    try:
        r = requests.get(f"{base}/streams", timeout=30)
        r.raise_for_status()
        for row in r.json():
            if row.get("name") == name:
                return int(row["id"])
        c = requests.post(f"{base}/streams", json={"name": name}, timeout=30)
        c.raise_for_status()
        return int(c.json()["id"])
    except requests.exceptions.RequestException as e:
        print(f"❌ Error resolving stream: {e}")
        return None


def create_student_via_api(
    roll_number: str,
    name: str,
    stream_id: int,
    batch_year: int,
    api_url: str = "http://localhost:8000",
):
    """
    Create student via API call (cohort = stream + batch year).

    Args:
        roll_number: Student roll number
        name: Student name
        stream_id: Program/branch id from GET /streams
        batch_year: Cohort year (e.g. 2025 for the 2025 batch)
        api_url: Base URL of the API

    Returns:
        True if successful, False otherwise
    """
    url = f"{api_url.rstrip('/')}/students"
    payload = {
        "roll_number": roll_number,
        "name": name,
        "stream_id": stream_id,
        "batch_year": batch_year,
    }
    
    try:
        response = requests.post(url, json=payload, timeout=30)
        if response.status_code == 409:
            print("ℹ️  Student already exists in the API — continuing with face encoding only.")
            return True
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ Error creating student: {e}")
        if hasattr(e, "response") and e.response is not None:
            try:
                error_data = e.response.json()
                print(f"   Error: {error_data.get('detail', 'Unknown error')}")
            except Exception:
                print(f"   Response: {e.response.text}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Enroll student with face recognition')
    parser.add_argument('--roll-number', type=str, required=True, help='Student roll number')
    parser.add_argument('--name', type=str, required=True, help='Student name')
    parser.add_argument(
        '--batch-year',
        type=int,
        required=True,
        help='Cohort batch year (e.g. 2025 for Mechanical Engineering 2025)',
    )
    parser.add_argument(
        '--stream',
        type=str,
        required=True,
        help='Program name (e.g. "Mechanical Engineering"); created on server if new',
    )
    parser.add_argument(
        '--stream-id',
        type=int,
        default=None,
        help='If set, skip name lookup and use this stream id from GET /streams',
    )
    parser.add_argument('--api-url', type=str, default='http://localhost:8000',
                       help='API base URL (default: http://localhost:8000)')
    parser.add_argument('--camera', type=int, default=0, help='USB camera index (default: 0)')
    parser.add_argument(
        '--rtsp',
        type=str,
        default=None,
        help='RTSP URL (network/IP camera). Same interactive capture as USB; use with room camera.',
    )
    parser.add_argument('--photo', type=str, default=None,
                       help='Enroll from image file (e.g. .jpg/.png) instead of live camera/RTSP')
    parser.add_argument(
        '--no-save-jpeg',
        action='store_true',
        help='Do not write data/face_encodings/<roll>.jpg reference photo (encoding JSON is always saved).',
    )

    args = parser.parse_args()

    # Initialize face recognition service
    print("Initializing face recognition service...")
    face_service = FaceRecognitionService()

    # Check if student already has face encoding
    if face_service.has_encoding(args.roll_number):
        print(f"⚠️  Face encoding already exists for {args.roll_number}")
        response = input("Do you want to update it? (y/n): ")
        if response.lower() != 'y':
            print("Cancelled.")
            return 0

    stream_id = args.stream_id
    if stream_id is None:
        print(f"\nResolving stream: {args.stream.strip()}...")
        stream_id = ensure_stream_id(args.api_url, args.stream)
        if stream_id is None:
            return 1
        print(f"   stream_id={stream_id}")

    # Create student in database first
    print(f"\nCreating student record: {args.name} ({args.roll_number})...")
    if not create_student_via_api(
        args.roll_number, args.name, stream_id, args.batch_year, args.api_url
    ):
        print("❌ Failed to create student. Please check the API is running and try again.")
        return 1

    print("✅ Student created in database")

    snapshot_bgr = None

    if args.photo:
        # Enroll from passport-size photo file
        photo_path = Path(args.photo)
        if not photo_path.is_file():
            print(f"❌ Photo file not found: {args.photo}")
            return 1
        print(f"\n📷 Encoding face from passport photo: {args.photo}")
        encoding = face_service.encode_face_from_passport_photo(str(photo_path))
        img = cv2.imread(str(photo_path))
        if img is not None:
            snapshot_bgr = img
    elif args.rtsp:
        print(f"\n📸 RTSP stream: {args.rtsp}")
        print("   Position your face in view; press 'c' to capture when a box appears, 'q' to quit")
        encoding, snapshot_bgr = face_service.capture_face_from_rtsp(args.rtsp.strip(), timeout=60)
    else:
        # Mac / USB camera (index 0 is usually FaceTime HD)
        print(f"\n📸 Capturing face from camera index {args.camera} (Mac: 0 is usually built-in)...")
        print("   Position your face in front of the camera")
        print("   Press 'c' to capture when ready, 'q' to quit")
        encoding, snapshot_bgr = face_service.capture_face_from_camera(camera_index=args.camera, timeout=60)

    if encoding is None:
        print("❌ No face found. For passport photos use a clear frontal face; try a higher-res image.")
        return 1

    if not args.no_save_jpeg and snapshot_bgr is not None:
        try:
            jpg_path = face_service.save_enrollment_jpeg(args.roll_number, snapshot_bgr)
            print(f"\n🖼️  Reference photo saved: {jpg_path}")
        except OSError as e:
            print(f"⚠️  Could not save reference JPEG: {e}")

    # Save face encoding (JSON in same folder; only *.json loaded for matching)
    print(f"\n💾 Saving face encoding...")
    face_service.save_encoding(args.roll_number, encoding, args.name)
    print(f"✅ Face encoding saved: {face_service.encodings_dir / (args.roll_number + '.json')}")
    print("\n🎉 Student enrollment complete!")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
