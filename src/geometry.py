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

    def arc(self, x, y, r, start_angle, end_angle, layer="CUT"):
        """Дуга окружности. Углы в градусах, против часовой стрелки, как в DXF."""
        self.entities += [
            "0", "ARC", "8", layer,
            "10", f"{x:.3f}", "20", f"{y:.3f}", "30", "0",
            "40", f"{r:.3f}",
            "50", f"{start_angle:.3f}", "51", f"{end_angle:.3f}",
        ]

    def polyline(self, points, layer="CUT", closed=True):
        # DXF R12 (AC1009) не поддерживает LWPOLYLINE (появился в R13+),
        # поэтому используем классическую связку POLYLINE/VERTEX/SEQEND,
        # которую гарантированно понимают ЧПУ/CAM программы.
        # Каждая точка может быть (x, y) для прямого сегмента или
        # (x, y, bulge) для дугового сегмента, идущего от этой вершины
        # к следующей (bulge = tan(угол_дуги / 4), см. DXF spec, код 42).
        self.entities += ["0", "POLYLINE", "8", layer, "66", "1", "70", "1" if closed else "0"]
        for pt in points:
            if len(pt) == 3:
                x, y, bulge = pt
                self.entities += ["0", "VERTEX", "8", layer, "10", f"{x:.3f}", "20", f"{y:.3f}", "30", "0", "42", f"{bulge:.6f}"]
            else:
                x, y = pt
                self.entities += ["0", "VERTEX", "8", layer, "10", f"{x:.3f}", "20", f"{y:.3f}", "30", "0"]
        self.entities += ["0", "SEQEND", "8", layer]

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

    def rdim(self, cx, cy, r, angle_deg, label, layer="DIM"):
        """Радиальный размер: линия от центра дуги наружу под заданным углом
        (градусы) с меткой (обычно 'R<значение>')."""
        rad = math.radians(angle_deg)
        x1, y1 = cx, cy
        x2 = cx + r * math.cos(rad)
        y2 = cy + r * math.sin(rad)
        x3 = x2 + 25 * math.cos(rad)
        y3 = y2 + 25 * math.sin(rad)
        self.line(x1, y1, x2, y2, layer)
        self._arrow(x2, y2, rad + math.pi, layer=layer)
        self.line(x2, y2, x3, y3, layer)
        self.text(x3 + 5, y3, label, 14, 0, "TEXT")

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


def rectangle_with_chamfers(width, height, top_left_chamfer=0.0, top_right_chamfer=0.0,
                             bottom_left_chamfer=0.0, bottom_right_chamfer=0.0):
    """
    Строит список точек контура прямоугольника width x height с опциональными
    срезами (фасками) 45 градусов в любом из четырёх углов.

    Углы отсчитываются в системе координат детали: (0,0) - нижний левый угол,
    (width, height) - верхний правый. Значение chamfer - величина катета среза
    (мм) вдоль каждой из двух сторон, сходящихся в угле (симметричный срез 45°).

    Возвращает список (x, y) точек в порядке обхода против часовой стрелки,
    начиная от нижней стороны, готовый для передачи в DxfBuilder.polyline().
    """
    pts = []

    # bottom-left corner
    if bottom_left_chamfer > 0:
        pts.append((0.0, bottom_left_chamfer))
        pts.append((bottom_left_chamfer, 0.0))
    else:
        pts.append((0.0, 0.0))

    # bottom-right corner
    if bottom_right_chamfer > 0:
        pts.append((width - bottom_right_chamfer, 0.0))
        pts.append((width, bottom_right_chamfer))
    else:
        pts.append((width, 0.0))

    # top-right corner
    if top_right_chamfer > 0:
        pts.append((width, height - top_right_chamfer))
        pts.append((width - top_right_chamfer, height))
    else:
        pts.append((width, height))

    # top-left corner
    if top_left_chamfer > 0:
        pts.append((top_left_chamfer, height))
        pts.append((0.0, height - top_left_chamfer))
    else:
        pts.append((0.0, height))

    return pts


def stadium_outline(length, width, radius):
    """
    Строит контур "стадион" (скруглённый прямоугольник с двумя
    полукруглыми торцами) как список вершин с bulge для polyline().

    length - общая длина детали по оси X (включая оба полукруга).
    width  - общая высота детали по оси Y (= 2 * radius, диаметр торцов).
    radius - радиус скругления торцов (полукруг).

    Прямые верхняя и нижняя стороны имеют длину (length - 2*radius).
    Система координат: (0, 0) - нижняя левая точка начала прямого
    участка нижней стороны, центр детали по Y на высоте width/2.

    Возвращает список (x, y, bulge) в порядке обхода против часовой
    стрелки, готовый для DxfBuilder.polyline(..., closed=True).
    """
    straight = length - 2 * radius
    if straight < 0:
        raise ValueError("length must be >= 2 * radius for a stadium shape")

    cy = width / 2.0
    # bulge для полукруга (дуга 180 градусов) = tan(180/4) = tan(45) = 1.0
    semicircle_bulge = 1.0

    pts = [
        (radius, 0.0, 0.0),                         # начало нижней прямой
        (radius + straight, 0.0, semicircle_bulge),  # конец нижней прямой -> дуга правого торца
        (radius + straight, width, 0.0),             # верх правого торца -> начало верхней прямой
        (radius, width, semicircle_bulge),           # конец верхней прямой -> дуга левого торца
    ]
    return pts
