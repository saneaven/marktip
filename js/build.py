"""Compile the wrapper and assemble the files shipped by the JS package."""

from pathlib import Path
import shutil
import subprocess


PACKAGE = Path(__file__).resolve().parent
ROOT = PACKAGE.parent
DIST = PACKAGE / "dist"


def main():
    if DIST.exists():
        shutil.rmtree(DIST)
    shutil.copyfile(ROOT / "python/marktip/presets.json", PACKAGE / "presets.json")
    subprocess.run(["tsc", "--project", str(PACKAGE / "tsconfig.json")], check=True)
    for name in ("marktip.mjs", "marktip.wasm"):
        shutil.copyfile(ROOT / "build-wasm" / name, DIST / name)
    shutil.copyfile(PACKAGE / "presets.json", DIST / "presets.json")
    licenses = DIST / "licenses"
    licenses.mkdir()
    for source, name in (
        ("LICENSE", "marktip-LICENSE"),
        ("third_party/md4c/LICENSE.md", "md4c-LICENSE.md"),
        ("third_party/md4c/upstream_metadata/Unicode-LICENSE.txt", "Unicode-LICENSE.txt"),
        ("third_party/yyjson/LICENSE", "yyjson-LICENSE"),
    ):
        shutil.copyfile(ROOT / source, licenses / name)


if __name__ == "__main__":
    main()
