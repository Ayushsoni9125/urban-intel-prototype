"""
test_anpr.py
------------
Run this to diagnose the ANPR pipeline step by step.
Usage: python detection/test_anpr.py <path_to_image>
       python detection/test_anpr.py  (uses webcam snapshot)
"""
import sys
import os
import cv2
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

print("=" * 60)
print("ANPR PIPELINE DIAGNOSTIC")
print("=" * 60)

# ── 1. Load image ───────────────────────────────────────────
if len(sys.argv) > 1:
    img_path = sys.argv[1]
    frame = cv2.imread(img_path)
    if frame is None:
        print(f"[ERROR] Cannot load image: {img_path}")
        sys.exit(1)
    print(f"[OK]  Loaded image: {img_path}  shape={frame.shape}")
else:
    # Try to grab a single webcam frame
    cap = cv2.VideoCapture(0)
    ret, frame = cap.read()
    cap.release()
    if not ret:
        print("[ERROR] No image path given and webcam not available.")
        print("Usage: python detection/test_anpr.py <image.jpg>")
        sys.exit(1)
    print(f"[OK]  Captured webcam frame  shape={frame.shape}")

# ── 2. Vehicle detection ─────────────────────────────────────
print("\n[STEP 1] Vehicle Detection (yolov8n.pt)")
try:
    from ultralytics import YOLO
    model_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "yolov8n.pt")
    if not os.path.exists(model_path):
        print(f"[WARN]  yolov8n.pt not found at {model_path}")
        vehicle_boxes = []
    else:
        model = YOLO(model_path)
        results = model(frame, verbose=False, conf=0.25)
        TARGET = {2: "car", 3: "motorcycle", 5: "bus", 7: "truck"}
        vehicle_boxes = []
        for r in results:
            if r.boxes is not None:
                for box in r.boxes:
                    cls_id = int(box.cls[0])
                    if cls_id in TARGET:
                        x1, y1, x2, y2 = map(int, box.xyxy[0])
                        conf = float(box.conf[0])
                        vehicle_boxes.append((x1, y1, x2, y2, TARGET[cls_id], conf))
        print(f"[OK]  Found {len(vehicle_boxes)} vehicle(s): {[(v[4], f'{v[5]:.2f}') for v in vehicle_boxes]}")
except Exception as e:
    print(f"[ERROR] YOLO failed: {e}")
    vehicle_boxes = []

# If no vehicles found, treat the whole frame as a "vehicle" for plate testing
if not vehicle_boxes:
    h, w = frame.shape[:2]
    vehicle_boxes = [(0, 0, w, h, "whole_frame", 1.0)]
    print("[INFO]  No vehicles detected. Testing OCR on full frame instead.")

# ── 3. For each vehicle, test plate crops + OCR ───────────────
print("\n[STEP 2] Plate Crop + OCR")

try:
    import easyocr
    reader = easyocr.Reader(['en'], gpu=False)
    print("[OK]  EasyOCR loaded.")
except Exception as e:
    print(f"[ERROR] EasyOCR failed to load: {e}")
    sys.exit(1)

def preprocess(img, mode):
    h, w = img.shape[:2]
    scale = max(1.0, 200.0 / h)
    img = cv2.resize(img, (int(w * scale * 2), int(h * scale * 2)), interpolation=cv2.INTER_CUBIC)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    if mode == 0:
        blur = cv2.bilateralFilter(gray, 9, 75, 75)
        clahe = cv2.createCLAHE(clipLimit=3.0, tileGridSize=(8, 8))
        return clahe.apply(blur)
    elif mode == 1:
        blur = cv2.GaussianBlur(gray, (5, 5), 0)
        return cv2.adaptiveThreshold(blur, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY, 11, 2)
    elif mode == 2:
        _, t = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
        return t
    else:
        _, t = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
        return t

mode_names = ["CLAHE+Bilateral", "AdaptiveThresh", "Otsu", "OtsuInvert"]

for vi, (x1, y1, x2, y2, vtype, vconf) in enumerate(vehicle_boxes):
    print(f"\n  Vehicle #{vi+1}: {vtype} (conf={vconf:.2f})  box=({x1},{y1},{x2},{y2})")
    vehicle_crop = frame[y1:y2, x1:x2]
    h, w = vehicle_crop.shape[:2]

    # Try multiple crop zones
    crop_zones = [
        ("bottom 55-85%", int(h*0.55), int(h*0.85)),
        ("bottom 65-100%", int(h*0.65), h),
        ("bottom 45-75%", int(h*0.45), int(h*0.75)),
        ("bottom 70-100%", int(h*0.70), h),
    ]

    best_result = None
    best_conf = 0.0

    for zone_name, zy1, zy2 in crop_zones:
        crop = vehicle_crop[zy1:zy2, :]
        if crop.size == 0:
            continue

        for mode in range(4):
            try:
                processed = preprocess(crop, mode)
            except Exception as e:
                continue

            try:
                ocr_results = reader.readtext(
                    processed,
                    allowlist='ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789',
                    detail=1,
                    paragraph=False,
                    min_size=5,
                )
            except Exception as e:
                continue

            if ocr_results:
                combined = "".join(t for (_, t, _) in ocr_results)
                avg_conf = sum(c for (_, _, c) in ocr_results) / len(ocr_results)
                print(f"    [{zone_name}] [{mode_names[mode]}] → '{combined}' (conf={avg_conf:.2f})")
                if avg_conf > best_conf:
                    best_conf = avg_conf
                    best_result = combined
            else:
                print(f"    [{zone_name}] [{mode_names[mode]}] → (no text detected)")

    if best_result:
        print(f"  ✅ Best OCR result: '{best_result}' (conf={best_conf:.2f})")
    else:
        print(f"  ❌ No text detected across all crops/preprocessing variants")

print("\n" + "=" * 60)
print("DIAGNOSIS COMPLETE")
print("=" * 60)
print("\nTips:")
print("  - If 'no vehicles detected': your image doesn't show a clear car/truck")
print("  - If 'no text detected': plate is too far, blurry, or at bad angle")
print("  - If text is detected but wrong: OCR confusion, try closer shot")
print("  - Save a test image from mobile camera and run: python detection/test_anpr.py <image.jpg>")
