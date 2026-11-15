"""Implicit wrappers must have an unambiguous visible content boundary."""

import pytest

import marktip as tm


def test_an_implicit_wrapper_cannot_contain_another_implicit_wrapper():
    with pytest.raises(ValueError):
        tm.Schema(nodes=[
            tm.NodeSpec("layout", "block", content="outer"),
            tm.NodeSpec("outer", "block", content="inner", group="", implicit=True),
            tm.NodeSpec("inner", "block", content="paragraph+", group="", implicit=True),
        ])
