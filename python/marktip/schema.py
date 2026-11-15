"""Plain declarations compiled by :class:`marktip.Schema`."""

from __future__ import annotations

from dataclasses import dataclass, field

from ._core import IntList, Schema as _CompiledSchema


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
    types = {"str": str, "int": int, "bool": bool, "IntList": IntList}
    if name not in types:
        raise ValueError("attr type must be 'str', 'int', 'bool' or 'IntList'")
    return Attr(types[name], data.get("required", False), data.get("choices"), data.get("default"), data.get("uri"))


def _attrs_from_dict(data: dict) -> dict[str, Attr]:
    return {name: _attr_from_dict(attr) for name, attr in data.items()}


def _mark_from_dict(data: dict) -> MarkSpec:
    excludes = data.get("excludes")
    if isinstance(excludes, list):
        excludes = tuple(excludes)
    return MarkSpec(data.get("name"), data.get("tag"), _attrs_from_dict(data.get("attrs", {})), excludes)


def _node_from_dict(data: dict) -> NodeSpec:
    return NodeSpec(data.get("name"), data.get("kind"), data.get("content"), data.get("group"), data.get("tag"),
                    _attrs_from_dict(data.get("attrs", {})), data.get("implicit", False),
                    data.get("fence"), data.get("math"), data.get("body"))


def _attrs_key(attrs: dict[str, Attr]) -> tuple:
    def value_key(value):
        return tuple(value) if isinstance(value, list) else value

    return tuple(
        (name, attr.type, attr.required,
         None if attr.choices is None else tuple(value_key(value) for value in attr.choices),
         value_key(attr.default), attr.uri)
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
    __slots__ = ("_marks", "_nodes", "_core_attrs", "_key")

    def __init__(self, *, marks=(), nodes=(), core_attrs=None):
        marks = tuple(marks)
        nodes = tuple(nodes)
        if core_attrs is None:
            core_attrs = {}
        super().__init__(marks=marks, nodes=nodes, core_attrs=core_attrs)
        self._marks = marks
        self._nodes = nodes
        self._core_attrs = {name: dict(attrs) for name, attrs in core_attrs.items()}
        self._key = (
            tuple((mark.name, mark.tag, _attrs_key(mark.attrs), mark.excludes) for mark in marks),
            tuple((node.name, node.kind, node.content, node.group, node.tag, _attrs_key(node.attrs), node.implicit,
                   node.fence, node.math, node.body)
                  for node in nodes),
            tuple((name, _attrs_key(attrs)) for name, attrs in self._core_attrs.items()),
        )

    @property
    def marks(self) -> tuple[MarkSpec, ...]:
        return self._marks

    @property
    def nodes(self) -> tuple[NodeSpec, ...]:
        return self._nodes

    @property
    def core_attrs(self) -> dict[str, dict[str, Attr]]:
        return self._core_attrs

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
        if self._core_attrs:
            declaration["core_attrs"] = {
                name: _attrs_to_dict(attrs) for name, attrs in self._core_attrs.items()
            }
        return declaration

    @classmethod
    def from_dict(cls, data: dict) -> Schema:
        marks = [_mark_from_dict(mark) for mark in data["marks"]]
        nodes = [_node_from_dict(node) for node in data.get("nodes", ())]
        core_attrs = {
            name: _attrs_from_dict(attrs)
            for name, attrs in data.get("core_attrs", {}).items()
        }
        return cls(marks=marks, nodes=nodes, core_attrs=core_attrs)

    def extend(self, *, marks=(), nodes=(), core_attrs=None) -> Schema:
        combined = {name: dict(attrs) for name, attrs in self._core_attrs.items()}
        if core_attrs is None:
            core_attrs = {}
        for name, attrs in core_attrs.items():
            target = combined.setdefault(name, {})
            for attr_name, attr in attrs.items():
                if attr_name in target:
                    raise ValueError(f"duplicate core attr '{name}.{attr_name}'")
                target[attr_name] = attr
        return type(self)(marks=(*self._marks, *marks), nodes=(*self._nodes, *nodes), core_attrs=combined)

    def __eq__(self, other):
        if not isinstance(other, Schema):
            return NotImplemented
        return self._key == other._key

    def __hash__(self):
        return hash(self._key)
