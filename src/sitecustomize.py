"""Runtime DXF compatibility for ezdxf R12 through R2018.

Python imports this module automatically when the repository is started with
``PYTHONPATH=src``.  Old DXF drawings cannot contain MTEXT, therefore MTEXT
creation is transparently represented by a plain TEXT entity for DXF R12.
"""
from __future__ import annotations

import re

_MTEXT_CODES = re.compile(r"\\[A-Za-z](?:[^;]*;)?|[{}]")
_R12_TRANSLATION = str.maketrans({
    "⌀": "DIA ",
    "Ø": "DIA ",
    "ø": "DIA ",
    "ОТВ.": "HOLE",
    "отв.": "HOLE",
    "мм": "mm",
})


def _plain_r12_text(value: object) -> str:
    """Return conservative single-line text readable by legacy CAD systems."""
    text = str(value).replace("\\P", " ").replace("\n", " ")
    text = _MTEXT_CODES.sub("", text).translate(_R12_TRANSLATION)
    text = " ".join(text.split())
    return text.encode("ascii", "replace").decode("ascii")


class _R12TextAdapter:
    """Expose the small MTEXT placement API used by the application."""

    def __init__(self, entity):
        self.entity = entity

    def set_location(self, insert, rotation=None, attachment_point=None):
        self.entity.dxf.insert = insert
        if rotation is not None:
            self.entity.dxf.rotation = rotation
        return self

    def __getattr__(self, name):
        return getattr(self.entity, name)


def _install_ezdxf_compatibility() -> None:
    try:
        from ezdxf.layouts import BaseLayout
    except ImportError:
        return

    if getattr(BaseLayout, "_dxf_photo_compatibility", False):
        return

    original_add_mtext = BaseLayout.add_mtext

    def compatible_add_mtext(self, text, dxfattribs=None):
        document = getattr(self, "doc", None)
        version = getattr(document, "dxfversion", "AC1015")
        if version != "AC1009":
            return original_add_mtext(self, text, dxfattribs=dxfattribs)

        attributes = dict(dxfattribs or {})
        height = attributes.pop("char_height", attributes.pop("height", 2.5))
        attributes.pop("attachment_point", None)
        attributes.pop("width", None)
        attributes["height"] = height
        entity = self.add_text(_plain_r12_text(text), dxfattribs=attributes)
        return _R12TextAdapter(entity)

    BaseLayout.add_mtext = compatible_add_mtext
    BaseLayout._dxf_photo_compatibility = True


_install_ezdxf_compatibility()
