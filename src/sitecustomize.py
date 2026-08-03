"""DXF text compatibility for ezdxf R12 through R2018."""
from __future__ import annotations

import os
import re

_MTEXT_CODES = re.compile(r"\\[A-Za-z](?:[^;]*;)?|[{}]")
_CHAR_TRANSLATION = str.maketrans({
    "⌀": "DIA ", "Ø": "DIA ", "ø": "DIA ",
})
_WORD_REPLACEMENTS = (
    ("ОТВ.", "HOLE"),
    ("отв.", "HOLE"),
    ("мм", "mm"),
)


def _plain_text(value: object) -> str:
    text = str(value).replace("\\P", " ").replace("\n", " ")
    text = _MTEXT_CODES.sub("", text)
    for source, target in _WORD_REPLACEMENTS:
        text = text.replace(source, target)
    text = text.translate(_CHAR_TRANSLATION)
    return " ".join(text.split()).encode("ascii", "replace").decode("ascii")


class _TextAdapter:
    def __init__(self, entity):
        self.entity = entity

    def set_location(self, insert, rotation=None, attachment_point=None):
        self.entity.dxf.insert = insert
        if rotation is not None:
            self.entity.dxf.rotation = rotation
        return self

    def __getattr__(self, name):
        return getattr(self.entity, name)


def _install() -> None:
    try:
        from ezdxf.graphicsfactory import CreatorInterface
    except ImportError:
        return

    if getattr(CreatorInterface, "_dxf_photo_compatibility", False):
        return

    original = CreatorInterface.add_mtext

    def compatible_add_mtext(self, text, dxfattribs=None):
        document = getattr(self, "doc", None)
        version = getattr(document, "dxfversion", "AC1015")
        if version != "AC1009":
            return original(self, text, dxfattribs=dxfattribs)

        attributes = dict(dxfattribs or {})
        attributes["height"] = attributes.pop(
            "char_height", attributes.pop("height", 2.5)
        )
        for unsupported in ("attachment_point", "width", "insert"):
            attributes.pop(unsupported, None)
        return _TextAdapter(self.add_text(_plain_text(text), dxfattribs=attributes))

    CreatorInterface.add_mtext = compatible_add_mtext
    CreatorInterface._dxf_photo_compatibility = True
    os.environ["DXF_PHOTO_COMPAT_ACTIVE"] = "1"


_install()
