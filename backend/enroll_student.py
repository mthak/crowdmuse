#!/usr/bin/env python3
"""
Enroll Student Script
Captures face from camera and registers student in database
"""
import argparse
import sys
from pathlib import Path

import requests

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent))

from app.face_recognition_service import FaceRecognitionService


def create_student_via_api(roll_number: str, name: str, year: int, stream: str,
                           api_url: str = "http://localhost:8000"):
    """
    Create student via API call
    
    Args:
        roll_number: Student roll number
        name: Student name
        year: Academic year
        stream: Tech stream (e.g., "Computer Science")
        api_url: Base URL of the API
        
    Returns:
        True if successful, False otherwise
    """
    url = f"{api_url}/students"
    payload = {
        "roll_number": roll_number,
        "name": name,
        "year": year,
        "stream": stream
    }
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ Error creating student: {e}")
        if hasattr(e, 'response') and e.response is not None:
            try:
                error_data = e.response.json()
                print(f"   Error: {error_data.get('detail', 'Unknown error')}")
            except:
                print(f"   Response: {e.response.text}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Enroll student with face recognition')
    parser.add_argument('--roll-number', type=str, required=True, help='Student roll number')
    parser.add_argument('--name', type=str, required=True, help='Student name')
    parser.add_argument('--year', type=int, required=True, help='Academic year (1-4)')
    parser.add_argument('--stream', type=str, required=True, 
                       help='Tech stream (e.g., "Computer Science", "Electronics")')
    parser.add_argument('--api-url', type=str, default='http://localhost:8000',
                       help='API base URL (default: http://localhost:8000)')
    parser.add_argument('--camera', type=int, default=0, help='Camera index (default: 0)')
    
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

    # Create student in database first
    print(f"\nCreating student record: {args.name} ({args.roll_number})...")
    if not create_student_via_api(args.roll_number, args.name, args.year, args.stream, args.api_url):
        print("❌ Failed to create student. Please check the API is running and try again.")
        return 1

    print("✅ Student created in database")

    # Capture face from camera
    print(f"\n📸 Capturing face from camera {args.camera}...")
    print("   Position your face in front of the camera")
    print("   Press 'c' to capture when ready, 'q' to quit")
    
    encoding = face_service.capture_face_from_camera(camera_index=args.camera, timeout=30)
    
    if encoding is None:
        print("❌ Failed to capture face. Please try again.")
        return 1

    # Save face encoding
    print(f"\n💾 Saving face encoding...")
    face_service.save_encoding(args.roll_number, encoding, args.name)
    print(f"✅ Face encoding saved for {args.name} ({args.roll_number})")
    print("\n🎉 Student enrollment complete!")
    
    return 0


if __name__ == "__main__":
    sys.exit(main())
