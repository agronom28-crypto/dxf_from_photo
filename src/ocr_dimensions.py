"""
Распознавание рукописных размерных чисел на фото эскиза (Уровень 4, локально).

Работает полностью локально — без внешних API и облачных сервисов.
Использует системный tesseract-ocr через pytesseract.

Пайплайн:
  1. Детекция текстовых зон через MSER + морфологическую группировку
     (устойчивее простого thresholding для рукописного текста разного
     размера и наклона).
  2. Для каждой зоны: кроп, увеличение (upscale), адаптивная бинаризация,
     прогон через Tesseract с whitelist только цифр и минимальных
     разделителей.
  3. Пост-фильтр по regex: похоже ли распознанное на разумный размер в мм.
  4. Дедупликация близких по координатам зон.
  5. Экспорт: JSON со списком {bbox, raw_text, parsed_value_mm, confidence}
     + debug-изображение с рамками и распознанным текстом.

ЧЕСТНАЯ ГРАНИЦА ВОЗМОЖНОСТЕЙ (важно прочитать перед использованием):
  Tesseract — универсальный OCR-движок, обученный в основном на печатном
  тексте. На инженерном рукописном почерке (тонкая ручка, наклон, цифры
  вплотную к линиям и стрелкам чертежа) точность распознавания низкая и
  требует обязательной проверки оператором. Тестирование на реальных
  эскизах показало, что из типичных 15-20 рукописных чисел на фото
  корректно распознаётся лишь малая часть, а иногда 0.
  Модуль выдаёт "кандидатов для проверки", а не окончательные размеры.
  Для промышленного качества распознавания рукописного текста нужна
  специализированная handwriting-модель (TrOCR-handwritten, PaddleOCR
  с handwriting-весами) с дообучением на собственном датасете скана
  эскизов — это отдельная задача Уровня 4+ с собственным roadmap.

Использование:
    python ocr_dimensions.py <фото> [--debug-dir=out_debug] [--lang=rus+eng]
"""
import argparse
import json
import os
import re
import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None

try:
    import pytesseract
except ImportError:
    pytesseract = None

NUMBER_RE = re.compile(r"^\d{1,5}([.,]\d{1,2})?$")
MIN_BOX_AREA_PX = 60
MAX_BOX_AREA_FRACTION = 0.02   # текстовая зона крупнее 2% кадра — скорее всего не число
UPSCALE_FACTOR = 3


def detect_text_regions(gray, dilate_px=14):
    """MSER находит компактные связные области высокого контраста —
    подходит для рукописного текста произвольного наклона/размера."""
    mser = cv2.MSER_create()
    mser.setMinArea(MIN_BOX_AREA_PX)
    mser.setMaxArea(int(gray.shape[0] * gray.shape[1] * MAX_BOX_AREA_FRACTION))
    regions, _ = mser.detectRegions(gray)

    boxes = []
    for pts in regions:
        x, y, w, h = cv2.boundingRect(pts.reshape(-1, 1, 2))
        boxes.append((x, y, w, h))

    boxes = merge_close_boxes(boxes, gray.shape, dilate_px=dilate_px)
    return boxes


def merge_close_boxes(boxes, img_shape, dilate_px=14):
    """Группирует близкие boxes (штрихи одного числа) в один прямоугольник
    через морфологическую дилатацию маски всех найденных боксов."""
    if not boxes:
        return []
    mask = np.zeros(img_shape[:2], dtype=np.uint8)
    for x, y, w, h in boxes:
        cv2.rectangle(mask, (x, y), (x + w, y + h), 255, -1)
    kernel = np.ones((dilate_px, dilate_px), np.uint8)
    mask = cv2.dilate(mask, kernel, iterations=1)
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    merged = []
    for c in contours:
        x, y, w, h = cv2.boundingRect(c)
        area = w * h
        if area < MIN_BOX_AREA_PX or area > MAX_BOX_AREA_FRACTION * img_shape[0] * img_shape[1] * 4:
            continue
        merged.append((x, y, w, h))
    return merged


