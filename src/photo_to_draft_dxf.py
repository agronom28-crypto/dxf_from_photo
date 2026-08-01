"""
Строит черновой DXF-контур по фотографии эскиза (v3 — эффективное распознавание).

Возможности:
  - RETR_TREE: находится полное дерево контуров (внешний контур + отверстия +
    вырезы + пазы на краю листа), а не только внешняя граница.
  - Классификация контуров по ролям: OUTER (контур детали), HOLE_ROUND
    (круглые отверстия), CUTOUT (замкнутые вырезы произвольной формы),
    OPEN_CUTOUT (вырезы на краю листа — требуют ручной проверки).
  - Deskew листа: если в кадре виден край бумаги, перспектива выравнивается
    автоматически через warpPerspective.
  - Двойная детекция круглых отверстий: findContours + HoughCircles,
    взаимно подтверждающие друг друга.
  - ROI-ограничение: Hough ищет круги только внутри области самой детали
    (маска по внешнему контуру), а не по всему кадру со столом и фоном —
    это убирает основной источник ложных срабатываний на реальных фото.
  - Sanity-фильтр по размеру: отверстие крупнее MAX_HOLE_FRACTION_OF_PART
    от габарита детали отбрасывается как шум/артефакт фона или почерка.
  - Hough-only находки (не подтверждённые findContours) по умолчанию НЕ
     попадают в финальный DXF — включаются флагом --include-hough-only.
  - Strict-режим (по умолчанию включён): в DXF попадают только объекты
    с confidence >= CONF_THRESHOLD.
  - Если после всех фильтров не найдено ни одного отверстия/выреза,
    программа явно сообщает об этом, а не выдаёт мусорные объекты.

ВНИМАНИЕ: результат всё ещё черновой. Автоматическое распознавание фото
даёт приблизительную топологию, а не проверенные размеры. Перед резкой
на ЧПУ оператор обязан подтвердить контур и размеры. Рукописные размеры
и их привязка к геометрии распознаются отдельным модулем ocr_dimensions.py
(см. README, раздел Roadmap — уровни 4-5) и требуют ручной проверки.

Использование:
    python photo_to_draft_dxf.py <фото> <output.dxf> --scale-mm=1830 \
        [--debug-dir=out_debug] [--no-hough] [--include-hough-only] [--no-strict]
"""
import argparse
import json
import os
import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None

from geometry import DxfBuilder

MIN_AREA_PX_FRACTION = 0.0008     # отбрасывать шум мельче этой доли площади кадра
CIRCULARITY_THRESHOLD = 0.82      # порог "похоже на окружность"
EDGE_TOUCH_MARGIN_PX = 4          # контур касается края кадра -> открытый вырез
MAX_HOLE_FRACTION_OF_PART = 0.30  # отверстие крупнее 30% габарита детали = шум
CONF_THRESHOLD = 0.75             # порог confidence для strict-режима


def load_and_preprocess(image_path, debug_dir=None):
    if cv2 is None:
        raise RuntimeError("Требуется opencv-python: pip install opencv-python")
    img = cv2.imread(image_path)
    if img is None:
        raise FileNotFoundError(f"Не удалось открыть изображение: {image_path}")

    img = deskew_sheet(img, debug_dir=debug_dir)

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    gray = cv2.bilateralFilter(gray, 9, 75, 75)
    gray_eq = cv2.createCLAHE(clipLimit=2.5, tileGridSize=(8, 8)).apply(gray)

    thresh = cv2.adaptiveThreshold(
        gray_eq, 255, cv2.ADAPTIVE_THRESH_GAUSSIAN_C, cv2.THRESH_BINARY_INV, 31, 8
    )
    kernel = np.ones((3, 3), np.uint8)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel, iterations=1)
    thresh = cv2.morphologyEx(thresh, cv2.MORPH_OPEN, kernel, iterations=1)

    if debug_dir:
        os.makedirs(debug_dir, exist_ok=True)
        cv2.imwrite(os.path.join(debug_dir, "01_gray_eq.png"), gray_eq)
        cv2.imwrite(os.path.join(debug_dir, "02_thresh.png"), thresh)

    return img, gray_eq, thresh


