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

# Relaxed thresholds — important for screen-to-camera scenario
OCR_CONFIDENCE_THRESHOLD = 0.15       # Very lenient — screen degrades quality
FRAME_CONFIRMATION_THRESHOLD = 1      # Single read is enough
OCR_INTERVAL = 5                      # Dashcam mode only

print("[ANPR] Initializing EasyOCR (English)...")
try:
    reader = easyocr.Reader(['en'], gpu=False)
    print("[ANPR] EasyOCR ready.")
except Exception as e:
    print(f"[ANPR] EasyOCR init failed: {e}")
    reader = None

_vehicle_ocr_history = defaultdict(lambda: defaultdict(list))
_confirmed_plates = {}

try:
    from ultralytics import YOLO
    if os.path.exists(PLATE_MODEL_PATH):
        plate_model = YOLO(PLATE_MODEL_PATH)
        print(f"[ANPR] Loaded plate model from {PLATE_MODEL_PATH}")
    else:
        plate_model = None
except Exception:
    plate_model = None


# --------------------------------------------------
# 2. Screen-aware preprocessing
# --------------------------------------------------

def _preprocess_for_screen(img):
    """
    Preprocessing optimised for text visible on a screen captured through a mobile camera.
    Handles moiré, glare, and low contrast.
    """
    # Aggressive upscale — plate area might only be 30px wide through camera→screen
    h, w = img.shape[:2]
    # Target: at least 400px wide
    scale = max(3.0, 400.0 / max(w, 1))
    img = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_LANCZOS4)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)

    # Gaussian blur FIRST to kill moiré pattern from screen
    denoised = cv2.GaussianBlur(gray, (3, 3), 0)

    # Sharpen with unsharp mask
    blurred = cv2.GaussianBlur(denoised, (0, 0), 3)
    sharpened = cv2.addWeighted(denoised, 1.5, blurred, -0.5, 0)

    # CLAHE for contrast
    clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(4, 4))
    enhanced = clahe.apply(sharpened)

    return enhanced


def _preprocess_variants(img):
    """Return list of preprocessed images to try."""
    h, w = img.shape[:2]
    scale = max(3.0, 400.0 / max(w, 1))
    big = cv2.resize(img, (int(w * scale), int(h * scale)), interpolation=cv2.INTER_LANCZOS4)
    gray = cv2.cvtColor(big, cv2.COLOR_BGR2GRAY)

    results = []

    # Variant 0: Screen-optimised (moiré removal + sharpen + CLAHE)
    denoised = cv2.GaussianBlur(gray, (3, 3), 0)
    blurred = cv2.GaussianBlur(denoised, (0, 0), 3)
    sharpened = cv2.addWeighted(denoised, 1.5, blurred, -0.5, 0)
    clahe = cv2.createCLAHE(clipLimit=4.0, tileGridSize=(4, 4))
    results.append(clahe.apply(sharpened))

    # Variant 1: Adaptive threshold
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    results.append(cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2))

    # Variant 2: Otsu
    _, t = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    results.append(t)

    # Variant 3: Inverted Otsu (for dark plate on light bg)
    _, t = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    results.append(t)

    return results


# --------------------------------------------------
# 3. Plate validation
# --------------------------------------------------

def validate_indian_plate(raw_text):
    """Clean and validate license plate text. Supports Indian, EU, and generic formats."""
    clean = re.sub(r'[^A-Z0-9]', '', raw_text.upper())

    # Accept plates 4–12 characters long
    if not (4 <= len(clean) <= 12):
        return None

    # Must contain BOTH letters AND digits (at least 1 of each)
    letters = re.findall(r'[A-Z]', clean)
    digits = re.findall(r'[0-9]', clean)
    if len(letters) < 1 or len(digits) < 1:
        return None

    # Reject repetitive characters like "AAAAA" or "121212"
    if len(set(clean)) < 3:
        return None

    # Reject web UI / website background text words
    blacklist_words = [
        "STOCK", "ROYALTY", "FREEPIK", "DOWNLOAD", "ATTRIBUTION", "RESOURCE",
        "YOUTUBE", "GOOGLE", "CHROME", "POTHOLE", "DETECT", "LIVE", "MODEL",
        "MOBILE", "CAMERA", "SCREEN", "DESKTOP", "CANCEL", "SUBMIT", "BUTTON",
        "HEADER", "FOOTER", "CLICK", "IMAGE", "PHOTO", "VECTOR",
        "SHUTTER", "ADOBE", "UNSPLASH", "PEXELS", "GITHUB", "FLATICON",
        "SUBSCRIBE", "SHARE", "LIKE", "COMMENT", "ELEMENT", "SEARCH", "REQUIRED",
        "INFO", "SYSTEM", "REPORT", "ALERT", "DASHBOARD", "INTEL", "URBAN", "ROAD"
    ]
    for bw in blacklist_words:
        if bw in clean:
            return None

    # --- Format checks (most specific first) ---

    # 1. Standard Indian state plate: e.g. DL3CCE1234, MH12AB1234, KA05M9999
    states = r'(DL|MH|KA|HR|UP|TN|TS|GJ|RJ|KL|WB|BR|MP|AP|OD|PB|CH|GA|JK|UK|PY|AN|DD|DN|LD|NL|MN|TR|ML|MZ|SK|HP|JH|CG)'
    if re.match(r'^' + states + r'\d{1,2}[A-Z]{1,3}\d{1,4}$', clean):
        return clean

    # 2. BH Series: e.g. 22BH1234AB
    if re.match(r'^\d{2}BH\d{4}[A-Z]{1,2}$', clean):
        return clean

    # 3. EU/Intl formats: e.g. 6934FMR, 9916GHS, AB1234, 1234ABC, ABC123
    if re.match(r'^\d{3,4}[A-Z]{2,4}$', clean):   # e.g. 6934FMR
        return clean
    if re.match(r'^[A-Z]{2,4}\d{3,4}$', clean):   # e.g. FMR6934
        return clean
    if re.match(r'^[A-Z]{1,3}\d{3,4}[A-Z]{1,3}$', clean):  # e.g. AB1234CD
        return clean
    if re.match(r'^[A-Z]\d{3,4}[A-Z]{2,3}$', clean):  # e.g. E9916GHS (EU with country prefix)
        return clean

    # 4. Generic fallback: mix of digits + letters, length 4-10
    if 4 <= len(clean) <= 10 and len(digits) >= 2 and len(letters) >= 2:
        return clean

    return None


