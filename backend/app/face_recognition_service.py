"""
Face Recognition Service
Handles face encoding, storage, and recognition using face_recognition library
"""
import json
import os
from pathlib import Path
from typing import Optional

import cv2
import face_recognition
import numpy as np
from sqlalchemy.orm import Session

from app.models import Student


class FaceRecognitionService:
    def __init__(self, encodings_dir: str = "data/face_encodings"):
        """
        Initialize the face recognition service
        
        Args:
            encodings_dir: Directory to store face encodings
        """
        self.encodings_dir = Path(encodings_dir)
        self.encodings_dir.mkdir(parents=True, exist_ok=True)
        self._known_encodings = {}
        self._known_roll_numbers = {}
        self._load_all_encodings()

    def _load_all_encodings(self):
        """Load all face encodings from disk"""
        encoding_files = list(self.encodings_dir.glob("*.json"))
        for encoding_file in encoding_files:
            roll_number = encoding_file.stem
            try:
                with open(encoding_file, 'r') as f:
                    data = json.load(f)
                    encoding = np.array(data['encoding'])
                    self._known_encodings[roll_number] = encoding
                    self._known_roll_numbers[roll_number] = data.get('name', '')
            except Exception as e:
                print(f"Error loading encoding for {roll_number}: {e}")

    def encode_face_from_image(self, image_path: str) -> Optional[np.ndarray]:
        """
        Encode a face from an image file
        
        Args:
            image_path: Path to the image file
            
        Returns:
            Face encoding array or None if no face found
        """
        try:
            image = face_recognition.load_image_file(image_path)
            encodings = face_recognition.face_encodings(image)
            if encodings:
                return encodings[0]  # Return first face found
            return None
        except Exception as e:
            print(f"Error encoding face from {image_path}: {e}")
            return None

    def encode_face_from_frame(self, frame: np.ndarray) -> Optional[np.ndarray]:
        """
        Encode a face from a video frame (BGR format from OpenCV)
        
        Args:
            frame: BGR image frame from OpenCV
            
        Returns:
            Face encoding array or None if no face found
        """
        try:
            # Convert BGR to RGB (face_recognition uses RGB)
            rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            encodings = face_recognition.face_encodings(rgb_frame)
            if encodings:
                return encodings[0]  # Return first face found
            return None
        except Exception as e:
            print(f"Error encoding face from frame: {e}")
            return None

    def save_encoding(self, roll_number: str, encoding: np.ndarray, name: str = ""):
        """
        Save face encoding to disk
        
        Args:
            roll_number: Student roll number
            encoding: Face encoding array
            name: Student name (optional)
        """
        encoding_file = self.encodings_dir / f"{roll_number}.json"
        data = {
            'encoding': encoding.tolist(),
            'name': name
        }
        with open(encoding_file, 'w') as f:
            json.dump(data, f)
        
        # Update in-memory cache
        self._known_encodings[roll_number] = encoding
        self._known_roll_numbers[roll_number] = name

    def recognize_face(self, frame: np.ndarray, tolerance: float = 0.6) -> Optional[tuple[str, float]]:
        """
        Recognize a face in a frame
        
        Args:
            frame: BGR image frame from OpenCV
            tolerance: How much distance between faces to consider it a match (lower = more strict)
            
        Returns:
            Tuple of (roll_number, confidence) or None if no match found
        """
        encoding = self.encode_face_from_frame(frame)
        if encoding is None:
            return None

        if not self._known_encodings:
            return None

        # Compare with all known faces
        roll_numbers = list(self._known_encodings.keys())
        known_encodings = [self._known_encodings[rn] for rn in roll_numbers]
        
        # Calculate face distances
        face_distances = face_recognition.face_distance(known_encodings, encoding)
        
        # Find the best match
        best_match_index = np.argmin(face_distances)
        best_distance = face_distances[best_match_index]
        
        # Check if distance is within tolerance
        if best_distance <= tolerance:
            confidence = 1.0 - best_distance  # Convert distance to confidence (0-1)
            return (roll_numbers[best_match_index], confidence)
        
        return None

    def get_student_encoding(self, roll_number: str) -> Optional[np.ndarray]:
        """Get stored encoding for a student"""
        return self._known_encodings.get(roll_number)

    def has_encoding(self, roll_number: str) -> bool:
        """Check if encoding exists for a student"""
        return roll_number in self._known_encodings

    def delete_encoding(self, roll_number: str):
        """Delete encoding for a student"""
        encoding_file = self.encodings_dir / f"{roll_number}.json"
        if encoding_file.exists():
            encoding_file.unlink()
        
        if roll_number in self._known_encodings:
            del self._known_encodings[roll_number]
        if roll_number in self._known_roll_numbers:
            del self._known_roll_numbers[roll_number]

    def capture_face_from_camera(self, camera_index: int = 0, timeout: int = 10) -> Optional[np.ndarray]:
        """
        Capture a face from the camera
        
        Args:
            camera_index: Camera device index (0 for default)
            timeout: Maximum seconds to wait for face detection
            
        Returns:
            Face encoding or None if no face detected
        """
        cap = cv2.VideoCapture(camera_index)
        if not cap.isOpened():
            print(f"Error: Could not open camera {camera_index}")
            return None

        print("Looking for a face... Press 'q' to quit, 'c' to capture")
        start_time = cv2.getTickCount()
        timeout_ticks = timeout * cv2.getTickFrequency()

        try:
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                # Check timeout
                elapsed = (cv2.getTickCount() - start_time) / cv2.getTickFrequency()
                if elapsed > timeout:
                    print("Timeout: No face detected")
                    break

                # Convert to RGB for face detection
                rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                face_locations = face_recognition.face_locations(rgb_frame)
                
                # Draw rectangle around face
                display_frame = frame.copy()
                if face_locations:
                    top, right, bottom, left = face_locations[0]
                    cv2.rectangle(display_frame, (left, top), (right, bottom), (0, 255, 0), 2)
                    cv2.putText(display_frame, "Face detected! Press 'c' to capture", 
                              (left, top - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                else:
                    cv2.putText(display_frame, "No face detected", 
                              (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)

                cv2.imshow('Face Capture - Press c to capture, q to quit', display_frame)
                
                key = cv2.waitKey(1) & 0xFF
                if key == ord('q'):
                    break
                elif key == ord('c') and face_locations:
                    # Capture the face
                    encoding = self.encode_face_from_frame(frame)
                    if encoding is not None:
                        cap.release()
                        cv2.destroyAllWindows()
                        return encoding
                    else:
                        print("Failed to encode face. Try again.")

        finally:
            cap.release()
            cv2.destroyAllWindows()

        return None
