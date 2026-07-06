"""Fast Markdown conversion for Tiptap-style JSON."""

try:
    from ._core import Document, UnknownTypeError, __version__, from_dict, from_markdown
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
    UnknownTypeError = _module.UnknownTypeError
    from_dict = _module.from_dict
    from_markdown = _module.from_markdown

__all__ = ["__version__", "Document", "UnknownTypeError", "from_markdown", "from_dict"]
