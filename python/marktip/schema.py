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


@dataclass(frozen=True)
class NodeSpec:
    name: str
    kind: str
    content: str | None = None
    group: str | None = None
    tag: str | None = None
    attrs: dict[str, Attr] = field(default_factory=dict)
    implicit: bool = False
    fence: str | None = None
    math: str | None = None
    body: str | None = None


def _attr_from_dict(data: dict) -> Attr:
    name = data.get("type")
    types = {"str": str, "int": int, "bool": bool}
    if name not in types:
        raise ValueError("attr type must be 'str', 'int' or 'bool'")
    return Attr(types[name], data.get("required", False), data.get("choices"), data.get("default"), data.get("uri"))


def _attrs_key(attrs: dict[str, Attr]) -> tuple:
    return tuple(
        (name, attr.type, attr.required, None if attr.choices is None else tuple(attr.choices), attr.default, attr.uri)
        for name, attr in attrs.items()
    )


def _attrs_to_dict(attrs: dict[str, Attr]) -> dict:
    return {
        name: {"type": attr.type.__name__, "required": attr.required,
               "choices": None if attr.choices is None else list(attr.choices),
               "default": attr.default, "uri": attr.uri}
        for name, attr in attrs.items()
    }


class Schema(_CompiledSchema):
    __slots__ = ("_marks", "_nodes", "_key")

    def __init__(self, *, marks=(), nodes=()):
        marks = tuple(marks)
        nodes = tuple(nodes)
        super().__init__(marks=marks, nodes=nodes)
        self._marks = marks
        self._nodes = nodes
        self._key = (
            tuple((mark.name, mark.tag, _attrs_key(mark.attrs), mark.excludes) for mark in marks),
            tuple((node.name, node.kind, node.content, node.group, node.tag, _attrs_key(node.attrs), node.implicit,
                   node.fence, node.math, node.body)
                  for node in nodes),
        )

    @property
    def marks(self) -> tuple[MarkSpec, ...]:
        return self._marks

    @property
    def nodes(self) -> tuple[NodeSpec, ...]:
        return self._nodes

    def to_dict(self) -> dict:
        declaration = {"marks": [
            {"name": mark.name, "tag": mark.tag, "attrs": _attrs_to_dict(mark.attrs),
             "excludes": list(mark.excludes) if isinstance(mark.excludes, tuple) else mark.excludes}
            for mark in self._marks
        ]}
        if self._nodes:
            declaration["nodes"] = [
                {"name": node.name, "kind": node.kind, "content": node.content, "group": node.group,
                 "tag": node.tag, "attrs": _attrs_to_dict(node.attrs), "implicit": node.implicit,
                 "fence": node.fence, "math": node.math, "body": node.body}
                for node in self._nodes
            ]
        return declaration

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
        nodes = [
            NodeSpec(node.get("name"), node.get("kind"), node.get("content"), node.get("group"), node.get("tag"),
                     {name: _attr_from_dict(attr) for name, attr in node.get("attrs", {}).items()},
                     node.get("implicit", False), node.get("fence"), node.get("math"), node.get("body"))
            for node in data.get("nodes", ())
        ]
        return cls(marks=marks, nodes=nodes)

    def extend(self, *, marks=(), nodes=()) -> Schema:
        return type(self)(marks=(*self._marks, *marks), nodes=(*self._nodes, *nodes))

    def __eq__(self, other):
        if not isinstance(other, Schema):
            return NotImplemented
        return self._key == other._key

    def __hash__(self):
        return hash(self._key)
