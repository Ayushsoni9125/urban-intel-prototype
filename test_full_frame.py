import cv2
import sys
from detection.anpr import scan_full_frame_for_plates, _preprocess_variants, run_ocr

img = cv2.imread(sys.argv[1])
print("Scanning full frame for plates...")
plates = scan_full_frame_for_plates(img)
print("Detected plates:", plates)

print("Raw OCR results for all variants:")
for i, processed in enumerate(_preprocess_variants(img)):
    raw, conf = run_ocr(processed)
    print(f"Variant {i}: '{raw}' (conf={conf})")
