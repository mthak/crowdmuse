# Mark Attendance Script - Documentation

## Overview

The `mark_attendance.py` script is a face recognition-based attendance system that:
1. Captures video from your MacBook camera
2. Recognizes students' faces in real-time
3. Marks their attendance via API calls to the backend database

## Prerequisites

Before running the script, ensure:

1. **Python 3.8+** is installed
2. **Dependencies are installed**:
   ```bash
   cd backend
   pip install -r requirements.txt
   ```
3. **Backend API server is running**:
   ```bash
   uvicorn app.main:app --reload --port 8000
   ```
4. **Students are enrolled** with face encodings (run `enroll_student.py` first)

## How It Works - Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Script Starts                                            │
│    - Loads face encodings from data/face_encodings/         │
│    - Opens camera (default: camera index 0)                 │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│ 2. Camera Loop (Continuous)                                  │
│    - Captures frame from camera                              │
│    - Converts BGR → RGB for face_recognition library         │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│ 3. Face Detection                                            │
│    - Uses face_recognition.face_locations()                  │
│    - Draws bounding box around detected face                 │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│ 4. Face Encoding                                            │
│    - Extracts face encoding from frame                      │
│    - Uses face_recognition.face_encodings()                  │
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│ 5. Face Recognition                                          │
│    - Compares encoding with all known encodings              │
│    - Calculates face_distance() for each known face         │
│    - Finds best match (lowest distance)                     │
│    - Checks if distance ≤ tolerance (default: 0.6)          │
└──────────────────┬──────────────────────────────────────────┘
                   │
         ┌─────────┴─────────┐
         │                   │
         ▼                   ▼
    ┌─────────┐        ┌──────────┐
    │ Match   │        │ No Match │
    │ Found   │        │ Found    │
    └────┬────┘        └────┬─────┘
         │                  │
         │                  │
         ▼                  ▼
    ┌─────────────────────────────────────┐
    │ 6. Display Recognition             │
    │    - Green box + name + roll number│
    │    - Shows confidence percentage    │
    │    - Shows "Press 'm' to mark"      │
    └──────────────┬──────────────────────┘
                   │
                   │ (User presses 'm')
                   ▼
┌─────────────────────────────────────────────────────────────┐
│ 7. Mark Attendance via API                                   │
│    - POST request to http://localhost:8000/attendance/mark   │
│    - Payload: roll_number, room, class_name, status, lat, lng│
└──────────────────┬──────────────────────────────────────────┘
                   │
                   ▼
┌─────────────────────────────────────────────────────────────┐
│ 8. API Response                                              │
│    - Success: Shows attendance details                      │
│    - Error: Shows error message                             │
└─────────────────────────────────────────────────────────────┘
```

## Code Structure

### Main Components

1. **`FaceRecognitionService`** (from `app/face_recognition_service.py`)
   - Loads face encodings from disk
   - Encodes faces from camera frames
   - Recognizes faces by comparing encodings

2. **`mark_attendance_via_api()` function**
   - Makes HTTP POST request to backend API
   - Handles errors and displays results

3. **Main loop**
   - Continuous camera capture
   - Real-time face recognition
   - Keyboard input handling ('m' to mark, 'q' to quit)

## Running the Script

### Basic Usage

```bash
cd backend
python mark_attendance.py --room "Room512" --class "Class1"
```

### Full Command with All Options

```bash
python mark_attendance.py \
  --room "Room512" \
  --class "Class1" \
  --api-url "http://localhost:8000" \
  --camera 0 \
  --tolerance 0.6 \
  --lat "28.613900" \
  --lng "77.209000"
