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

PLATE_MODEL_PATH = os.environ.get("PLATE_MODEL_PATH", os.path.join(_THIS_DIR, "models", "plate_model.pt"))

# Lowered thresholds for real-world mobile capture
OCR_CONFIDENCE_THRESHOLD = 0.25       # Accept weaker OCR reads
FRAME_CONFIRMATION_THRESHOLD = 1      # Single confirmed read is enough for mobile
OCR_INTERVAL = 5                      # Run ANPR every 5th frame in dashcam mode

# Initialize EasyOCR reader
print("[ANPR] Initializing EasyOCR (English)...")
try:
    reader = easyocr.Reader(
        ['en'],
        gpu=False,
        # Allow lower-detail detection — faster and still works for plates
        detect_network="craft",
        recognizer_network="standard"
    )
    print("[ANPR] EasyOCR ready.")
except Exception as e:
    print(f"[ANPR] EasyOCR init failed: {e}")
    reader = None

# Track OCR results per track_id
_vehicle_ocr_history = defaultdict(lambda: defaultdict(list))
_confirmed_plates = {}

# Load optional plate YOLO model
try:
    from ultralytics import YOLO
    if os.path.exists(PLATE_MODEL_PATH):
        plate_model = YOLO(PLATE_MODEL_PATH)
        print(f"[ANPR] Loaded plate model from {PLATE_MODEL_PATH}")
    else:
        plate_model = None
        print(f"[ANPR] No plate model found. Using multi-crop fallback.")
except Exception:
    plate_model = None


# --------------------------------------------------
# 2. Preprocessing variants
# --------------------------------------------------

def _preprocess_variant(img, mode):
    """Return a preprocessed copy of img according to mode (0-3)."""
    # Upscale first — bigger image = better OCR
    h, w = img.shape[:2]
    scale = max(1.0, 200.0 / h)  # ensure height is at least 200px
    img = cv2.resize(img, (int(w * scale * 2), int(h * scale * 2)), interpolation=cv2.INTER_CUBIC)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    if mode == 0:
        # CLAHE + bilateral — general purpose
        blur = cv2.bilateralFilter(gray, 9, 75, 75)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        return clahe.apply(blur)

    elif mode == 1:
        # Adaptive threshold — works well for low contrast / shadows
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        return cv2.adaptiveThreshold(
            blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2
        )

    elif mode == 2:
        # Otsu binarization
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return thresh

    elif mode == 3:
        # Inverted Otsu — for dark plates with light text
        _, thresh = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        return thresh

    return gray


# --------------------------------------------------
# 3. Plate region candidates
# --------------------------------------------------

def _get_plate_crops(vehicle_crop):
    """
    Return a list of candidate plate crop images from the vehicle crop.
    Tries multiple vertical regions since plate position varies by vehicle type.
    """
    h, w = vehicle_crop.shape[:2]
    candidates = []

    if plate_model is not None:
        try:
            results = plate_model(vehicle_crop, verbose=False, conf=0.20)
            for r in results:
                if r.boxes is not None and len(r.boxes) > 0:
                    for box in r.boxes:
                        px1, py1, px2, py2 = map(int, box.xyxy[0])
                        crop = vehicle_crop[py1:py2, px1:px2]
                        if crop.size > 0:
                            candidates.append(crop)
        except Exception:
            pass

    # Always add rule-based fallback crops even if model returned something
    for top_frac, bot_frac in [(0.55, 0.85), (0.65, 1.0), (0.45, 0.75), (0.70, 1.0)]:
        y1 = int(h * top_frac)
        y2 = int(h * bot_frac)
        crop = vehicle_crop[y1:y2, :]
        if crop.size > 0:
            candidates.append(crop)

    return candidates


# --------------------------------------------------
# 4. OCR runner
# --------------------------------------------------

def run_ocr(image):
    """
    Run EasyOCR on a preprocessed image.
    Returns (combined_text, best_confidence).
    """
    if reader is None or image is None or image.size == 0:
        return None, 0.0

    try:
        results = reader.readtext(
            image,
            allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',
            detail=1,
            paragraph=False,
            min_size=5,
        )
    except Exception as e:
        print(f"[ANPR] OCR error: {e}")
        return None, 0.0

    if not results:
        return None, 0.0

    # Combine all text fragments (left-to-right by x position)
    results_sorted = sorted(results, key=lambda r: r[0][0][0])
    combined_text = "".join(t for (_, t, _) in results_sorted)
    avg_conf = sum(c for (_, _, c) in results_sorted) / len(results_sorted)

    # Also pick single best token in case combining hurts
    best_text, best_conf = max(results, key=lambda r: r[2])[1], max(results, key=lambda r: r[2])[2]

    # Return whichever gives a valid plate
    return combined_text, avg_conf


# --------------------------------------------------
# 5. Validation
# --------------------------------------------------

def validate_indian_plate(raw_text):
    """
    Clean and loosely validate an Indian-format number plate.
    Returns cleaned text if valid, else None.
    """
    clean = re.sub(r'[^A-Z0-9]', '', raw_text.upper())

    # Must be 5–13 chars (loose — OCR often misses/adds a char)
    if not (5 <= len(clean) <= 13):
        return None

    # Must contain at least one letter AND one digit
    if not re.search(r'[A-Z]', clean) or not re.search(r'[0-9]', clean):
        return None

    # Reject garbage like "AAAAAAA" or "0000000"
    if len(set(clean)) < 3:
        return None

    return clean


# --------------------------------------------------
# 6. Main entry point
# --------------------------------------------------

def process_vehicle(vehicle_crop, track_id):
    """
    Try every combination of crop region × preprocessing variant.
    Return confirmed plate dict if consensus reached, else None.
    """
    if vehicle_crop is None or vehicle_crop.size == 0:
        return None

    # Already confirmed for this track — skip re-processing
    if track_id in _confirmed_plates:
        return None

    plate_crops = _get_plate_crops(vehicle_crop)

    best_text = None
    best_conf = 0.0

    for crop in plate_crops:
        for mode in range(4):
            try:
                processed = _preprocess_variant(crop, mode)
            except Exception:
                continue

            raw_text, conf = run_ocr(processed)
            if not raw_text:
                continue

            clean = validate_indian_plate(raw_text)
            if not clean:
                continue

            if conf > best_conf:
                best_conf = conf
                best_text = clean

    if best_text is None or best_conf < OCR_CONFIDENCE_THRESHOLD:
        return None

    # Multi-frame consensus
    _vehicle_ocr_history[track_id][best_text].append(best_conf)

    reads = _vehicle_ocr_history[track_id][best_text]
    if len(reads) >= FRAME_CONFIRMATION_THRESHOLD:
        avg_conf = sum(reads) / len(reads)
        _confirmed_plates[track_id] = {
            "plate_number": best_text,
            "confidence": avg_conf
        }
        print(f"[ANPR] ✅ Vehicle {track_id} CONFIRMED plate: {best_text} (Conf: {avg_conf:.2f})")
        return _confirmed_plates[track_id]

    return None


def get_confirmed_plate(track_id):
    """Return the confirmed plate for a track_id if it exists."""
    return _confirmed_plates.get(track_id)


def reset_anpr_state():
    """Clear all tracking history (for demo reset)."""
    _vehicle_ocr_history.clear()
    _confirmed_plates.clear()