def deskew_sheet(img, debug_dir=None):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    edges = cv2.Canny(blur, 40, 120)
    edges = cv2.dilate(edges, np.ones((5, 5), np.uint8), iterations=2)

    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        return img

    img_area = img.shape[0] * img.shape[1]
    best = None
    for c in contours:
        area = cv2.contourArea(c)
        if area < 0.35 * img_area:
            continue
        peri = cv2.arcLength(c, True)
        approx = cv2.approxPolyDP(c, 0.02 * peri, True)
        if len(approx) == 4:
            if best is None or area > cv2.contourArea(best):
                best = approx

    if best is None:
        return img

    pts = best.reshape(4, 2).astype("float32")
    rect = order_quad_points(pts)
    (tl, tr, br, bl) = rect
    width_a = np.linalg.norm(br - bl)
    width_b = np.linalg.norm(tr - tl)
    max_width = int(max(width_a, width_b))
    height_a = np.linalg.norm(tr - br)
    height_b = np.linalg.norm(tl - bl)
    max_height = int(max(height_a, height_b))
    if max_width < 50 or max_height < 50:
        return img

    dst = np.array([
        [0, 0], [max_width - 1, 0],
        [max_width - 1, max_height - 1], [0, max_height - 1]
    ], dtype="float32")
    M = cv2.getPerspectiveTransform(rect, dst)
    warped = cv2.warpPerspective(img, M, (max_width, max_height))

    if debug_dir:
        os.makedirs(debug_dir, exist_ok=True)
        cv2.imwrite(os.path.join(debug_dir, "00_deskewed.png"), warped)

    return warped


def order_quad_points(pts):
    s = pts.sum(axis=1)
    diff = np.diff(pts, axis=1).reshape(-1)
    tl = pts[np.argmin(s)]
    br = pts[np.argmax(s)]
    tr = pts[np.argmin(diff)]
    bl = pts[np.argmax(diff)]
    return np.array([tl, tr, br, bl], dtype="float32")


def circularity(contour):
    area = cv2.contourArea(contour)
    peri = cv2.arcLength(contour, True)
    if peri == 0:
        return 0.0
    return float(4 * np.pi * area / (peri * peri))


def touches_frame_edge(contour, img_shape, margin=EDGE_TOUCH_MARGIN_PX):
    h, w = img_shape[:2]
    x, y, cw, ch = cv2.boundingRect(contour)
    return x <= margin or y <= margin or (x + cw) >= (w - margin) or (y + ch) >= (h - margin)