# --------------------------------------------------
# 4. OCR runner
# --------------------------------------------------

def run_ocr(image, combine=True):
    """Run EasyOCR and return (text, confidence) if combine=True, else raw results list."""
    if reader is None or image is None or image.size == 0:
        return (None, 0.0) if combine else []
    try:
        results = reader.readtext(
            image,
            allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',
            detail=1,
            paragraph=False,
            min_size=3,
            text_threshold=0.4,
            low_text=0.3,
        )
    except Exception as e:
        return (None, 0.0) if combine else []

    if not results:
        return (None, 0.0) if combine else []

    if not combine:
        return results

    # Sort left-to-right and combine fragments
    results_sorted = sorted(results, key=lambda r: r[0][0][0])
    combined_text = "".join(t for (_, t, _) in results_sorted)
    avg_conf = sum(c for (_, _, c) in results_sorted) / len(results_sorted)
    return combined_text, avg_conf


# --------------------------------------------------
# 5. Full-frame plate scan (primary for mobile/screen use)
# --------------------------------------------------

def scan_full_frame_for_plates(frame):
    """
    Scan the entire frame for any Indian-format plate text.
    More reliable than vehicle-crop approach when plate size is small.
    Returns list of (plate_text, confidence) tuples.
    """
    if frame is None or frame.size == 0:
        return []

    found = []
    for processed in _preprocess_variants(frame):
        ocr_results = run_ocr(processed, combine=False)
        for _, raw, conf in ocr_results:
            if not raw or conf < OCR_CONFIDENCE_THRESHOLD:
                continue
            
            # Try the whole block
            clean = validate_indian_plate(raw)
            if clean:
                found.append((clean, conf))
                
            # Try splitting it in case multiple words got grouped
            for chunk in re.split(r'[\s\-_]+', raw):
                if len(chunk) >= 4:  # lowered from >4 to >=4 to catch short plates
                    clean_chunk = validate_indian_plate(chunk)
                    if clean_chunk:
                        found.append((clean_chunk, conf))

    # Deduplicate by plate text, keep highest conf
    best = {}
    for plate, conf in found:
        if plate not in best or conf > best[plate]:
            best[plate] = conf
    return list(best.items())


# --------------------------------------------------
# 6. Vehicle-crop scan (secondary — for dashcam mode)
# --------------------------------------------------

def _get_plate_crops(vehicle_crop):
    """Return candidate plate region crops from a vehicle bounding box."""
    h, w = vehicle_crop.shape[:2]
    candidates = []

    if plate_model is not None:
        try:
            results = plate_model(vehicle_crop, verbose=False, conf=0.20)
            for r in results:
                if r.boxes is not None:
                    for box in r.boxes:
                        px1, py1, px2, py2 = map(int, box.xyxy[0])
                        crop = vehicle_crop[py1:py2, px1:px2]
                        if crop.size > 0:
                            candidates.append(crop)
        except Exception:
            pass

    for top_frac, bot_frac in [(0.50, 0.80), (0.60, 0.95), (0.40, 0.70), (0.65, 1.0)]:
        y1 = int(h * top_frac)
        y2 = int(h * bot_frac)
        crop = vehicle_crop[y1:y2, :]
        if crop.size > 0:
            candidates.append(crop)

    return candidates


def process_vehicle(vehicle_crop, track_id):
    """
    Process a vehicle crop for plate detection (dashcam mode).
    For mobile/screen mode, prefer scan_full_frame_for_plates().
    """
    if vehicle_crop is None or vehicle_crop.size == 0:
        return None
    if track_id in _confirmed_plates:
        return None

    best_text = None
    best_conf = 0.0

    for crop in _get_plate_crops(vehicle_crop):
        for processed in _preprocess_variants(crop):
            raw, conf = run_ocr(processed)
            if not raw:
                continue
            clean = validate_indian_plate(raw)
            if clean and conf > best_conf:
                best_conf = conf
                best_text = clean

    if best_text is None or best_conf < OCR_CONFIDENCE_THRESHOLD:
        return None

    _vehicle_ocr_history[track_id][best_text].append(best_conf)
    reads = _vehicle_ocr_history[track_id][best_text]
    if len(reads) >= FRAME_CONFIRMATION_THRESHOLD:
        avg_conf = sum(reads) / len(reads)
        _confirmed_plates[track_id] = {"plate_number": best_text, "confidence": avg_conf}
        print(f"[ANPR] ✅ Vehicle {track_id} CONFIRMED plate: {best_text} (Conf: {avg_conf:.2f})")
        return _confirmed_plates[track_id]
    return None


def get_confirmed_plate(track_id):
    return _confirmed_plates.get(track_id)


def reset_anpr_state():
    _vehicle_ocr_history.clear()
    _confirmed_plates.clear()