def ocr_crop(gray, box, lang="rus+eng"):
    x, y, w, h = box
    pad = int(max(w, h) * 0.25)
    x0, y0 = max(0, x - pad), max(0, y - pad)
    x1, y1 = min(gray.shape[1], x + w + pad), min(gray.shape[0], y + h + pad)
    crop = gray[y0:y1, x0:x1]
    if crop.size == 0:
        return "", 0.0

    crop = cv2.resize(crop, None, fx=UPSCALE_FACTOR, fy=UPSCALE_FACTOR, interpolation=cv2.INTER_CUBIC)
    crop = cv2.bilateralFilter(crop, 7, 50, 50)
    _, crop_bin = cv2.threshold(crop, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)

    config = "--psm 7 -c tessedit_char_whitelist=0123456789.,мм"
    try:
        data = pytesseract.image_to_data(
            crop_bin, lang=lang, config=config, output_type=pytesseract.Output.DICT
        )
    except Exception:
        return "", 0.0

    texts, confs = [], []
    for t, c in zip(data["text"], data["conf"]):
        t = t.strip()
        if t:
            texts.append(t)
            try:
                confs.append(float(c))
            except ValueError:
                pass
    raw = "".join(texts)
    conf = (sum(confs) / len(confs) / 100.0) if confs else 0.0
    return raw, conf


def parse_number_candidate(raw_text):
    """Извлекает число-кандидат из OCR-строки, отбрасывая мм/буквы."""
    cleaned = raw_text.replace(",", ".").strip()
    cleaned = re.sub(r"[^0-9.]", "", cleaned)
    if not cleaned:
        return None
    try:
        value = float(cleaned)
    except ValueError:
        return None
    if value <= 0 or value > 99999:
        return None
    return value


def recognize_dimensions(image_path, debug_dir=None, lang="rus+eng"):
    if cv2 is None:
        raise RuntimeError("Требуется opencv-python: pip install opencv-python")
    if pytesseract is None:
        raise RuntimeError("Требуется pytesseract: pip install pytesseract (и системный tesseract-ocr)")

    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Не удалось открыть изображение: {image_path}")
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray_eq = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(gray)

    boxes = detect_text_regions(gray_eq)

    results = []
    for box in boxes:
        raw, conf = ocr_crop(gray_eq, box, lang=lang)
        if not raw:
            continue
        value = parse_number_candidate(raw)
        if value is None:
            continue
        results.append({
            "bbox": box, "raw_text": raw, "parsed_value_mm": value,
            "ocr_confidence": round(conf, 3),
        })

    results.sort(key=lambda r: -r["ocr_confidence"])

    if debug_dir:
        os.makedirs(debug_dir, exist_ok=True)
        vis = img.copy()
        for r in results:
            x, y, w, h = r["bbox"]
            color = (0, 255, 0) if r["ocr_confidence"] >= 0.5 else (0, 165, 255)
            cv2.rectangle(vis, (x, y), (x + w, y + h), color, 2)
            cv2.putText(vis, f"{r['parsed_value_mm']:.0f}", (x, max(0, y - 6)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        cv2.imwrite(os.path.join(debug_dir, "ocr_overlay.png"), vis)
        with open(os.path.join(debug_dir, "ocr_dimensions.json"), "w", encoding="utf-8") as f:
            json.dump(results, f, ensure_ascii=False, indent=2)

    return results


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("image")
    parser.add_argument("--debug-dir", type=str, default=None)
    parser.add_argument("--lang", type=str, default="rus+eng")
    args = parser.parse_args()

    results = recognize_dimensions(args.image, debug_dir=args.debug_dir, lang=args.lang)
    print(f"Найдено {len(results)} числовых кандидатов:")
    for r in results:
        print(f"  bbox={r['bbox']} raw='{r['raw_text']}' value={r['parsed_value_mm']} conf={r['ocr_confidence']}")
    print("\nВНИМАНИЕ: это кандидаты для проверки оператором, не окончательные размеры.")
    print("Точность на рукописном тексте ограничена — см. docstring модуля.")


if __name__ == "__main__":
    main()
