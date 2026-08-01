"""Общие утилиты для построения DXF (ASCII R12) с размерными линиями."""
import math

LAYER_COLORS = {
    "CUT": 7,
    "HOLES": 1,
    "DIM": 3,
    "CENTER": 4,
    "TEXT": 2,
    "DIM_AUTO": 5,
    "TEXT_AUTO": 6,
}


class DxfBuilder:
    def __init__(self):
        self.entities = []

    def line(self, x1, y1, x2, y2, layer="CUT"):
        self.entities += [
            "0", "LINE", "8", layer,
            "10", f"{x1:.3f}", "20", f"{y1:.3f}", "30", "0",
            "11", f"{x2:.3f}", "21", f"{y2:.3f}", "31", "0",
        ]

    def circle(self, x, y, r, layer="HOLES"):
        self.entities += [
            "0", "CIRCLE", "8", layer,
            "10", f"{x:.3f}", "20", f"{y:.3f}", "30", "0",
            "40", f"{r:.3f}",
        ]

    def polyline(self, points, layer="CUT", closed=True):
        self.entities += ["0", "LWPOLYLINE", "8", layer, "90", str(len(points)), "70", "1" if closed else "0"]
        for x, y in points:
            self.entities += ["10", f"{x:.3f}", "20", f"{y:.3f}"]

    def text(self, x, y, s, h=14, rot=0, layer="TEXT"):
        self.entities += [
            "0", "TEXT", "8", layer,
            "10", f"{x:.3f}", "20", f"{y:.3f}", "30", "0",
            "40", f"{h:.3f}", "1", s, "50", str(rot),
        ]

    def _arrow(self, x, y, ang, size=8, layer="DIM"):
        a1 = ang + 2.7
        a2 = ang - 2.7
        self.line(x, y, x + size * math.cos(a1), y + size * math.sin(a1), layer)
        self.line(x, y, x + size * math.cos(a2), y + size * math.sin(a2), layer)

    def hdim(self, x1, x2, y, obj_y, label, layer="DIM"):
        self.line(x1, obj_y, x1, y + 8, layer)
        self.line(x2, obj_y, x2, y + 8, layer)
        self.line(x1, y, x2, y, layer)
        self._arrow(x1, y, 0, layer=layer)
        self._arrow(x2, y, math.pi, layer=layer)
        self.text((x1 + x2) / 2 - 3.5 * len(label), y + 8, label, 14, 0, "TEXT")

    def vdim(self, y1, y2, x, obj_x, label, layer="DIM"):
        self.line(obj_x, y1, x + 8, y1, layer)
        self.line(obj_x, y2, x + 8, y2, layer)
        self.line(x, y1, x, y2, layer)
        self._arrow(x, y1, math.pi / 2, layer=layer)
        self._arrow(x, y2, -math.pi / 2, layer=layer)
        self.text(x - 20, (y1 + y2) / 2 - 3.5 * len(label), label, 14, 90, "TEXT")

    def centermark(self, x, y, size=8, layer="CENTER"):
        self.line(x - size, y, x + size, y, layer)
        self.line(x, y - size, x, y + size, layer)

    def leader(self, x0, y0, x1, y1, x2, y2, text_str, layer="DIM"):
        self.line(x0, y0, x1, y1, layer)
        self.line(x1, y1, x2, y2, layer)
        self.text(x2 + 10, y2 + 8, text_str, 14, 0, "TEXT")

    def to_dxf(self):
        header = [
            "0", "SECTION", "2", "HEADER",
            "9", "$ACADVER", "1", "AC1009",
            "9", "$INSUNITS", "70", "4",
            "0", "ENDSEC",
            "0", "SECTION", "2", "TABLES",
            "0", "TABLE", "2", "LAYER", "70", str(len(LAYER_COLORS)),
        ]
        for name, color in LAYER_COLORS.items():
            header += ["0", "LAYER", "2", name, "70", "0", "62", str(color), "6", "CONTINUOUS"]
        header += ["0", "ENDTAB", "0", "ENDSEC", "0", "SECTION", "2", "ENTITIES"]
        footer = ["0", "ENDSEC", "0", "EOF"]
        return "\n".join(header + self.entities + footer)

    def save(self, path):
        with open(path, "w", encoding="ascii") as f:
            f.write(self.to_dxf())
