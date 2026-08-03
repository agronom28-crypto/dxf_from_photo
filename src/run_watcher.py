"""Fail-safe launcher that enforces DXF compatibility before the watcher starts."""
from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path

SRC = Path(__file__).resolve().parent
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

import sitecustomize  # noqa: F401,E402
import hole_diameter_clarification as hole_info  # noqa: E402


def _write_universal_hole_info(path, spec) -> None:
    """Use the TEXT entity supported by every writable DXF version."""
    try:
        import ezdxf
    except ImportError as error:
        raise RuntimeError("Для записи диаметра требуется ezdxf") from error

    document = ezdxf.readfile(path)
    model = document.modelspace()
    if "HOLE_INFO" not in document.layers:
        document.layers.add("HOLE_INFO", color=3)
    label = f"{spec.count} HOLE DIA {spec.diameter:g} mm"
    model.add_text(
        label,
        dxfattribs={
            "layer": "HOLE_INFO",
            "height": 5,
            "insert": (0, 10),
        },
    )
    document.saveas(path)


hole_info.add_to_info_dxf = _write_universal_hole_info

if os.environ.get("DXF_PHOTO_COMPAT_ACTIVE") != "1":
    raise RuntimeError(
        "Слой совместимости DXF не загрузился; обработка остановлена до создания файла"
    )

runpy.run_path(str(SRC / "inbox_watcher.py"), run_name="__main__")
