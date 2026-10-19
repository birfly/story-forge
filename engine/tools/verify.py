#!/usr/bin/env python3
"""Story Forge — end-to-end verification.

Checks:
1. text fidelity + data validation (delegated to parse_chapters.py --check)
2. no network dependencies in the built site
3. required data files exist
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
TOOLS = ENGINE / "tools"

FORBIDDEN = [
    (re.compile(r"<script\s+src=\"http"), "external script"),
    (re.compile(r"<link[^>]+href=\"http"), "external stylesheet"),
    (re.compile(r"<img\s+[^>]*src=\"http"), "external image"),
    (re.compile(r"fetch\s*\("), "fetch()"),
    (re.compile(r"XMLHttpRequest"), "XMLHttpRequest"),
    (re.compile(r"type=\"module\""), "ES module"),
    (re.compile(r"new\s+Worker"), "Worker"),
    (re.compile(r"@import\s+url"), "CSS @import"),
]


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    if len(sys.argv) < 2:
        raise SystemExit("usage: verify.py <project-dir>")
    project = Path(sys.argv[1]).resolve()
    site = project / "site"
    data = site / "data"

    errors: list[str] = []
    required = [
        "config.js",
        "chapters.js",
        "entities.js",
        "meta.js",
        "recap.js",
        "worldview.js",
    ]
    index_path = site / "index.html"
    index_text = (
        index_path.read_text(encoding="utf-8", errors="ignore")
        if index_path.exists()
        else ""
    )
    for optional in ("timeline.js", "mentions.js"):
        if optional in index_text:
            required.append(optional)
    for name in required:
        if not (data / name).exists():
            errors.append(f"missing data file: {data / name}")

    print("== fidelity / data validation ==")
    result = subprocess.run(
        [sys.executable, str(TOOLS / "parse_chapters.py"), str(project), "--check"]
    )
    if result.returncode != 0:
        errors.append("parse/validation reported problems")

    print("\n== offline scan ==")
    targets = list(site.rglob("*.html")) + list(site.rglob("*.js")) + list(site.rglob("*.css"))
    offline_errors: list[str] = []
    for target in targets:
        text = target.read_text(encoding="utf-8", errors="ignore")
        for pattern, label in FORBIDDEN:
            if pattern.search(text):
                offline_errors.append(f"{target.relative_to(project)}: {label}")
    errors.extend(offline_errors)
    if offline_errors:
        print(f"  scanned {len(targets)} files: {len(offline_errors)} problem(s)")
    else:
        print(f"  scanned {len(targets)} files: no network dependencies")

    print("\nRESULT:", "PASS" if not errors else "FAIL")
    for error in errors:
        print(f"  - {error}")
    sys.exit(0 if not errors else 1)


if __name__ == "__main__":
    main()
