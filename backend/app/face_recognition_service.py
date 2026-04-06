"""
Face Recognition Service
Handles face encoding, storage, and recognition using face_recognition library
"""
import json
import time
from pathlib import Path
from typing import Optional

import cv2
import face_recognition
import numpy as np


class FaceRecognitionService:
    # Self-learning: buffer similar live encodings, then append averaged encoding
    SELF_LEARN_MIN_CONFIDENCE = 0.75
    SELF_LEARN_MAX_TEMP_DISTANCE = 0.5
    SELF_LEARN_BATCH_SIZE = 5
    SELF_LEARN_COOLDOWN_SEC = 60.0
    MAX_ENCODINGS_PER_STUDENT = 20

    def __init__(self, encodings_dir: str = "data/face_encodings"):
        """
        Initialize the face recognition service
        
        Args:
            encodings_dir: Directory to store face encodings
        """
        self.encodings_dir = Path(encodings_dir)
        self.encodings_dir.mkdir(parents=True, exist_ok=True)
        self._known_encodings = {}  # roll_number → list of encodings
        self._known_roll_numbers = {}
        self._self_learn_temp: dict[str, list[np.ndarray]] = {}
        self._self_learn_last_commit: dict[str, float] = {}
        self._load_all_encodings()

    def _load_all_encodings(self):
        """Load all face encodings from disk"""
        encoding_files = list(self.encodings_dir.glob("*.json"))
        for encoding_file in encoding_files:
            roll_number = encoding_file.stem
            try:
                with open(encoding_file, 'r') as f:
                    data = json.load(f)
                    if roll_number not in self._known_encodings:
                        self._known_encodings[roll_number] = []
                    name = data.get('name', '')
                    if 'encodings' in data and data['encodings']:
                        for row in data['encodings']:
                            self._known_encodings[roll_number].append(
                                np.asarray(row, dtype=np.float64).reshape(-1)
                            )
                    elif 'encoding' in data:
                        arr = np.asarray(data['encoding'], dtype=np.float64)
                        if arr.ndim == 1:
                            self._known_encodings[roll_number].append(arr)
                        else:
                            for row in arr:
                                self._known_encodings[roll_number].append(
                                    np.asarray(row, dtype=np.float64).reshape(-1)
                                )
                    self._known_roll_numbers[roll_number] = name
            except Exception as e:
                print(f"Error loading encoding for {roll_number}: {e}")

    def encode_face_from_image(self, image_path: str) -> Optional[np.ndarray]:
        """
        Encode a face from an image file (any size).
        
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

    def encode_face_from_passport_photo(self, image_path: str, min_side_px: int = 400, num_jitters: int = 2) -> Optional[np.ndarray]:
        """
        Encode a face from a passport-size or small photo.
        Upscales small images so the face is at least ~96px (required by the model)
        and uses extra jitters for more stable encoding to match live video.
        
        Args:
            image_path: Path to the passport/small photo (e.g. JPG/PNG).
            min_side_px: Minimum width or height in pixels (upscale if smaller).
            num_jitters: Number of times to re-sample encoding (higher = more stable).
            
        Returns:
            Face encoding array or None if no face found.
        """
        try:
            image = face_recognition.load_image_file(image_path)
            h, w = image.shape[:2]
            if min(h, w) < min_side_px:
                scale = min_side_px / min(h, w)
                new_w, new_h = int(w * scale), int(h * scale)
                image = cv2.resize(image, (new_w, new_h), interpolation=cv2.INTER_LINEAR)
            # Use num_jitters for better match to live frames (same as typical video usage)
            encodings = face_recognition.face_encodings(image, num_jitters=num_jitters)
            if encodings:
                return encodings[0]
            return None
        except Exception as e:
            print(f"Error encoding passport photo {image_path}: {e}")
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

    def encode_face_from_bytes(self, image_bytes: bytes) -> Optional[np.ndarray]:
        """
        Encode a face from raw image bytes (e.g. uploaded file).
        Supports JPEG/PNG. Decodes to BGR then encodes first face found.
        """
        try:
            arr = np.frombuffer(image_bytes, dtype=np.uint8)
            frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            if frame is None:
                return None
            return self.encode_face_from_frame(frame)
        except Exception as e:
            print(f"Error encoding face from bytes: {e}")
            return None

    def recognize_face_from_image_bytes(
        self, image_bytes: bytes, tolerance: float = 0.6
    ) -> Optional[tuple[str, float]]:
        """
        Decode image bytes, encode face, and match against stored encodings
        (e.g. from passport photos). Used when server receives a captured frame.
        """
        encoding = self.encode_face_from_bytes(image_bytes)
        if encoding is None:
            return None
        return self.match_encoding(encoding, tolerance)

    def _persist_roll_encodings(self, roll_number: str):
        """Write all encodings for a roll number to disk."""
        enc_list = self._known_encodings.get(roll_number)
        if not enc_list:
            return
        encoding_file = self.encodings_dir / f"{roll_number}.json"
        data = {
            'name': self._known_roll_numbers.get(roll_number, ''),
            'encodings': [e.reshape(-1).tolist() for e in enc_list],
        }
        with open(encoding_file, 'w') as f:
            json.dump(data, f)

    def match_encoding(
        self, encoding: np.ndarray, tolerance: float = 0.6
    ) -> Optional[tuple[str, float]]:
        """Match a 128-d face encoding against stored encodings."""
        if encoding is None or not self._known_encodings:
            return None
        enc = np.asarray(encoding, dtype=np.float64).reshape(-1)
        roll_numbers = []
        known_encodings = []
        for rn, enc_list in self._known_encodings.items():
            for e in enc_list:
                roll_numbers.append(rn)
                known_encodings.append(np.asarray(e, dtype=np.float64).reshape(-1))
        if not known_encodings:
            return None
        face_distances = face_recognition.face_distance(known_encodings, enc)
        best_match_index = int(np.argmin(face_distances))
        best_distance = face_distances[best_match_index]
        if best_distance <= tolerance:
            confidence = 1.0 - best_distance
            return (roll_numbers[best_match_index], confidence)
        return None

    def self_learn_from_recognition(
        self, roll_number: str, encoding: np.ndarray, confidence: float
    ) -> None:
        """
        Buffer high-confidence encodings that cluster together; after
        SELF_LEARN_BATCH_SIZE samples, append their mean (does not replace).
        Respects cooldown and max encodings per student.
        """
        if confidence < self.SELF_LEARN_MIN_CONFIDENCE:
            return
        enc = np.asarray(encoding, dtype=np.float64).reshape(-1)
        if enc.size != 128:
            return
        now = time.monotonic()
        last = self._self_learn_last_commit.get(roll_number)
        if last is not None and (now - last) < self.SELF_LEARN_COOLDOWN_SEC:
            return
        temp = self._self_learn_temp.setdefault(roll_number, [])
        for existing in temp:
            d = float(face_recognition.face_distance([existing], enc)[0])
            if d >= self.SELF_LEARN_MAX_TEMP_DISTANCE:
                return
        temp.append(enc.copy())
        if len(temp) < self.SELF_LEARN_BATCH_SIZE:
            return
        avg = np.mean(np.stack(temp, axis=0), axis=0)
        self._self_learn_temp[roll_number] = []
        if self.add_encoding(roll_number, avg):
            self._self_learn_last_commit[roll_number] = now
            print(f"Self-learn: appended averaged encoding for {roll_number}")

    def save_encoding(self, roll_number: str, encoding: np.ndarray, name: str = ""):
        """
        Save face encoding to disk
        
        Args:
            roll_number: Student roll number
            encoding: Face encoding array
            name: Student name (optional)
        """
        if roll_number not in self._known_encodings:
            self._known_encodings[roll_number] = []
        enc = np.asarray(encoding, dtype=np.float64).reshape(-1)
        self._known_encodings[roll_number].append(enc)
        self._known_roll_numbers[roll_number] = name
        self._persist_roll_encodings(roll_number)

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
        return self.match_encoding(encoding, tolerance)

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
        self._self_learn_temp.pop(roll_number, None)
        self._self_learn_last_commit.pop(roll_number, None)

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
    
    def get_encoding_count(self, roll_number: str) -> int:

        enc = self._known_encodings.get(roll_number)

        if enc is None:
            return 0

        if isinstance(enc, list):
            return len(enc)

        # old format (single encoding)
        return 1


    def add_encoding(self, roll_number: str, encoding: np.ndarray) -> bool:
        if roll_number not in self._known_encodings:
            self._known_encodings[roll_number] = []

        if not isinstance(self._known_encodings[roll_number], list):
            self._known_encodings[roll_number] = [self._known_encodings[roll_number]]

        if len(self._known_encodings[roll_number]) >= self.MAX_ENCODINGS_PER_STUDENT:
            return False

        enc = np.asarray(encoding, dtype=np.float64).reshape(-1)
        self._known_encodings[roll_number].append(enc)
        self._persist_roll_encodings(roll_number)
        return True


    