```

### Command Line Arguments

| Argument | Required | Default | Description |
|----------|----------|---------|-------------|
| `--room` | ✅ Yes | - | Room number (e.g., "Room512") |
| `--class` | ✅ Yes | - | Class name (e.g., "Class1") |
| `--api-url` | ❌ No | `http://localhost:8000` | Backend API base URL |
| `--camera` | ❌ No | `0` | Camera device index (0 = default camera) |
| `--tolerance` | ❌ No | `0.6` | Face recognition tolerance (lower = stricter) |
| `--lat` | ❌ No | `None` | Latitude for geotagging |
| `--lng` | ❌ No | `None` | Longitude for geotagging |

### Keyboard Controls

- **'m'** - Mark attendance for recognized face
- **'q'** - Quit the application

## Debugging Guide

### Issue 1: "No face encodings found"

**Error Message:**
```
❌ No face encodings found. Please enroll students first.
```

**Cause:** No students have been enrolled with face encodings.

**Solution:**
1. Run the enrollment script first:
   ```bash
   python enroll_student.py --roll-number "CS23-001" --name "John Doe" --year 2 --stream "Computer Science"
   ```
2. Check if encodings exist:
   ```bash
   ls -la data/face_encodings/
   ```
3. You should see JSON files like `CS23-001.json`

### Issue 2: "Could not open camera"

**Error Message:**
```
❌ Error: Could not open camera 0
```

**Causes & Solutions:**

1. **Camera is being used by another application**
   - Close other apps using the camera (Zoom, FaceTime, etc.)
   - Try a different camera index: `--camera 1`

2. **Camera permissions not granted**
   - macOS: System Settings → Privacy & Security → Camera
   - Grant permission to Terminal/Python

3. **Wrong camera index**
   - List available cameras:
     ```python
     import cv2
     for i in range(5):
         cap = cv2.VideoCapture(i)
         if cap.isOpened():
             print(f"Camera {i} is available")
             cap.release()
     ```

### Issue 3: "Face not recognized"

**Symptoms:**
- Face detected (red box) but no recognition
- Shows "Face not recognized" message

**Causes & Solutions:**

1. **Face encoding not enrolled**
   - Make sure student was enrolled using `enroll_student.py`
   - Check encoding file exists: `data/face_encodings/{roll_number}.json`

2. **Tolerance too strict**
   - Try increasing tolerance: `--tolerance 0.7` (default is 0.6)
   - Lower tolerance = stricter matching

3. **Poor lighting or angle**
   - Ensure good lighting
   - Face should be front-facing
   - Remove glasses/mask if possible

4. **Face encoding quality**
   - Re-enroll the student with better lighting
   - Capture multiple angles during enrollment

### Issue 4: "Error marking attendance" (API errors)

**Error Message:**
```
❌ Error marking attendance: ...
```

**Causes & Solutions:**

1. **API server not running**
   ```bash
   # Check if API is running
   curl http://localhost:8000/health
   # Should return: {"status":"ok"}
   ```
   - Start API: `uvicorn app.main:app --reload --port 8000`

2. **Student not found in database**
   - Error: `404 - Student not found`
   - Solution: Create student via API or enrollment script

3. **Network/connection issues**
   - Check API URL: `--api-url "http://localhost:8000"`
   - Verify firewall isn't blocking connections

4. **Database errors**
   - Check API server logs for database errors
   - Ensure database file exists: `data/crowdmuse.sqlite3`

### Issue 5: Low recognition confidence

**Symptoms:**
- Face recognized but confidence is low (< 50%)
- Recognition is inconsistent

**Solutions:**

1. **Improve enrollment quality**
   - Re-enroll with better lighting
   - Capture face from same angle as attendance marking
   - Ensure face fills most of the frame

2. **Adjust tolerance**
   - Lower tolerance (0.5) = stricter, fewer false positives
   - Higher tolerance (0.7) = more lenient, more matches

3. **Check face encoding files**
   ```bash
   # View encoding file
   cat data/face_encodings/CS23-001.json
   # Should contain "encoding" array with 128 numbers
   ```

### Issue 6: Multiple faces detected

**Behavior:**
- Script only recognizes the first face found
- If multiple students in frame, only one is recognized

