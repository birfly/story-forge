#!/usr/bin/env python3
"""Story Forge — fetch openly licensed illustrations into a project.

Sources:
  local      copy images from a directory the user already owns
  wikimedia  Wikimedia Commons search API
  openverse  Openverse image API (CC / public domain only)
  auto       try wikimedia, then openverse

Every downloaded image is stored under the project's assets directory and gets
an entry in content/illustrations.json with credit, license and source URL.
The tool never hotlinks: the built site stays offline.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import shutil
import struct
import sys
import urllib.parse
import urllib.request
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

USER_AGENT = "StoryForge/1.1 (offline reading site builder; image fetch)"
MAX_BYTES = 20 * 1024 * 1024
ALLOWED_LICENSE = ("public domain", "cc0", "cc by", "cc-by", "by-sa", "by-sa", "pdm")
TAG_RE = re.compile(r"<[^>]+>")


def strip_html(value: str) -> str:
    return html.unescape(TAG_RE.sub(" ", value or "")).strip()


def license_ok(value: str) -> bool:
    text = (value or "").lower()
    return any(token in text for token in ALLOWED_LICENSE)


def http_json(url: str, timeout: int = 20) -> dict:
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8", "replace"))


def download(url: str, destination: Path) -> int:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme != "https":
        raise ValueError(f"refusing non-https image URL: {url}")
    request = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(request, timeout=30) as response:
        content_type = response.headers.get("Content-Type", "")
        if not content_type.startswith("image/"):
            raise ValueError(f"not an image: {content_type or 'unknown'}")
        data = response.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise ValueError(f"image larger than {MAX_BYTES // 1024 // 1024} MB")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(data)
    return len(data)


def image_size(path: Path) -> tuple[int, int]:
    """Read PNG / JPEG / GIF / WebP dimensions without Pillow."""
    data = path.read_bytes()[:64 * 1024]
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        width, height = struct.unpack(">II", data[16:24])
        return int(width), int(height)
    if data[:6] in (b"GIF87a", b"GIF89a"):
        width, height = struct.unpack("<HH", data[6:10])
        return int(width), int(height)
    if data[:2] == b"\xff\xd8":
        index = 2
        while index + 9 < len(data):
            if data[index] != 0xFF:
                index += 1
                continue
            marker = data[index + 1]
            if marker in (0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF):
                height, width = struct.unpack(">HH", data[index + 5:index + 9])
                return int(width), int(height)
            length = struct.unpack(">H", data[index + 2:index + 4])[0]
            index += 2 + length
        return 0, 0
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        chunk = data[12:16]
        if chunk == b"VP8X" and len(data) >= 30:
            width = 1 + int.from_bytes(data[24:27], "little")
            height = 1 + int.from_bytes(data[27:30], "little")
            return width, height
        if chunk == b"VP8 " and len(data) >= 30:
            width = struct.unpack("<H", data[26:28])[0] & 0x3FFF
            height = struct.unpack("<H", data[28:30])[0] & 0x3FFF
            return width, height
    return 0, 0


def wikimedia_candidates(query: str, limit: int) -> list[dict]:
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": f"filetype:bitmap {query}",
        "gsrnamespace": "6",
        "gsrlimit": str(limit),
        "prop": "imageinfo",
        "iiprop": "url|size|extmetadata",
        "iiurlwidth": "1600",
    }
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)
    data = http_json(url)
    pages = data.get("query", {}).get("pages", {})
    candidates: list[dict] = []
    for page in pages.values():
        info = (page.get("imageinfo") or [{}])[0]
        meta = info.get("extmetadata", {})
        license_name = strip_html(
            meta.get("LicenseShortName", {}).get("value")
            or meta.get("License", {}).get("value")
            or ""
        )
        if not license_ok(license_name):
            continue
        candidates.append(
            {
                "url": info.get("thumburl") or info.get("url"),
                "page": info.get("descriptionurl") or "",
                "title": page.get("title", "").replace("File:", ""),
                "width": info.get("width") or 0,
                "height": info.get("height") or 0,
                "license": license_name,
                "credit": strip_html(
                    meta.get("Artist", {}).get("value")
                    or meta.get("Credit", {}).get("value")
                    or "Wikimedia Commons"
                ),
                "source": "wikimedia",
            }
        )
    return candidates


def openverse_candidates(query: str, limit: int) -> list[dict]:
    params = {
        "q": query,
        "page_size": str(limit),
        "license": "cc0,by,by-sa,pdm",
    }
    url = "https://api.openverse.org/v1/images/?" + urllib.parse.urlencode(params)
    data = http_json(url)
    candidates: list[dict] = []
    for item in data.get("results", []):
        license_name = f"CC {item.get('license', '')} {item.get('license_version', '')}".strip()
        if not license_ok(license_name):
            continue
        candidates.append(
            {
                "url": item.get("url"),
                "page": item.get("foreign_landing_url") or "",
                "title": item.get("title") or "",
                "width": item.get("width") or 0,
                "height": item.get("height") or 0,
                "license": license_name,
                "credit": item.get("creator") or "Openverse",
                "source": "openverse",
            }
        )
    return candidates


def local_candidates(directory: Path, limit: int) -> list[dict]:
    patterns = ("*.jpg", "*.jpeg", "*.png", "*.webp", "*.gif")
    files: list[Path] = []
    for pattern in patterns:
        files.extend(sorted(directory.glob(pattern)))
    return [
        {
            "path": path,
            "title": path.stem,
            "width": 0,
            "height": 0,
            "license": "user-provided",
            "credit": "本地提供",
            "source": "local",
        }
        for path in files[:limit]
    ]


def ensure_manifest(project: Path) -> dict:
    path = project / "content" / "illustrations.json"
    if path.exists():
        data = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            return {"images": data}
        if isinstance(data, dict):
            data.setdefault("images", [])
            return data
    return {"images": []}


def safe_id(value: str) -> str:
    cleaned = re.sub(r"[^a-zA-Z0-9_-]+", "-", value or "").strip("-")
    return cleaned[:48] or "img"


def save_manifest(project: Path, data: dict) -> Path:
    path = project / "content" / "illustrations.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def add_image(
    project: Path,
    data: dict,
    candidate: dict,
    query: str,
    chapter: str,
    section: str,
    after_block: int,
    mode: str,
    image_id: str | None,
    assets_dir: Path,
) -> dict | None:
    existing_urls = {image.get("sourceUrl") for image in data.get("images", [])}
    existing_ids = {str(image.get("id")) for image in data.get("images", [])}
    if candidate.get("page") and candidate["page"] in existing_urls:
        print(f"skip duplicate: {candidate['page']}")
        return None
    base_id = safe_id(image_id or hashlib.sha1(
        (candidate.get("page") or candidate.get("path") or candidate.get("url") or "").encode("utf-8")
    ).hexdigest()[:10])
    final_id = base_id
    suffix_index = 2
    while final_id in existing_ids:
        final_id = f"{base_id}-{suffix_index}"
        suffix_index += 1
    assets_dir.mkdir(parents=True, exist_ok=True)
    if candidate["source"] == "local":
        source_path = Path(candidate["path"])
        digest = hashlib.sha1(source_path.read_bytes()).hexdigest()[:10]
        target = assets_dir / f"{final_id or digest}{source_path.suffix.lower()}"
        shutil.copy2(source_path, target)
        src_url = ""
    else:
        url = candidate.get("url") or ""
        if not url:
            return None
        digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:10]
        suffix = Path(urllib.parse.urlparse(url).path).suffix.lower() or ".jpg"
        target = assets_dir / f"{final_id or digest}{suffix}"
        download(url, target)
        src_url = candidate.get("page") or url
    width, height = image_size(target)
    if not width or not height:
        width, height = int(candidate.get("width") or 0), int(candidate.get("height") or 0)
    relative = target.relative_to(project).as_posix()
    entry = {
        "id": final_id,
        "file": relative,
        "alt": candidate.get("title") or query,
        "caption": candidate.get("title") or query,
        "credit": candidate.get("credit") or "",
        "license": candidate.get("license") or "",
        "sourceUrl": src_url,
        "source": candidate["source"],
        "width": width,
        "height": height,
        "chapter": chapter,
        "section": section,
        "afterBlock": after_block,
        "mode": mode,
        "status": "placed" if section else "unplaced",
        "keywords": [query] if query else [],
    }
    data.setdefault("images", []).append(entry)
    return entry


def main() -> None:
    parser = argparse.ArgumentParser(description="Fetch openly licensed illustrations")
    parser.add_argument("project")
    parser.add_argument("--query", default="", help="search keywords")
    parser.add_argument("--chapter", default="")
    parser.add_argument("--section", default="")
    parser.add_argument("--after-block", type=int, default=0)
    parser.add_argument("--mode", default="both", choices=["both", "original", "retold"])
    parser.add_argument("--source", default="auto", choices=["auto", "wikimedia", "openverse", "local"])
    parser.add_argument("--local-dir", default="")
    parser.add_argument("--limit", type=int, default=1)
    parser.add_argument("--min-width", type=int, default=800)
    parser.add_argument("--id", dest="image_id", default="")
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--assets", default="assets/img", help="project-relative image directory")
    args = parser.parse_args()

    project = Path(args.project).resolve()
    data = ensure_manifest(project)
    assets_dir = project / args.assets

    candidates: list[dict] = []
    if args.source in ("auto", "local") and args.local_dir:
        candidates = local_candidates(Path(args.local_dir), args.limit)
    if not candidates and args.source in ("auto", "wikimedia") and args.query:
        try:
            candidates = wikimedia_candidates(args.query, args.limit * 3)
        except Exception as error:  # network is optional
            print(f"wikimedia failed: {error}")
    if not candidates and args.source in ("auto", "openverse") and args.query:
        try:
            candidates = openverse_candidates(args.query, args.limit * 3)
        except Exception as error:
            print(f"openverse failed: {error}")
    candidates = [item for item in candidates if int(item.get("width") or 0) >= args.min_width or item["source"] == "local"]
    candidates = candidates[: args.limit]
    if not candidates:
        raise SystemExit("no licensed image candidates found")

    for index, candidate in enumerate(candidates):
        print(
            f"- {candidate['source']}: {candidate.get('title')} "
            f"({candidate.get('width')}x{candidate.get('height')}, {candidate.get('license')})"
        )
        if candidate.get("page"):
            print(f"  {candidate['page']}")
        if args.dry_run:
            continue
        image_id = f"{args.image_id}-{index + 1}" if args.image_id and len(candidates) > 1 else args.image_id or None
        entry = add_image(
            project,
            data,
            candidate,
            args.query,
            args.chapter,
            args.section,
            args.after_block,
            args.mode,
            image_id,
            assets_dir,
        )
        if entry:
            print(f"  saved {entry['file']}")

    if args.dry_run:
        print("dry-run: manifest unchanged")
        return
    path = save_manifest(project, data)
    print(f"manifest: {path}")
    print("next: python engine/tools/place_illustrations.py <project> --apply")


if __name__ == "__main__":
    main()
