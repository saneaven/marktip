"""Plain declarations compiled by :class:`marktip.Schema`."""

from __future__ import annotations

from dataclasses import dataclass, field

from ._core import Schema as _CompiledSchema


@dataclass(frozen=True)
class Attr:
    type: type
    required: bool = False
    choices: tuple[object, ...] | None = None
    default: object = None
    uri: str | None = None


@dataclass(frozen=True)
class MarkSpec:
    name: str
    tag: str | None = None
    attrs: dict[str, Attr] = field(default_factory=dict)
    excludes: tuple[str, ...] | str | None = None


def _attr_from_dict(data: dict) -> Attr:
    name = data.get("type")
    types = {"str": str, "int": int, "bool": bool}
    if name not in types:
        raise ValueError("attr type must be 'str', 'int' or 'bool'")
    return Attr(types[name], data.get("required", False), data.get("choices"), data.get("default"), data.get("uri"))


class Schema(_CompiledSchema):
    __slots__ = ("_marks", "_key")

    def __init__(self, *, marks=()):
        marks = tuple(marks)
        super().__init__(marks=marks)
        self._marks = marks
        self._key = tuple(
            (mark.name, mark.tag, tuple(
                (name, attr.type, attr.required, None if attr.choices is None else tuple(attr.choices),
                 attr.default, attr.uri)
                for name, attr in mark.attrs.items()
            ), mark.excludes)
            for mark in marks
        )

    @property
    def marks(self) -> tuple[MarkSpec, ...]:
        return self._marks

    def to_dict(self) -> dict:
        return {"marks": [
            {"name": mark.name, "tag": mark.tag, "attrs": {
                name: {"type": attr.type.__name__, "required": attr.required,
                       "choices": None if attr.choices is None else list(attr.choices),
                       "default": attr.default, "uri": attr.uri}
                for name, attr in mark.attrs.items()
            }, "excludes": list(mark.excludes) if isinstance(mark.excludes, tuple) else mark.excludes}
            for mark in self._marks
        ]}

    @classmethod
    def from_dict(cls, data: dict) -> Schema:
        marks = []
        for mark in data["marks"]:
            attrs = mark.get("attrs", {})
            excludes = mark.get("excludes")
            if isinstance(excludes, list):
                excludes = tuple(excludes)
            marks.append(MarkSpec(mark.get("name"), mark.get("tag"),
                                  {name: _attr_from_dict(attr) for name, attr in attrs.items()}, excludes))
        return cls(marks=marks)

    def extend(self, *, marks=()) -> Schema:
        return type(self)(marks=(*self._marks, *marks))

    def __eq__(self, other):
        if not isinstance(other, Schema):
            return NotImplemented
        return self._key == other._key

    def __hash__(self):
        return hash(self._key)
