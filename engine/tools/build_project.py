#!/usr/bin/env python3
"""Story Forge — build a project: copy site template on first run, parse data."""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
TOOLS = ENGINE / "tools"


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: build_project.py <project-dir> [--single] [--sync-template]")
    project = Path(sys.argv[1]).resolve()
    site = project / "site"
    if not project.exists():
        raise SystemExit(f"project not found: {project}")
    if not (site / "index.html").exists():
        shutil.copytree(ENGINE / "site", site, dirs_exist_ok=True)
        print(f"copied site template -> {site}")
    elif "--sync-template" in sys.argv[2:]:
        shutil.copy2(ENGINE / "site" / "index.html", site / "index.html")
        for folder in ("assets/css", "assets/js"):
            target = site / folder
            if target.exists():
                shutil.rmtree(target)
            shutil.copytree(ENGINE / "site" / folder, target)
        print("site template synced (data preserved)")

    parse = [
        sys.executable,
        str(TOOLS / "parse_chapters.py"),
        str(project),
    ]
    result = subprocess.run(parse)
    if result.returncode != 0:
        raise SystemExit("parse/validation failed; fix the report above")

    assets = project / "assets"
    if assets.exists():
        target_assets = site / "assets"
        shutil.copytree(assets, target_assets, dirs_exist_ok=True)
        print(f"copied illustrations -> {target_assets}")

    if "--single" in sys.argv[2:]:
        single = subprocess.run(
            [sys.executable, str(TOOLS / "build_singlefile.py"), str(project)]
        )
        if single.returncode != 0:
            raise SystemExit("single-file build failed")

    print("\nbuild complete.")
    print(f"open: {site / 'index.html'}")
    print("serve: python -m http.server 8000 --directory site")


if __name__ == "__main__":
    main()
