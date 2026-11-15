"""Fast Markdown conversion for Tiptap-style JSON."""

try:
    from ._core import (
        Document,
        InvalidNodeError,
        MarktipError,
        ParseError,
        UnknownTypeError,
        __version__,
        from_dict,
        from_markdown,
    )
except ImportError:  # pragma: no cover - development-only CMake build fallback
    import importlib.util
    import pathlib
    import sys

    _root = pathlib.Path(__file__).resolve().parents[2]
    _candidates = sorted(_root.glob("build/**/_core*.so")) + sorted(_root.glob("build/**/_core*.pyd"))
    if not _candidates:
        raise

    _spec = importlib.util.spec_from_file_location("marktip._core", _candidates[0])
    if _spec is None or _spec.loader is None:
        raise
    _module = importlib.util.module_from_spec(_spec)
    sys.modules[_spec.name] = _module
    _spec.loader.exec_module(_module)

    __version__ = _module.__version__
    Document = _module.Document
    MarktipError = _module.MarktipError
    UnknownTypeError = _module.UnknownTypeError
    InvalidNodeError = _module.InvalidNodeError
    ParseError = _module.ParseError
    from_dict = _module.from_dict
    from_markdown = _module.from_markdown

from .schema import Attr, IntList, MarkSpec, NodeSpec, Schema
from .presets import (
    BLOCK_MATH,
    DETAILS,
    HIGHLIGHT,
    IMAGE_SIZE,
    INLINE_MATH,
    LINK_ATTRS,
    MENTION,
    SUBSCRIPT,
    SUPERSCRIPT,
    TABLE_SPANS,
    TEXT_ALIGN,
    TEXT_STYLE,
    UNDERLINE,
    link_attrs,
    text_align,
    text_style,
)


__all__ = [
    "__version__",
    "Document",
    "Attr",
    "IntList",
    "MarkSpec",
    "NodeSpec",
    "Schema",
    "UNDERLINE",
    "HIGHLIGHT",
    "SUBSCRIPT",
    "SUPERSCRIPT",
    "TEXT_STYLE",
    "MENTION",
    "DETAILS",
    "INLINE_MATH",
    "BLOCK_MATH",
    "TEXT_ALIGN",
    "LINK_ATTRS",
    "IMAGE_SIZE",
    "TABLE_SPANS",
    "text_style",
    "text_align",
    "link_attrs",
    "MarktipError",
    "UnknownTypeError",
    "InvalidNodeError",
    "ParseError",
    "from_markdown",
    "from_dict",
]
