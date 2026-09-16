import os
import cv2
import re
import numpy as np
from collections import defaultdict
import easyocr

# --------------------------------------------------
# 1. Configuration
# --------------------------------------------------
_THIS_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.dirname(_THIS_DIR)

# Example placeholder for a future YOLO plate model
PLATE_MODEL_PATH = os.environ.get("PLATE_MODEL_PATH", os.path.join(_THIS_DIR, "models", "plate_model.pt"))

OCR_CONFIDENCE_THRESHOLD = 0.50
FRAME_CONFIRMATION_THRESHOLD = 2  # Needs to be seen 2 times consistently
OCR_INTERVAL = 5  # Run ANPR every 5th frame for a given vehicle (or overall)

# Initialize EasyOCR reader (loads weights on first run)
print("[ANPR] Initializing EasyOCR (English)...")
try:
    reader = easyocr.Reader(['en'], gpu=False) # Fallback to CPU for general compatibility on mac
except Exception as e:
    print(f"[ANPR] EasyOCR init failed: {e}")
    reader = None

# Track OCR results over multiple frames for each track_id
# Format: { track_id: { "plate_string": [confidence1, confidence2, ...], ... } }
_vehicle_ocr_history = defaultdict(lambda: defaultdict(list))
_confirmed_plates = {} # track_id -> {"plate_number": str, "confidence": float}

# If a plate model exists, load it
try:
    from ultralytics import YOLO
    if os.path.exists(PLATE_MODEL_PATH):
        plate_model = YOLO(PLATE_MODEL_PATH)
        print(f"[ANPR] Loaded plate model from {PLATE_MODEL_PATH}")
    else:
        plate_model = None
        print(f"[ANPR] No plate model found at {PLATE_MODEL_PATH}. Using bottom 30% crop fallback.")
except Exception:
    plate_model = None


def preprocess_plate(plate_img):
    """
    Preprocess the cropped plate image to improve OCR accuracy.
    """
    if plate_img is None or plate_img.size == 0:
        return None
    
    # Resize to make text larger for OCR
    plate_img = cv2.resize(plate_img, None, fx=2.0, fy=2.0, interpolation=cv2.INTER_CUBIC)
    
    # Grayscale
    gray = cv2.cvtColor(plate_img, cv2.COLOR_BGR2GRAY)
    
    # Bilateral filter for denoising while keeping edges sharp
    blur = cv2.bilateralFilter(gray, 11, 17, 17)
    
    # CLAHE for contrast improvement
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8,8))
    enhanced = clahe.apply(blur)
    
    return enhanced


def validate_indian_plate(raw_text):
    """
    Cleans up the raw OCR text and checks if it loosely matches an Indian format.
    Example: UP14AB1234
    """
    # Remove spaces and non-alphanumeric chars
    clean_text = re.sub(r'[^A-Z0-9]', '', raw_text.upper())
    
    # Simple length check (usually 8 to 10 characters for Indian plates)
    # E.g., DL8CAA1111 (10), MH12AB1234 (10), UP14Z1234 (9)
    if 6 <= len(clean_text) <= 12:
        # A very basic regex for typical Indian plate format: 2 letters, 1-2 digits, 1-3 letters, 4 digits
        # This is relaxed because OCR makes mistakes (e.g. interpreting '8' as 'B')
        # We just return the clean text if it passes basic length
        return clean_text
    
    return None


def run_ocr(image):
    """
    Run EasyOCR on the preprocessed image.
    Returns (best_text, confidence).
    """
    if reader is None or image is None:
        return None, 0.0

    results = reader.readtext(image)
    if not results:
        return None, 0.0

    # Combine text if multiple boxes are found, or just take the most confident one
    # For number plates, usually one main box is the plate number
    best_text = ""
    best_conf = 0.0
    
    for (bbox, text, prob) in results:
        if prob > best_conf:
            best_conf = prob
            best_text = text

    return best_text, best_conf


def process_vehicle(vehicle_crop, track_id):
    """
    Process a vehicle crop to find and read the number plate.
    Returns a confirmed plate dict if consensus is reached, else None.
    """
    if vehicle_crop is None or vehicle_crop.size == 0:
        return None

    # 1. Plate Detection
    plate_crop = None
    if plate_model is not None:
        # Run YOLO plate model
        results = plate_model(vehicle_crop, verbose=False, conf=0.25)
        for r in results:
            if r.boxes is not None and len(r.boxes) > 0:
                # Take the highest confidence plate
                box = r.boxes[0]
                px1, py1, px2, py2 = map(int, box.xyxy[0])
                plate_crop = vehicle_crop[py1:py2, px1:px2]
                break
    
    # Fallback: Crop bottom 30% of vehicle
    if plate_crop is None:
        h, w = vehicle_crop.shape[:2]
        crop_h = int(h * 0.3)
        plate_crop = vehicle_crop[h - crop_h : h, :]

    if plate_crop is None or plate_crop.size == 0:
        return None

    # 2. Preprocessing
    processed_img = preprocess_plate(plate_crop)

    # 3. OCR
    raw_text, conf = run_ocr(processed_img)
    
    if not raw_text or conf < OCR_CONFIDENCE_THRESHOLD:
        return None

    # 4. Validation & Normalization
    clean_plate = validate_indian_plate(raw_text)
    if not clean_plate:
        return None

    # 5. Multi-frame Consensus
    _vehicle_ocr_history[track_id][clean_plate].append(conf)
    
    # Check if this plate has been seen enough times
    if len(_vehicle_ocr_history[track_id][clean_plate]) >= FRAME_CONFIRMATION_THRESHOLD:
        if track_id not in _confirmed_plates:
            # Confirm it!
            avg_conf = sum(_vehicle_ocr_history[track_id][clean_plate]) / len(_vehicle_ocr_history[track_id][clean_plate])
            _confirmed_plates[track_id] = {
                "plate_number": clean_plate,
                "confidence": avg_conf
            }
            print(f"[ANPR] Vehicle {track_id} CONFIRMED plate: {clean_plate} (Conf: {avg_conf:.2f})")
            return _confirmed_plates[track_id]
        
    return None

def get_confirmed_plate(track_id):
    """Return the confirmed plate for a track_id if it exists."""
    return _confirmed_plates.get(track_id)

def reset_anpr_state():
    """Clear tracking history (useful for demo reset)."""
    _vehicle_ocr_history.clear()
    _confirmed_plates.clear()
