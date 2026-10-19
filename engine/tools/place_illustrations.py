#!/usr/bin/env python3
"""Story Forge — place illustrations at suitable sections.

Reads build/chapters.json and content/illustrations.json. For every image that
has no section (or is marked unplaced), picks a section by keyword overlap or
distributes images evenly across the chapter. Writes the manifest with --apply.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

MIN_SECTION_CHARS = 160


def load_json(path: Path, fallback):
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def variants_of(chapter: dict) -> dict[str, dict]:
    if isinstance(chapter.get("variants"), dict):
        return chapter["variants"]
    mode = chapter.get("defaultMode") or (chapter.get("modeNames") or ["original"])[0]
    return {mode: chapter}


def sections_of(chapter: dict) -> list[dict]:
    variants = variants_of(chapter)
    mode = chapter.get("defaultMode") or next(iter(variants))
    parts = variants.get(mode, {}).get("parts", [])
    sections = []
    for part in parts:
        for section in part.get("sections", []):
            text = section.get("title", "") + "".join(
                block.get("text", "") for block in section.get("blocks", [])
            )
            sections.append({"id": section["id"], "title": section.get("title", ""), "text": text})
    return sections


def score_section(section: dict, keywords: list[str]) -> int:
    score = 0
    for keyword in keywords:
        keyword = keyword.strip()
        if not keyword:
            continue
        score += section["text"].count(keyword)
        if keyword in section["title"]:
            score += 5
    return score


def candidates(sections: list[dict]) -> list[dict]:
    long_sections = [item for item in sections if len(item["text"]) >= MIN_SECTION_CHARS]
    return long_sections or sections


def choose_by_keywords(sections: list[dict], keywords: list[str], used: set[str]) -> dict | None:
    ranked = sorted(
        ((score_section(section, keywords), section) for section in sections),
        key=lambda item: item[0],
        reverse=True,
    )
    for score, section in ranked:
        if score > 0 and section["id"] not in used:
            return section
    return None


def choose_even(sections: list[dict], index: int, total: int, used: set[str]) -> dict | None:
    pool = candidates(sections)
    if not pool:
        return None
    free = [section for section in pool if section["id"] not in used] or pool
    # Spread placements across the chapter: 1 image -> 1/3, 2 -> 1/3+2/3, ...
    position = (index + 1) / (total + 1)
    target = min(len(free) - 1, max(0, int(position * len(free))))
    return free[target]


def place(project: Path, apply: bool, max_per_chapter: int, only_chapter: str = "") -> None:
    chapters = load_json(project / "build" / "chapters.json", [])
    if not chapters:
        raise SystemExit("build/chapters.json missing; run story.py parse first")
    manifest_path = project / "content" / "illustrations.json"
    manifest = load_json(manifest_path, {"images": []})
    images = manifest.get("images", [])
    if not images:
        raise SystemExit("no images in content/illustrations.json")

    chapter_map = {str(chapter["id"]): chapter for chapter in chapters}
    used_by_chapter: dict[str, set[str]] = {}
    counts: dict[str, int] = {}
    assigned = 0

    for image in images:
        if only_chapter and str(image.get("chapter", "")) != only_chapter:
            continue
        if image.get("section") and image.get("status", "placed") == "placed":
            used_by_chapter.setdefault(str(image["chapter"]), set()).add(str(image["section"]))
            counts[str(image["chapter"])] = counts.get(str(image["chapter"]), 0) + 1
            continue
        chapter_id = str(image.get("chapter") or "")
        if not chapter_id:
            # Spread across chapters that still have room.
            ordered = sorted(chapters, key=lambda item: int(item.get("order", 0)))
            chapter_id = next(
                (
                    str(chapter["id"])
                    for chapter in ordered
                    if counts.get(str(chapter["id"]), 0) < max_per_chapter
                ),
                str(ordered[0]["id"]),
            )
            image["chapter"] = chapter_id
        chapter = chapter_map.get(chapter_id)
        if chapter is None:
            print(f"skip {image.get('id')}: unknown chapter {chapter_id}")
            continue
        if counts.get(chapter_id, 0) >= max_per_chapter:
            print(f"skip {image.get('id')}: {chapter_id} already has {counts[chapter_id]} images")
            continue
        sections = sections_of(chapter)
        if not sections:
            print(f"skip {image.get('id')}: {chapter_id} has no sections")
            continue
        used = used_by_chapter.setdefault(chapter_id, set())
        keywords = [str(item) for item in image.get("keywords", []) if str(item).strip()]
        target = choose_by_keywords(sections, keywords, used)
        method = "keyword"
        if target is None:
            index = counts.get(chapter_id, 0)
            target = choose_even(sections, index, max_per_chapter, used)
            method = "even"
        if target is None:
            continue
        image["section"] = target["id"]
        image.setdefault("afterBlock", 0)
        image.setdefault("mode", "both")
        image["status"] = "placed"
        image["placement"] = method
        used.add(target["id"])
        counts[chapter_id] = counts.get(chapter_id, 0) + 1
        assigned += 1
        print(f"{image.get('id')} -> {chapter_id} / {target['id']} ({method}) {target['title']}")

    if apply:
        manifest_path.write_text(
            json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        print(f"updated {manifest_path} ({assigned} placed)")
    else:
        print(f"dry-run: {assigned} would be placed; add --apply to write")


def main() -> None:
    parser = argparse.ArgumentParser(description="Place illustrations in sections")
    parser.add_argument("project")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--max-per-chapter", type=int, default=0)
    parser.add_argument("--chapter", default="")
    args = parser.parse_args()
    project = Path(args.project).resolve()
    config = load_json(project / "project.json", {})
    configured = int(
        (config.get("illustrations") or {}).get("maxPerChapter") or 4
    )
    place(project, args.apply, args.max_per_chapter or configured, args.chapter)


if __name__ == "__main__":
    main()
