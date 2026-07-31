"""
Строит DXF с профессионально нанесёнными размерами по проверенной
спецификации детали (JSON), заданной оператором после подтверждения
реальных размеров (по фото, шаблону или замеру).

Использование:
    python build_dimensioned_dxf.py <part_spec.json> <output.dxf>

Формат part_spec.json:
{
  "width": 1830,
  "height": 381,
  "holes": [
    {"x": 52, "y": 22, "d": 10},
    ...
  ]
}
"""
import sys
import json
import argparse

from geometry import DxfBuilder


def build_dimensioned_dxf(spec_path, dxf_path):
    with open(spec_path, "r", encoding="utf-8") as f:
        spec = json.load(f)

    W = float(spec["width"])
    H = float(spec["height"])
    holes = spec.get("holes", [])

    b = DxfBuilder()

    b.polyline([(0, 0), (W, 0), (W, H), (0, H)], layer="CUT", closed=True)

    for hole in holes:
        x, y, d = float(hole["x"]), float(hole["y"]), float(hole["d"])
        b.circle(x, y, d / 2, layer="HOLES")
        b.centermark(x, y, layer="CENTER")

    b.hdim(0, W, -95, 0, f"{W:.0f}")
    b.vdim(0, H, W + 85, W, f"{H:.0f}")

    xs_sorted = sorted(set(h["x"] for h in holes))
    if xs_sorted:
        chain = [0.0] + xs_sorted + [W]
        chain = sorted(set(chain))
        for a, c in zip(chain[:-1], chain[1:]):
            if c - a > 0.5:
                b.hdim(a, c, -45, 0, f"{c - a:.0f}")

    ys_sorted = sorted(set(h["y"] for h in holes))
    if ys_sorted:
        b.vdim(0, ys_sorted[0], -75, 0, f"{ys_sorted[0]:.0f}")
        b.vdim(ys_sorted[-1], H, -75, 0, f"{H - ys_sorted[-1]:.0f}")
        if len(ys_sorted) > 1:
            b.vdim(ys_sorted[0], ys_sorted[-1], -130, 0, f"{ys_sorted[-1] - ys_sorted[0]:.0f}")

    if holes:
        diam_groups = {}
        for h in holes:
            diam_groups.setdefault(h["d"], []).append(h)
        y_offset = H + 60
        for d, group in diam_groups.items():
            ref = group[0]
            b.leader(
                ref["x"] + 4, ref["y"] + 4,
                ref["x"] + 90, ref["y"] + 70,
                ref["x"] + 220, ref["y"] + 70,
                f"{len(group)} HOLES DIA {d:.0f}",
            )

    b.text(0, H + 115, f"PART: RECTANGLE {W:.0f} x {H:.0f} mm", 20, 0, "TEXT")
    b.text(0, H + 85, "ALL DIMENSIONS IN mm. VERIFY BEFORE CNC CUTTING.", 14, 0, "TEXT")

    b.save(dxf_path)
    return dxf_path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("spec", help="Путь к JSON со спецификацией детали")
    parser.add_argument("output", help="Путь для сохранения dimensioned.dxf")
    args = parser.parse_args()

    path = build_dimensioned_dxf(args.spec, args.output)
    print(f"DXF с размерами сохранён: {path}")


if __name__ == "__main__":
    main()
