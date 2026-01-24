#!/usr/bin/env python3
"""
Mark Attendance Script
Captures face from camera, recognizes student, and marks attendance via API
"""
import argparse
import sys
from pathlib import Path

import cv2
import face_recognition
import requests

# Add parent directory to path to import app modules
sys.path.insert(0, str(Path(__file__).parent))

from app.face_recognition_service import FaceRecognitionService


def mark_attendance_via_api(roll_number: str, room: str, class_name: str, 
                            api_url: str = "http://localhost:8000",
                            lat: str = None, lng: str = None):
    """
    Mark attendance via API call
    
    Args:
        roll_number: Student roll number
        room: Room number (e.g., "Room512")
        class_name: Class name (e.g., "Class1")
        api_url: Base URL of the API
        lat: Latitude (optional)
        lng: Longitude (optional)
    """
    url = f"{api_url}/attendance/mark"
    payload = {
        "roll_number": roll_number,
        "room": room,
        "class_name": class_name,
        "status": "present"
    }
    
    if lat:
        payload["lat"] = lat
    if lng:
        payload["lng"] = lng
    
    try:
        response = requests.post(url, json=payload)
        response.raise_for_status()
        data = response.json()
        print(f"✅ Attendance marked successfully!")
        print(f"   Student: {data.get('student_name')} ({data.get('student_roll')})")
        print(f"   Room: {data.get('room')}, Class: {data.get('class_name')}")
        print(f"   Date: {data.get('date_key')}, Time: {data.get('marked_at')}")
        return True
    except requests.exceptions.RequestException as e:
        print(f"❌ Error marking attendance: {e}")
        if hasattr(e.response, 'text'):
            print(f"   Response: {e.response.text}")
        return False


def main():
    parser = argparse.ArgumentParser(description='Mark attendance using face recognition')
    parser.add_argument('--room', type=str, required=True, help='Room number (e.g., Room512)')
    parser.add_argument('--class', type=str, dest='class_name', required=True, 
                       help='Class name (e.g., Class1)')
    parser.add_argument('--api-url', type=str, default='http://localhost:8000',
                       help='API base URL (default: http://localhost:8000)')
    parser.add_argument('--camera', type=int, default=0, help='Camera index (default: 0)')
    parser.add_argument('--tolerance', type=float, default=0.6,
                       help='Face recognition tolerance (default: 0.6, lower = more strict)')
    parser.add_argument('--lat', type=str, help='Latitude for geotagging')
    parser.add_argument('--lng', type=str, help='Longitude for geotagging')
    
    args = parser.parse_args()

    # Initialize face recognition service
    print("Loading face recognition service...")
    face_service = FaceRecognitionService()
    
    if not face_service._known_encodings:
        print("❌ No face encodings found. Please enroll students first.")
        print("   Run: python enroll_student.py")
        return 1

    print(f"✅ Loaded {len(face_service._known_encodings)} student face encodings")
    print(f"\nRoom: {args.room}, Class: {args.class_name}")
    print("Looking for faces... Press 'q' to quit\n")

    # Open camera
    cap = cv2.VideoCapture(args.camera)
    if not cap.isOpened():
        print(f"❌ Error: Could not open camera {args.camera}")
        return 1

    try:
        while True:
            ret, frame = cap.read()
            if not ret:
                break

            # Try to recognize face
            result = face_service.recognize_face(frame, tolerance=args.tolerance)
            
            # Display frame with annotations
            display_frame = frame.copy()
            
            if result:
                roll_number, confidence = result
                name = face_service._known_roll_numbers.get(roll_number, "Unknown")
                
                # Draw green box and info
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                face_locations = face_recognition.face_locations(rgb_frame)
                if face_locations:
                    top, right, bottom, left = face_locations[0]
                    cv2.rectangle(display_frame, (left, top), (right, bottom), (0, 255, 0), 2)
                    
                    # Display recognition info
                    info_text = f"{name} ({roll_number})"
                    conf_text = f"Confidence: {confidence:.2%}"
                    cv2.putText(display_frame, info_text, (left, top - 30),
                              cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                    cv2.putText(display_frame, conf_text, (left, top - 10),
                              cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 0), 2)
                    cv2.putText(display_frame, "Press 'm' to mark attendance",
                              (left, bottom + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)
            else:
                # No face recognized
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                face_locations = face_recognition.face_locations(rgb_frame)
                if face_locations:
                    top, right, bottom, left = face_locations[0]
                    cv2.rectangle(display_frame, (left, top), (right, bottom), (0, 0, 255), 2)
                    cv2.putText(display_frame, "Face not recognized", (left, top - 10),
                              cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 0, 255), 2)
                else:
                    cv2.putText(display_frame, "No face detected",
                              (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

            cv2.imshow('Face Recognition - Press m to mark, q to quit', display_frame)
            
            key = cv2.waitKey(1) & 0xFF
            if key == ord('q'):
                break
            elif key == ord('m') and result:
                # Mark attendance
                roll_number, confidence = result
                print(f"\n🎯 Recognizing: {face_service._known_roll_numbers.get(roll_number, 'Unknown')} ({roll_number})")
                print(f"   Confidence: {confidence:.2%}")
                
                if mark_attendance_via_api(roll_number, args.room, args.class_name,
                                         args.api_url, args.lat, args.lng):
                    print("\n✅ Attendance marked! Continue scanning or press 'q' to quit.\n")
                else:
                    print("\n❌ Failed to mark attendance. Try again.\n")

    finally:
        cap.release()
        cv2.destroyAllWindows()

    return 0


if __name__ == "__main__":
    sys.exit(main())
