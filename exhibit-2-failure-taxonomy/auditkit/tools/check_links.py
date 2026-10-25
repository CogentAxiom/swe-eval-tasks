"""Check that every relative markdown link in the repository's docs resolves.

    py -3 exhibit-2-failure-taxonomy/auditkit/tools/check_links.py [root]

Scans *.md under the root (default: the repository), extracts [text](target)
links, skips http(s)/mailto/anchors, and verifies the target exists relative to
the file. Exit 1 on any missing target.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

LINK = re.compile(r"\[[^\]]*\]\(([^)\s]+)\)")
SKIP_DIRS = {".git", "__pycache__", "node_modules", "_private", "submission"}


def main() -> int:
    root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[3]
    bad = []
    n_files = n_links = 0
    for md in root.rglob("*.md"):
        if any(part in SKIP_DIRS for part in md.parts):
            continue
        n_files += 1
        for m in LINK.finditer(md.read_text(encoding="utf-8", errors="replace")):
            target = m.group(1)
            if target.startswith(("http://", "https://", "mailto:", "#")):
                continue
            n_links += 1
            path = target.split("#", 1)[0]
            if not path:
                continue
            if not (md.parent / path).exists():
                bad.append(f"{md.relative_to(root)}: ({target})")
    print(f"checked {n_links} relative links in {n_files} files; {len(bad)} missing")
    for b in bad:
        print("  MISSING", b)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
