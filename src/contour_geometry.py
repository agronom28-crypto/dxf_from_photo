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
    gray = cv2.GaussianBlur(cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY), (3, 3), 0.7)
    edges = cv2.Canny(gray, 45, 135)
    scale = max(1, int(round(min(width, height) / 350)))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * scale + 1, 2 * scale + 1))
    edges = cv2.morphologyEx(edges, cv2.MORPH_CLOSE, kernel, iterations=2)
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_NONE)
    viable = []
    for candidate in contours:
        area = abs(cv2.contourArea(candidate))
        bx, by, bw, bh = cv2.boundingRect(candidate)
        if area >= width * height * 0.025 and bw >= width * 0.15 and bh >= height * 0.15:
            viable.append((area, candidate, (bx, by, bw, bh)))
    if not viable:
        return fallback
    _, selected, (bx, by, bw, bh) = max(viable, key=lambda item: item[0])
    perimeter = cv2.arcLength(selected, True)
    approximation = cv2.approxPolyDP(selected, max(0.75, perimeter * 0.001), True).reshape(-1, 2)
    if len(approximation) < 4:
        return fallback
    points = [[round((float(px) - bx) / bw, 7), round(1 - (float(py) - by) / bh, 7)] for px, py in approximation]
    confidence = min(1.0, abs(cv2.contourArea(selected)) / max(1.0, float(bw * bh)))
    return {"points": points, "bbox": [x0 + bx, y0 + by, bw, bh], "confidence": round(confidence, 4)}


def _rectangle(width, height):
    return [(0.0, 0.0), (width, 0.0), (width, height), (0.0, height)]


def _scaled_points(measurements, width, height):
    raw = measurements.get("contour_points") or measurements.get("points") or []
    points = []
    for point in raw:
        if isinstance(point, (list, tuple)) and len(point) >= 2:
            x, y = float(point[0]), float(point[1])
            points.append((x * width, y * height) if -0.05 <= x <= 1.05 and -0.05 <= y <= 1.05 else (x, y))
    return points


def _looks_rectangular(points, width, height):
    if len(points) < 4:
        return True
    corners = ((0, 0), (width, 0), (width, height), (0, height))
    tolerance = max(width, height) * 0.055
    return all(min((x - cx) ** 2 + (y - cy) ** 2 for x, y in points) ** 0.5 <= tolerance for cx, cy in corners)


def _capsule(width, height, segments=24):
    if width < height:
        return [(y, x) for x, y in _capsule(height, width, segments)]
    radius = height / 2
    left, right = radius, width - radius
    points = []
    for angle in np.linspace(90, 270, segments, endpoint=False):
        radians = np.deg2rad(angle); points.append((left + radius * np.cos(radians), radius + radius * np.sin(radians)))
    for angle in np.linspace(-90, 90, segments, endpoint=False):
        radians = np.deg2rad(angle); points.append((right + radius * np.cos(radians), radius + radius * np.sin(radians)))
    return points


def build_contour_from_measurements(measurements):
    width, height = float(measurements["width"]), float(measurements["height"])
    points = _scaled_points(measurements, width, height)
    mode = measurements.get("cutout_mode", "Без открытых вырезов")
    if mode == "С открытыми вырезами" and len(points) >= 4:
        return points
    if _looks_rectangular(points, width, height):
        return _rectangle(width, height)
    if max(width, height) >= min(width, height) * 1.25:
        return _capsule(width, height)
    return _rectangle(width, height)
