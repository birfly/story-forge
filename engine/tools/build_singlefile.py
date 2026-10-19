#!/usr/bin/env python3
"""Story Forge — inline CSS, JS and data into one standalone HTML file."""
from __future__ import annotations

import base64
import json
import mimetypes
import re
import sys
from pathlib import Path

IMG_PATTERN = re.compile(r'(<img\b[^>]*?\bsrc=")([^"]+)(")')
DATA_IMG_PATTERN = re.compile(
    r'"src":"([^"]+\.(?:png|jpe?g|webp|gif|svg|avif))"'
)


def data_uri(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    payload = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{payload}"


def inline_images(html: str, site: Path, project: Path) -> tuple[str, int, int]:
    """Inline static <img> tags in the HTML shell."""
    total = [0, 0]

    def resolve(src: str) -> Path | None:
        if src.startswith(("data:", "http://", "https://")):
            return None
        return next(
            (item for item in (site / src, project / src) if item.exists()),
            None,
        )

    def replace(match: re.Match) -> str:
        src = match.group(2)
        path = resolve(src)
        if path is None:
            if not src.startswith(("data:", "http")):
                print(f"warning: image not found for single file: {src}")
            return match.group(0)
        total[0] += path.stat().st_size
        total[1] += 1
        return f"{match.group(1)}{data_uri(path)}{match.group(3)}"

    html = IMG_PATTERN.sub(replace, html)
    return html, total[0], total[1]


def build_image_map(html: str, site: Path, project: Path) -> tuple[str, int, int]:
    """Embed chapter images once and let the reader resolve them at runtime."""
    mapping: dict[str, str] = {}
    total = 0
    for src in sorted(set(DATA_IMG_PATTERN.findall(html))):
        path = next(
            (item for item in (site / src, project / src) if item.exists()), None
        )
        if path is None:
            print(f"warning: image not found for single file: {src}")
            continue
        mapping[src] = data_uri(path)
        total += path.stat().st_size
    if not mapping:
        return html, 0, 0
    payload = json.dumps(mapping, ensure_ascii=False, separators=(",", ":"))
    script = f"<script>window.STORY_IMAGES={payload};</script>\n</head>"
    html = html.replace("</head>", script, 1)
    return html, total, len(mapping)





def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: build_singlefile.py <project-dir> [--out path]")
    project = Path(sys.argv[1]).resolve()
    config_path = project / "project.json"
    config = (
        json.loads(config_path.read_text(encoding="utf-8"))
        if config_path.exists()
        else {}
    )
    site = project / config.get("siteDir", "site")
    index = site / "index.html"
    if not index.exists():
        raise SystemExit(f"missing site entry: {index}")

    html = index.read_text(encoding="utf-8")
    css_pattern = re.compile(r'<link\s+rel="stylesheet"\s+href="([^"]+)"\s*/?>')
    script_pattern = re.compile(r'<script\s+src="([^"]+)"\s*></script>')

    def inline_css(match: re.Match) -> str:
        path = site / match.group(1)
        return f"<style>\n{path.read_text(encoding='utf-8')}\n</style>"

    def inline_js(match: re.Match) -> str:
        path = site / match.group(1)
        code = path.read_text(encoding="utf-8").replace("</script", "<\\/script")
        return f"<script>\n{code}\n</script>"

    html = css_pattern.sub(inline_css, html)
    html = script_pattern.sub(inline_js, html)
    if "--no-inline-images" not in sys.argv[2:]:
        html, image_bytes, image_count = inline_images(html, site, project)
        html, data_bytes, data_count = build_image_map(html, site, project)
        image_bytes += data_bytes
        image_count += data_count
        if image_count:
            print(f"inlined images: {image_count} ({image_bytes / 1024 / 1024:.2f} MB)")

    # Guard against accidental network dependencies.
    for forbidden in (
        '<script src="http',
        '<link rel="stylesheet" href="http',
        '<img src="http',
    ):
        if forbidden in html:
            raise SystemExit(f"external dependency found: {forbidden}")

    out_dir = project / "dist"
    out_dir.mkdir(parents=True, exist_ok=True)
    slug = config.get("slug") or project.name
    out = Path(sys.argv[sys.argv.index("--out") + 1]) if "--out" in sys.argv else out_dir / f"{slug}.html"
    out.write_text(html, encoding="utf-8")
    alias = out_dir / "story.html"
    if alias != out:
        alias.write_text(html, encoding="utf-8")

    size = out.stat().st_size
    print(f"single file: {out} ({size / 1024 / 1024:.2f} MB)")
    print(f"alias:       {alias}")
    if size > 3 * 1024 * 1024:
        print("warning: file is larger than 3 MB")


if __name__ == "__main__":
    main()
