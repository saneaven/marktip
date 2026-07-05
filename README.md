# marktip

Fast C++/MD4C Markdown conversion for Tiptap-style JSON.

## Installation

```bash
python -m pip install marktip
```

Release wheels are built for common CPython versions on Linux, macOS, and
Windows. If a wheel is not available for a platform, pip can build from the
source distribution with a C++17 compiler and standard Python build tooling.

## Usage

```python
import marktip as tm

doc = tm.from_markdown("# Hello")
ast = doc.to_dict()
markdown = doc.to_markdown()

doc = tm.from_dict(ast)
```

The first version targets GFM core syntax and canonical Markdown output rather
than byte-identical source preservation.

## Development

```bash
python -m pip install .[test]
python -m pytest
```

For a direct local CMake build:

```bash
cmake -S . -B build -G Ninja -DCMAKE_BUILD_TYPE=Release \
  -Dpybind11_DIR="$(python -m pybind11 --cmakedir)"
cmake --build build
PYTHONPATH=python python -m pytest
PYTHONPATH=python python scripts/benchmark.py
```
