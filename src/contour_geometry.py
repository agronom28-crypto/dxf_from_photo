from pathlib import Path
import cv2
import numpy as np


def _load(path):
    data = np.fromfile(str(path), dtype=np.uint8)
    return cv2.imdecode(data, cv2.IMREAD_COLOR)


def extract_outline(path, roi):
    image = _load(Path(path))
    x0, y0, width, height = map(int, roi)
    fallback = {"points": [[0, 0], [1, 0], [1, 1], [0, 1]], "bbox": [x0, y0, width, height], "confidence": 0.0}
    if image is None or width < 10 or height < 10:
        return fallback
    crop = image[y0:y0 + height, x0:x0 + width]
    if crop.size == 0:
        return fallback
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0.7)
    edges = cv2.Canny(gray, 45, 135)
    scale = max(1, int(round(min(width, height) / 350)))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * scale + 1, 2 * scale + 1))
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    if not contours:
        return fallback
    viable = []
    roi_area = float(width * height)
    for candidate in contours:
        area = abs(cv2.contourArea(candidate))
        bx, by, bw, bh = cv2.boundingRect(candidate)
        if area < roi_area * 0.025 or bw < width * 0.15 or bh < height * 0.15:
            continue
        border_penalty = 0.65 if bx <= 1 and by <= 1 and bx + bw >= width - 1 and by + bh >= height - 1 else 1.0
        viable.append((area * border_penalty, candidate, (bx, by, bw, bh)))
    if not viable:
        return fallback
    _, selected, (bx, by, bw, bh) = max(viable, key=lambda item: item[0])
    perimeter = cv2.arcLength(selected, True)
    epsilon = max(0.75, perimeter * 0.00065)
    approximation = cv2.approxPolyDP(selected, epsilon, True).reshape(-1, 2)
    while len(approximation) > 700:
        epsilon *= 1.25
        approximation = cv2.approxPolyDP(selected, epsilon, True).reshape(-1, 2)
    if len(approximation) < 4 or bw < 2 or bh < 2:
        return fallback
    points = [[round((float(px) - bx) / bw, 7), round(1.0 - (float(py) - by) / bh, 7)] for px, py in approximation]
    confidence = min(1.0, abs(cv2.contourArea(selected)) / max(1.0, float(bw * bh)))
    return {"points": points, "bbox": [x0 + bx, y0 + by, bw, bh], "confidence": round(confidence, 4)}
