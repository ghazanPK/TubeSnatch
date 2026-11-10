"""Compare package versions between two uv.lock files.

    python scripts/lock_diff.py OLD_LOCK NEW_LOCK

Prints one "- name: old → new" line per changed package (nothing if equal).
"""

import sys
import tomllib


def versions(path: str) -> dict[str, str]:
    with open(path, "rb") as f:
        data = tomllib.load(f)
    return {p["name"]: p.get("version", "") for p in data.get("package", []) if p.get("name") != "tubesnatch"}


def main() -> None:
    old, new = versions(sys.argv[1]), versions(sys.argv[2])
    for name in sorted(set(old) | set(new)):
        if old.get(name) != new.get(name):
            print(f"- {name}: {old.get(name, '—')} → {new.get(name, '—')}")


if __name__ == "__main__":
    main()
