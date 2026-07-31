"""
Строит черновой DXF-контур по фотографии эскиза.

ВНИМАНИЕ: результат приблизительный. Контур получен автоматическим
распознаванием линий на фото и НЕ подтверждён точными размерами.
Перед резкой на ЧПУ размеры обязательно должен проверить оператор.

Использование:
    python photo_to_draft_dxf.py <путь_к_фото> <путь_к_dxf> [--scale-mm=1830]
"""
import sys
import argparse
import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None

from geometry import DxfBuilder


def load_and_preprocess(image_path):
    if cv2 is None:
        raise RuntimeError("Требуется opencv-python: pip install opencv-python")
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Не удалось открыть изображение: {image_path}")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (5, 5), 0)
    thresh = cv2.adaptiveThreshold(
        gray, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 25, 10
    )
    return img, thresh


def find_main_contour(thresh):
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        raise RuntimeError("Контур на фото не найден. Проверьте освещение и контраст фото.")
    largest = max(contours, key=cv2.contourArea)
    epsilon = 0.002 * cv2.arcLength(largest, True)
    approx = cv2.approxPolyDP(largest, epsilon, True)
    return approx.reshape(-1, 2)


def scale_points(points, target_width_mm):
    xs = points[:, 0].astype(float)
    ys = points[:, 1].astype(float)
    w = xs.max() - xs.min()
    h = ys.max() - ys.min()
    if w == 0:
        raise RuntimeError("Некорректный контур: нулевая ширина.")
    scale = target_width_mm / w
    xs = (xs - xs.min()) * scale
    ys = (ys.max() - ys) * scale  # инверсия оси Y (в изображении Y растёт вниз)
    return xs, ys


def build_draft_dxf(image_path, dxf_path, target_width_mm):
    _, thresh = load_and_preprocess(image_path)
    points = find_main_contour(thresh)
    xs, ys = scale_points(points, target_width_mm)

    builder = DxfBuilder()
    poly = list(zip(xs.tolist(), ys.tolist()))
    builder.polyline(poly, layer="CUT", closed=True)
    builder.text(0, ys.max() + 40, "DRAFT - NOT VERIFIED - DO NOT USE FOR CUTTING", 18, 0, "TEXT")
    builder.text(0, ys.max() + 15, f"Auto width: {target_width_mm:.0f} mm (assumed)", 14, 0, "TEXT")
    builder.save(dxf_path)
    return dxf_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("image", help="Путь к фото эскиза")
    parser.add_argument("output", help="Путь для сохранения draft.dxf")
    parser.add_argument(
        "--scale-mm", type=float, default=1000.0,
        help="Известная ширина детали в мм для масштабирования (обязательно задать вручную)"
    )
    args = parser.parse_args()

    path = build_draft_dxf(args.image, args.output, args.scale_mm)
    print(f"Черновой DXF сохранён: {path}")
    print("ВНИМАНИЕ: проверьте контур и размеры перед использованием на ЧПУ.")


if __name__ == "__main__":
    main()