**Solution:**
- Position camera so only one student is visible
- Or modify code to handle multiple faces (advanced)

## Debugging Tips

### 1. Enable Verbose Output

Add print statements to see what's happening:

```python
# In mark_attendance.py, add after line 89:
if result:
    roll_number, confidence = result
    print(f"DEBUG: Recognized {roll_number} with confidence {confidence:.2%}")
```

### 2. Test Face Recognition Separately

Create a test script:

```python
# test_face_recognition.py
from app.face_recognition_service import FaceRecognitionService
import cv2

service = FaceRecognitionService()
print(f"Loaded {len(service._known_encodings)} encodings")

cap = cv2.VideoCapture(0)
ret, frame = cap.read()
if ret:
    result = service.recognize_face(frame)
    if result:
        print(f"Recognized: {result}")
    else:
        print("No match found")
cap.release()
```

### 3. Check API Endpoints Manually

Test the API directly:

```bash
# Check health
curl http://localhost:8000/health

# List students
curl http://localhost:8000/students

# Mark attendance manually
curl -X POST http://localhost:8000/attendance/mark \
  -H "Content-Type: application/json" \
  -d '{
    "roll_number": "CS23-001",
    "room": "Room512",
    "class_name": "Class1"
  }'
```

### 4. Verify Face Encodings

```python
# check_encodings.py
import json
from pathlib import Path

encodings_dir = Path("data/face_encodings")
for file in encodings_dir.glob("*.json"):
    with open(file) as f:
        data = json.load(f)
        print(f"{file.stem}: encoding length = {len(data['encoding'])}")
```

### 5. Monitor API Logs

Watch the API server terminal for:
- Request logs
- Database errors
- Validation errors

## Common Workflow

1. **First Time Setup:**
   ```bash
   # 1. Install dependencies
   pip install -r requirements.txt
   
   # 2. Start API server
   uvicorn app.main:app --reload --port 8000
   
   # 3. Enroll students
   python enroll_student.py --roll-number "CS23-001" --name "John" --year 2 --stream "CS"
   ```

2. **Daily Attendance Marking:**
   ```bash
   # Start API (if not running)
   uvicorn app.main:app --reload --port 8000
   
   # Mark attendance
   python mark_attendance.py --room "Room512" --class "Class1"
   ```

## Performance Tips

1. **Recognition Speed:**
   - Fewer enrolled students = faster recognition
   - Consider limiting to active students only

2. **Camera Settings:**
   - Lower resolution = faster processing
   - Default OpenCV resolution is usually fine

3. **Tolerance Tuning:**
   - Start with default (0.6)
   - Adjust based on your environment
   - Test with multiple students

## Troubleshooting Checklist

- [ ] API server is running (`curl http://localhost:8000/health`)
- [ ] Students are enrolled (`ls data/face_encodings/`)
- [ ] Camera permissions granted (macOS Settings)
- [ ] Camera not used by other apps
- [ ] Good lighting conditions
- [ ] Face is front-facing and clearly visible
- [ ] Tolerance is appropriate (try 0.5-0.7)
- [ ] Network connectivity to API

## Getting Help

If issues persist:

1. Check API server logs
2. Verify face encoding files exist and are valid
3. Test camera with simple OpenCV script
4. Test API endpoints with curl/Postman
5. Review error messages carefully - they usually indicate the issue

## Example Output

**Successful Recognition:**
```
✅ Loaded 5 student face encodings

Room: Room512, Class: Class1
Looking for faces... Press 'q' to quit

🎯 Recognizing: John Doe (CS23-001)
   Confidence: 87.45%
✅ Attendance marked successfully!
   Student: John Doe (CS23-001)
   Room: Room512, Class: Class1
   Date: 2024-01-19, Time: 2024-01-19T10:30:00
```

**Error Example:**
```
❌ Error marking attendance: 404 Client Error: Not Found
   Response: {"detail":"Student not found"}
```

---

For more information, see the main [README.md](../README.md) file.
