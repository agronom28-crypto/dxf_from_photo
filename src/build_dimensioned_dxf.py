"""
Строит DXF-файлы по проверенной спецификации детали (JSON), заданной
оператором после подтверждения реальных размеров (по фото, шаблону
или замеру).

Генерирует ДВА файла:
  1. <output>_CNC.dxf         — чистый чертёж для резки: только контур
                                 (слой CUT) и отверстия (слой HOLES),
                                 без текста, размеров и выносок. Готов
                                 к прямой загрузке в ЧПУ/CAM.
  2. <output>_DIMENSIONED.dxf — тот же контур с полным профессиональным
                                 простановкой размеров: габариты, шаг
                                 отверстий по X и Y, диаметры, фаски,
                                 подписи — как делает чертёжник вручную.

Использование:
    python build_dimensioned_dxf.py <part_spec.json> <output_basename>

Формат part_spec.json:
{
  "width": 1830,
  "height": 381,
  "chamfers": {
    "top_left": 2, "top_right": 2, "bottom_left": 0, "bottom_right": 0
  },
  "holes": [
    {"x": 52, "y": 22, "d": 10},
    ...
  ]
}

Поле "chamfers" необязательно (по умолчанию все срезы = 0, обычный
прямоугольник). Величина среза задаётся катетом (мм) при угле 45°.
"""
import sys
import json
import argparse

from geometry import DxfBuilder, rectangle_with_chamfers, stadium_outline


def _load_spec(spec_path):
    with open(spec_path, "r", encoding="utf-8") as f:
        spec = json.load(f)

    W = float(spec["width"])
    H = float(spec["height"])
    holes = spec.get("holes", [])
    shape = spec.get("shape", "rectangle")
    ch = spec.get("chamfers", {}) or {}
    chamfers = {
        "top_left": float(ch.get("top_left", 0.0)),
        "top_right": float(ch.get("top_right", 0.0)),
        "bottom_left": float(ch.get("bottom_left", 0.0)),
        "bottom_right": float(ch.get("bottom_right", 0.0)),
    }
    radius = float(spec.get("radius", 0.0))
    return W, H, holes, chamfers, shape, radius


def _build_outline(W, H, chamfers, shape, radius):
    if shape == "stadium":
        return stadium_outline(W, H, radius)
    return rectangle_with_chamfers(
        W, H,
        top_left_chamfer=chamfers["top_left"],
        top_right_chamfer=chamfers["top_right"],
        bottom_left_chamfer=chamfers["bottom_left"],
        bottom_right_chamfer=chamfers["bottom_right"],
    )


def build_cnc_dxf(spec_path, dxf_path):
    """Чистый файл для ЧПУ: только геометрия реза, без аннотаций."""
    W, H, holes, chamfers, shape, radius = _load_spec(spec_path)

    b = DxfBuilder()
    outline = _build_outline(W, H, chamfers, shape, radius)
    b.polyline(outline, layer="CUT", closed=True)

    for hole in holes:
        x, y, d = float(hole["x"]), float(hole["y"]), float(hole["d"])
        b.circle(x, y, d / 2, layer="HOLES")

    b.save(dxf_path)
    return dxf_path


def build_dimensioned_dxf(spec_path, dxf_path):
    """Полный чертёж с профессионально нанесёнными размерами."""
    W, H, holes, chamfers, shape, radius = _load_spec(spec_path)

    b = DxfBuilder()
    outline = _build_outline(W, H, chamfers, shape, radius)
    b.polyline(outline, layer="CUT", closed=True)

    for hole in holes:
        x, y, d = float(hole["x"]), float(hole["y"]), float(hole["d"])
        b.circle(x, y, d / 2, layer="HOLES")
        b.centermark(x, y, layer="CENTER")

    # габаритные размеры
    b.hdim(0, W, -95, 0, f"{W:.0f}")
    b.vdim(0, H, W + 85, W, f"{H:.0f}")

    # цепочка по X между центрами отверстий
    xs_sorted = sorted(set(h["x"] for h in holes))
    if xs_sorted:
        chain = sorted(set([0.0] + xs_sorted + [W]))
        for a, c in zip(chain[:-1], chain[1:]):
            if c - a > 0.5:
                b.hdim(a, c, -45, 0, f"{c - a:.0f}")

    # размеры по Y (отступы от кромок + межрядный шаг)
    ys_sorted = sorted(set(h["y"] for h in holes))
    if ys_sorted:
        b.vdim(0, ys_sorted[0], -75, 0, f"{ys_sorted[0]:.0f}")
        b.vdim(ys_sorted[-1], H, -75, 0, f"{H - ys_sorted[-1]:.0f}")
        if len(ys_sorted) > 1:
            b.vdim(ys_sorted[0], ys_sorted[-1], -130, 0, f"{ys_sorted[-1] - ys_sorted[0]:.0f}")

    # подписи диаметров отверстий (группировка по диаметру)
    if holes:
        diam_groups = {}
        for h in holes:
            diam_groups.setdefault(h["d"], []).append(h)
        for d, group in diam_groups.items():
            ref = group[0]
            b.leader(
                ref["x"] + 4, ref["y"] + 4,
                ref["x"] + 90, ref["y"] + 70,
                ref["x"] + 220, ref["y"] + 70,
                f"{len(group)} HOLES DIA {d:.0f}",
            )

    if shape == "stadium":
        straight = W - 2 * radius
        cy = H / 2.0
        # длина прямых участков сверху и снизу
        b.hdim(radius, radius + straight, H + 40, H, f"{straight:.0f}")
        b.hdim(radius, radius + straight, -40, 0, f"{straight:.0f}")
        # радиус левого и правого торца (подпись под углом 225 и -45 град.)
        b.rdim(radius, cy, radius, 225, f"R{radius:.0f}")
        b.rdim(W - radius, cy, radius, -45, f"R{radius:.0f}")
    else:
        # подписи фасок (для каждого ненулевого среза)
        chamfer_labels = {
            "top_left": (0.0, H),
            "top_right": (W, H),
            "bottom_left": (0.0, 0.0),
            "bottom_right": (W, 0.0),
        }
        for name, val in chamfers.items():
            if val > 0:
                cx, cy = chamfer_labels[name]
                offx = 60 if "left" in name else -60
                offy = -60 if "bottom" in name else 60
                b.leader(cx, cy, cx + offx, cy + offy, cx + offx * 1.8, cy + offy,
                          f"CHAMFER {val:.0f}x45")

    b.text(0, H + 115, f"PART: RECTANGLE {W:.0f} x {H:.0f} mm", 20, 0, "TEXT")
    b.text(0, H + 85, "ALL DIMENSIONS IN mm. VERIFY BEFORE CNC CUTTING.", 14, 0, "TEXT")

    b.save(dxf_path)
    return dxf_path


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("spec", help="Путь к JSON со спецификацией детали")
    parser.add_argument("output_basename", help="Базовое имя выходных файлов (без расширения)")
    args = parser.parse_args()

    cnc_path = f"{args.output_basename}_CNC.dxf"
    dim_path = f"{args.output_basename}_DIMENSIONED.dxf"

    build_cnc_dxf(args.spec, cnc_path)
    build_dimensioned_dxf(args.spec, dim_path)

    print(f"Чистый DXF для ЧПУ сохранён: {cnc_path}")
    print(f"DXF с размерами сохранён: {dim_path}")


if __name__ == "__main__":
    main()