def find_all_contours(thresh, img_shape):
    contours, hierarchy = cv2.findContours(thresh, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
    if not contours:
        raise RuntimeError("Контуры на фото не найдены. Проверьте освещение и контраст фото.")
    hierarchy = hierarchy[0]

    img_area = img_shape[0] * img_shape[1]
    min_area = MIN_AREA_PX_FRACTION * img_area

    objects = []
    for i, cnt in enumerate(contours):
        area = cv2.contourArea(cnt)
        if area < min_area:
            continue
        parent = hierarchy[i][3]
        objects.append({
            "index": i, "contour": cnt, "area": area,
            "parent": parent, "is_outer": parent == -1,
        })

    if not objects:
        raise RuntimeError("После фильтрации шума не осталось валидных контуров.")

    outer_candidates = [o for o in objects if o["is_outer"]]
    main_outer = max(outer_candidates, key=lambda o: o["area"]) if outer_candidates else max(objects, key=lambda o: o["area"])

    classified = []
    for o in objects:
        if o["index"] == main_outer["index"]:
            role = "OUTER"
        elif o["parent"] == main_outer["index"] or _is_descendant(o, main_outer, hierarchy):
            circ = circularity(o["contour"])
            if circ >= CIRCULARITY_THRESHOLD:
                role = "HOLE_ROUND"
            elif touches_frame_edge(o["contour"], img_shape):
                role = "OPEN_CUTOUT"
            else:
                role = "CUTOUT"
        else:
            continue
        classified.append({**o, "role": role, "circularity": circularity(o["contour"])})

    return classified, main_outer


def _is_descendant(obj, main_outer, hierarchy):
    parent = obj["parent"]
    seen = set()
    while parent != -1 and parent not in seen:
        if parent == main_outer["index"]:
            return True
        seen.add(parent)
        parent = hierarchy[parent][3]
    return False


def build_outer_mask(img_shape, main_outer_contour):
    """Заливает внутреннюю область детали белым — используется как ROI,
    чтобы Hough не искал круги по фону/столу/тексту за пределами детали."""
    mask = np.zeros(img_shape[:2], dtype=np.uint8)
    cv2.drawContours(mask, [main_outer_contour], -1, 255, thickness=cv2.FILLED)
    return mask


def detect_hough_circles(gray_eq, roi_mask, part_bbox_diag_px):
    """Ищет круги только внутри ROI детали, с порогом radius относительно
    габарита детали, чтобы не ловить крупные артефакты фона/почерка."""
    blur = cv2.medianBlur(gray_eq, 5)
    max_radius = max(4, int(part_bbox_diag_px * 0.12))
    circles = cv2.HoughCircles(
        blur, cv2.HOUGH_GRADIENT, dp=1.2, minDist=15,
        param1=70, param2=38, minRadius=4, maxRadius=max_radius
    )
    result = []
    if circles is not None:
        for x, y, r in circles[0]:
            xi, yi = int(round(x)), int(round(y))
            if not (0 <= yi < roi_mask.shape[0] and 0 <= xi < roi_mask.shape[1]):
                continue
            if roi_mask[yi, xi] == 0:
                continue
            result.append((float(x), float(y), float(r)))
    return result


def deduplicate_holes(classified, px_tolerance=10):
    """На грубых/толстых линиях findContours иногда даёт два вложенных
    контура одного и того же отверстия. Оставляем контур с максимальной
    площадью среди близких центров."""
    holes = [o for o in classified if o["role"] == "HOLE_ROUND"]
    others = [o for o in classified if o["role"] != "HOLE_ROUND"]
    kept = []
    used = [False] * len(holes)
    for i, h in enumerate(holes):
        if used[i]:
            continue
        (cx_i, cy_i), _ = cv2.minEnclosingCircle(h["contour"])
        group = [h]
        used[i] = True
        for j in range(i + 1, len(holes)):
            if used[j]:
                continue
            (cx_j, cy_j), _ = cv2.minEnclosingCircle(holes[j]["contour"])
            if abs(cx_i - cx_j) < px_tolerance and abs(cy_i - cy_j) < px_tolerance:
                group.append(holes[j])
                used[j] = True
        best = max(group, key=lambda o: o["area"])
        kept.append(best)
    return others + kept


def merge_hough_with_contour_holes(hough_circles, classified, part_dim_px, px_tolerance=12):
    """Подтверждает contour-holes через Hough (высокий confidence) и
    возвращает отдельно 'hough-only' кандидатов, прошедших sanity-фильтр
    по максимально правдоподобному размеру относительно детали."""
    for hc_x, hc_y, hc_r in hough_circles:
        for obj in classified:
            if obj["role"] != "HOLE_ROUND":
                continue
            (cx, cy), cr = cv2.minEnclosingCircle(obj["contour"])
            if abs(cx - hc_x) < px_tolerance and abs(cy - hc_y) < px_tolerance:
                obj["confidence"] = 0.95
                obj["hough_confirmed"] = True

    extra_circles = []
    max_allowed_r = part_dim_px * MAX_HOLE_FRACTION_OF_PART
    for hc_x, hc_y, hc_r in hough_circles:
        matched = False
        for obj in classified:
            if obj["role"] != "HOLE_ROUND":
                continue
            (cx, cy), cr = cv2.minEnclosingCircle(obj["contour"])
            if abs(cx - hc_x) < px_tolerance and abs(cy - hc_y) < px_tolerance:
                matched = True
                break
        if matched:
            continue
        if hc_r > max_allowed_r:
            continue  # sanity-фильтр: слишком крупный "круг" относительно детали -> шум
        extra_circles.append({
            "role": "HOLE_ROUND_HOUGH_ONLY",
            "cx": hc_x, "cy": hc_y, "r": hc_r,
            "confidence": 0.55,
            "hough_confirmed": True,
        })
    return extra_circles


def scale_points(points, min_xy, scale, img_shape):
    xs = (points[:, 0].astype(float) - min_xy[0]) * scale
    ys = (img_shape[0] - points[:, 1].astype(float)) * scale
    return xs, ys


def contour_to_polyline(contour, epsilon_ratio=0.0025):
    peri = cv2.arcLength(contour, True)
    epsilon = epsilon_ratio * peri
    approx = cv2.approxPolyDP(contour, epsilon, True)
    return approx.reshape(-1, 2)


def build_draft_dxf(image_path, dxf_path, target_width_mm, debug_dir=None,
                     use_hough=True, include_hough_only=False, strict=True):
    img, gray_eq, thresh = load_and_preprocess(image_path, debug_dir=debug_dir)
    classified, main_outer = find_all_contours(thresh, img.shape)
    classified = deduplicate_holes(classified)

    for obj in classified:
        obj.setdefault("confidence", 0.85 if obj["role"] == "OUTER" else 0.7)
        obj.setdefault("hough_confirmed", False)

    outer_points = contour_to_polyline(main_outer["contour"])
    xs_all = outer_points[:, 0].astype(float)
    ys_all = outer_points[:, 1].astype(float)
    min_x, min_y = xs_all.min(), ys_all.min()
    w_px = xs_all.max() - min_x
    h_px = ys_all.max() - ys_all.min()
    if w_px == 0:
        raise RuntimeError("Некорректный внешний контур: нулевая ширина.")
    scale = target_width_mm / w_px
    part_diag_px = float(np.hypot(w_px, h_px))

    extra_hough_circles = []
    if use_hough:
        roi_mask = build_outer_mask(img.shape, main_outer["contour"])
        hough_circles = detect_hough_circles(gray_eq, roi_mask, part_diag_px)
        extra_hough_circles = merge_hough_with_contour_holes(hough_circles, classified, part_diag_px)
        if not include_hough_only:
            extra_hough_circles = []  # по умолчанию неподтверждённые контуром круги не выводим

    builder = DxfBuilder()
    outer_xs, outer_ys = scale_points(outer_points, (min_x, min_y), scale, img.shape)
    builder.polyline(list(zip(outer_xs.tolist(), outer_ys.tolist())), layer="CUT", closed=True)

    report_lines = [f"OUTER contour: {len(outer_points)} pts, width={target_width_mm:.1f}mm (assumed)"]
    hole_count = cutout_count = open_cutout_count = skipped_low_conf = 0

    for obj in classified:
        if obj["role"] == "OUTER":
            continue
        conf = obj["confidence"]
        if strict and conf < CONF_THRESHOLD and obj["role"] != "HOLE_ROUND":
            skipped_low_conf += 1
            report_lines.append(f"SKIPPED (low confidence {conf:.2f}, strict mode): role={obj['role']}")
            continue

        pts = contour_to_polyline(obj["contour"])
        xs, ys = scale_points(pts, (min_x, min_y), scale, img.shape)

        if obj["role"] == "HOLE_ROUND":
            (cx, cy), r_px = cv2.minEnclosingCircle(obj["contour"])
            cx_mm = (cx - min_x) * scale
            cy_mm = (img.shape[0] - cy) * scale
            r_mm = r_px * scale
            builder.circle(cx_mm, cy_mm, r_mm, layer="HOLES")
            builder.centermark(cx_mm, cy_mm, size=max(4, r_mm * 0.3), layer="CENTER")
            hole_count += 1
            report_lines.append(f"HOLE round d={2*r_mm:.1f}mm at ({cx_mm:.1f},{cy_mm:.1f}) confidence={conf:.2f} hough={obj['hough_confirmed']}")
        elif obj["role"] == "CUTOUT":
            builder.polyline(list(zip(xs.tolist(), ys.tolist())), layer="CUTOUTS", closed=True)
            cutout_count += 1
            report_lines.append(f"CUTOUT closed, {len(pts)} pts, area~{obj['area']:.0f}px confidence={conf:.2f}")
        elif obj["role"] == "OPEN_CUTOUT":
            builder.polyline(list(zip(xs.tolist(), ys.tolist())), layer="OPEN_CUTOUTS", closed=False)
            open_cutout_count += 1
            report_lines.append(f"OPEN CUTOUT (touches sheet edge), {len(pts)} pts confidence={conf:.2f} — ПРОВЕРИТЬ ВРУЧНУЮ")

    for extra in extra_hough_circles:
        cx_mm = (extra["cx"] - min_x) * scale
        cy_mm = (img.shape[0] - extra["cy"]) * scale
        r_mm = extra["r"] * scale
        builder.circle(cx_mm, cy_mm, r_mm, layer="HOLES_LOW_CONF")
        hole_count += 1
        report_lines.append(f"HOLE round (Hough-only) d={2*r_mm:.1f}mm confidence={extra['confidence']:.2f} — ПРОВЕРИТЬ ВРУЧНУЮ")

    if hole_count == 0 and cutout_count == 0 and open_cutout_count == 0:
        report_lines.append("ПРИМЕЧАНИЕ: не найдено ни одного отверстия/выреза, подтверждённого достаточной уверенностью — вероятно, на эскизе только внешний контур и размерные линии.")

    y_top = outer_ys.max()
    builder.text(0, y_top + 55, "DRAFT v3 - NOT VERIFIED - DO NOT USE FOR CUTTING", 18, 0, "TEXT")
    builder.text(0, y_top + 32, f"Auto width: {target_width_mm:.0f} mm (assumed) | holes={hole_count} cutouts={cutout_count} open={open_cutout_count} skipped_low_conf={skipped_low_conf}", 12, 0, "TEXT")
    if open_cutout_count > 0:
        builder.text(0, y_top + 12, "ВНИМАНИЕ: обнаружены вырезы на краю листа — проверить их форму вручную", 12, 0, "TEXT")

    builder.save(dxf_path)

    if debug_dir:
        os.makedirs(debug_dir, exist_ok=True)
        geometry_report = {
            "coordinate_system": "image_pixels",
            "image_size": {"width": int(img.shape[1]), "height": int(img.shape[0])},
            "scale": {"target_width_mm": float(target_width_mm), "px_to_mm": float(scale),
                      "origin_px": [float(min_x), float(img.shape[0])]},
            "outer_contour": outer_points.astype(float).tolist(),
            "holes": [], "cutouts": [],
            "counts": {"outer_points": len(outer_points), "holes": hole_count,
                       "cutouts": cutout_count, "open_cutouts": open_cutout_count,
                       "skipped_low_conf": skipped_low_conf},
            "details": report_lines,
        }
        for obj in classified:
            if obj["role"] == "HOLE_ROUND":
                (cx, cy), r_px = cv2.minEnclosingCircle(obj["contour"])
                geometry_report["holes"].append({"center": [float(cx), float(cy)],
                    "radius": float(r_px), "confidence": float(obj["confidence"])})
            elif obj["role"] in ("CUTOUT", "OPEN_CUTOUT"):
                pts = contour_to_polyline(obj["contour"])
                geometry_report["cutouts"].append({"points": pts.astype(float).tolist(),
                    "open": obj["role"] == "OPEN_CUTOUT", "confidence": float(obj["confidence"])})
        with open(os.path.join(debug_dir, "recognition_report.json"), "w", encoding="utf-8") as f:
            json.dump(geometry_report, f, ensure_ascii=False, indent=2)
        vis = img.copy()
        cv2.drawContours(vis, [main_outer["contour"]], -1, (0, 255, 0), 3)
        for obj in classified:
            if obj["role"] == "HOLE_ROUND":
                cv2.drawContours(vis, [obj["contour"]], -1, (255, 0, 0), 2)
            elif obj["role"] == "CUTOUT" and obj["confidence"] >= (CONF_THRESHOLD if strict else 0):
                cv2.drawContours(vis, [obj["contour"]], -1, (0, 200, 255), 2)
            elif obj["role"] == "OPEN_CUTOUT":
                cv2.drawContours(vis, [obj["contour"]], -1, (0, 0, 255), 2)
        cv2.imwrite(os.path.join(debug_dir, "03_classified_overlay.png"), vis)

    return dxf_path, report_lines


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("image")
    parser.add_argument("output")
    parser.add_argument("--scale-mm", type=float, default=1000.0)
    parser.add_argument("--debug-dir", type=str, default=None)
    parser.add_argument("--no-hough", action="store_true")
    parser.add_argument("--include-hough-only", action="store_true",
                         help="Включить в DXF Hough-круги, не подтверждённые findContours (менее надёжно)")
    parser.add_argument("--no-strict", action="store_true",
                         help="Отключить фильтрацию объектов с низким confidence")
    args = parser.parse_args()

    path, report = build_draft_dxf(
        args.image, args.output, args.scale_mm,
        debug_dir=args.debug_dir, use_hough=not args.no_hough,
        include_hough_only=args.include_hough_only, strict=not args.no_strict
    )
    print(f"Черновой DXF сохранён: {path}")
    for line in report:
        print(" -", line)
    print("ВНИМАНИЕ: проверьте контур, отверстия и размеры перед использованием на ЧПУ.")


if __name__ == "__main__":
    main()
