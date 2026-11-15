"""Tiptap declarations loaded from the shared preset data."""

from dataclasses import replace
from importlib.resources import files
import json

from .schema import _attrs_from_dict, _mark_from_dict, _node_from_dict


_DATA = json.loads(files(__package__).joinpath("presets.json").read_text(encoding="utf-8"))


def _mark(name):
    return _mark_from_dict(_DATA[name]["marks"][0])


def _nodes(name):
    return tuple(_node_from_dict(declaration) for declaration in _DATA[name]["nodes"])


def _core_attrs(name):
    return {type_: _attrs_from_dict(attrs) for type_, attrs in _DATA[name]["core_attrs"].items()}


def text_style(*, background_color=True, color=True, font_family=True, font_size=True, line_height=True):
    """Select the attrs enabled by TextStyleKit."""
    mark = _mark("TEXT_STYLE")
    enabled = (background_color, color, font_family, font_size, line_height)
    return replace(mark, attrs={name: attr for (name, attr), active in zip(mark.attrs.items(), enabled) if active})


_ALIGN_TYPES = _core_attrs("TEXT_ALIGN")
_ALIGN_ATTRS = next(iter(_ALIGN_TYPES.values()))
_ALIGN = next(iter(_ALIGN_ATTRS.values()))


def text_align(*, types=tuple(_ALIGN_TYPES), alignments=_ALIGN.choices, default_alignment=_ALIGN.default):
    """Match TextAlign's target types, alignments and defaultAlignment."""
    return {
        type_: {name: replace(attr, choices=tuple(alignments), default=default_alignment)
                for name, attr in _ALIGN_ATTRS.items()}
        for type_ in types
    }


_LINK_ATTRS = _core_attrs("LINK_ATTRS")
_LINK = _LINK_ATTRS["link"]


def link_attrs(*, target=_LINK["target"].default, rel=_LINK["rel"].default, class_=_LINK["class"].default):
    """Match Link's HTMLAttributes defaults."""
    return {"link": {name: replace(attr, default=value)
                     for (name, attr), value in zip(_LINK.items(), (target, rel, class_))}}


UNDERLINE = _mark("UNDERLINE")
HIGHLIGHT = _mark("HIGHLIGHT")
SUBSCRIPT = _mark("SUBSCRIPT")
SUPERSCRIPT = _mark("SUPERSCRIPT")
TEXT_STYLE = text_style()
MENTION, = _nodes("MENTION")
DETAILS = _nodes("DETAILS")
INLINE_MATH, = _nodes("INLINE_MATH")
BLOCK_MATH, = _nodes("BLOCK_MATH")
TEXT_ALIGN = text_align()
LINK_ATTRS = link_attrs()
IMAGE_SIZE = _core_attrs("IMAGE_SIZE")
TABLE_SPANS = _core_attrs("TABLE_SPANS")
