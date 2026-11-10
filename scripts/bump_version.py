"""Bump TubeSnatch's version (patch by default) in __init__.py and pyproject.toml.

    python scripts/bump_version.py            # 1.1.0 -> 1.1.1
    python scripts/bump_version.py minor      # 1.1.3 -> 1.2.0
    python scripts/bump_version.py 2.0.0      # explicit

Prints the new version.
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
INIT = ROOT / "src" / "tubesnatch" / "__init__.py"
PYPROJECT = ROOT / "pyproject.toml"


def current() -> str:
    return re.search(r'__version__ = "([^"]+)"', INIT.read_text(encoding="utf-8")).group(1)


def bump(v: str, part: str) -> str:
    if re.fullmatch(r"\d+\.\d+\.\d+", part):
        return part
    major, minor, patch = (int(x) for x in v.split("."))
    if part == "major":
        return f"{major + 1}.0.0"
    if part == "minor":
        return f"{major}.{minor + 1}.0"
    return f"{major}.{minor}.{patch + 1}"


def main() -> None:
    part = sys.argv[1] if len(sys.argv) > 1 else "patch"
    new = bump(current(), part)
    INIT.write_text(re.sub(r'__version__ = "[^"]+"', f'__version__ = "{new}"', INIT.read_text(encoding="utf-8")),
                    encoding="utf-8")
    text = PYPROJECT.read_text(encoding="utf-8")
    PYPROJECT.write_text(re.sub(r'(?m)^version = "[^"]+"', f'version = "{new}"', text, count=1), encoding="utf-8")
    print(new)


if __name__ == "__main__":
    main()
