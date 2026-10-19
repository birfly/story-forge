#!/usr/bin/env python3
"""Story Forge — config-driven chapter parser and data builder.

Usage:
    python parse_chapters.py <project-dir> [--check]

Reads <project-dir>/project.json, parses the configured Markdown chapter files,
annotates the first mention of each entity per chapter, writes the reader data
files into <project-dir>/site/data/, and verifies text fidelity.

Design rules:
- Bulk prose is never retyped: the parser transforms the source Markdown.
- The model only authors structured metadata (entities, relations, recap...).
- Single-character names are never auto-annotated; use manual_links.json.
"""
from __future__ import annotations

import html as html_lib
import json
import re
import sys
from pathlib import Path

HANZI_RE = re.compile(r"[一-鿿]")
TEXT_CHAR_RE = re.compile(r"[一-鿿A-Za-z0-9]")
FIDELITY_RE = re.compile(r"[一-鿿A-Za-z0-9]+")
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
HEADING_RE = re.compile(r"^(#{1,4})\s+(.*)$")
LIST_RE = re.compile(r"^\s*(?:[-*]|\d+\.)\s+(.*)$")
HR_RE = re.compile(r"^\s*(?:---|\*\*\*|___)\s*$")
TAG_RE = re.compile(r"<[^>]+>")
MARKER_RE = re.compile(r"\x00[^\x00]*\x00[^\x00]*\x00")


def count_hanzi(text: str) -> int:
    return len(HANZI_RE.findall(text))


def count_text_chars(text: str) -> int:
    """Count CJK characters plus Latin letters and digits (for statistics)."""
    return len(TEXT_CHAR_RE.findall(text))


def esc(text: str) -> str:
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def strip_tags(html: str) -> str:
    return html_lib.unescape(TAG_RE.sub("", html))


def normalize_for_fidelity(text: str) -> str:
    """Keep CJK and alphanumeric runs, preserving order.

    Punctuation and whitespace are ignored, but Latin letters and digits are
    kept so translation variants are checked as well as Chinese source text.
    """
    return "".join(FIDELITY_RE.findall(text))


class Annotator:
    """Wrap the first mention of each entity per chapter in a private marker."""

    def __init__(self, content_dir: Path):
        entities_path = content_dir / "entities.json"
        manual_path = content_dir / "manual_links.json"
        data = (
            json.loads(entities_path.read_text(encoding="utf-8"))
            if entities_path.exists()
            else {"entities": [], "relations": []}
        )
        self.entities = {entity["id"]: entity for entity in data.get("entities", [])}
        alias_pairs: list[tuple[str, str]] = []
        for entity in data.get("entities", []):
            for alias in entity.get("aliases", []):
                if len(alias) >= 2:  # single-character names need manual anchors
                    alias_pairs.append((alias, entity["id"]))
        alias_pairs.sort(key=lambda pair: -len(pair[0]))
        self.alias_map: dict[str, str] = {}
        for alias, entity_id in alias_pairs:
            self.alias_map.setdefault(alias, entity_id)
        pattern = "|".join(re.escape(alias) for alias, _ in alias_pairs)
        self.alias_re = re.compile(pattern) if pattern else None
        self.manual: dict[tuple[str, str], list[dict]] = {}
        self.manual_chapter: dict[str, list[dict]] = {}
        if manual_path.exists():
            for link in json.loads(manual_path.read_text(encoding="utf-8")).get("links", []):
                chapter_id = str(link.get("chapter", ""))
                if link.get("section"):
                    self.manual.setdefault(
                        (chapter_id, str(link["section"])), []
                    ).append(link)
                else:
                    self.manual_chapter.setdefault(chapter_id, []).append(link)
        self.chapter_id = ""
        self.used: set[str] = set()

    def start_chapter(self, chapter_id: str) -> None:
        self.chapter_id = chapter_id
        self.used = set()

    def _apply_link(self, raw: str, link: dict) -> str:
        entity_id = link["entity"]
        if entity_id in self.used:
            return raw
        quote, target = link["quote"], link["target"]
        index = raw.find(quote)
        if index < 0 or target not in quote:
            return raw
        start = index + quote.find(target)
        raw = (
            raw[:start]
            + f"\x00{entity_id}\x00{target}\x00"
            + raw[start + len(target):]
        )
        self.used.add(entity_id)
        return raw

    def annotate(self, raw: str, chapter_id: str, section_id: str) -> str:
        if not raw:
            return raw
        if chapter_id != self.chapter_id:
            self.start_chapter(chapter_id)

        for link in self.manual.get((chapter_id, section_id), []):
            raw = self._apply_link(raw, link)
        for link in self.manual_chapter.get(chapter_id, []):
            raw = self._apply_link(raw, link)

        if not self.alias_re:
            return raw

        chunks: list[str] = []
        pos = 0
        for marker in MARKER_RE.finditer(raw):
            chunks.append(self._annotate_segment(raw[pos:marker.start()]))
            chunks.append(marker.group(0))
            pos = marker.end()
        chunks.append(self._annotate_segment(raw[pos:]))
        return "".join(chunks)

    def _annotate_segment(self, text: str) -> str:
        if not text or not self.alias_re:
            return text

        def replace(match: re.Match) -> str:
            alias = match.group(0)
            entity_id = self.alias_map.get(alias)
            if not entity_id or entity_id in self.used:
                return alias
            self.used.add(entity_id)
            return f"\x00{entity_id}\x00{alias}\x00"

        return self.alias_re.sub(replace, text)


def render_inline(
    raw: str,
    sources: list[dict],
    related: list[dict],
    annotator: Annotator | None,
    chapter_id: str,
    section_id: str,
) -> str:
    """Render the Markdown subset used by chapter files.

    Links are collected into the chapter footer instead of staying inline.
    """
    parts: list[str] = []
    pos = 0
    for match in LINK_RE.finditer(raw):
        parts.append(("text", raw[pos:match.start()]))
        label, url = match.group(1).strip(), match.group(2).strip()
        if url.endswith(".html") and not url.startswith("http"):
            related.append({"label": label, "url": url})
        else:
            sources.append({"label": label, "url": url})
        parts.append(("text", label))
        pos = match.end()
    parts.append(("text", raw[pos:]))

    out: list[str] = []
    for _, chunk in parts:
        if annotator is not None:
            chunk = annotator.annotate(chunk, chapter_id, section_id)
        chunk = esc(chunk)
        chunk = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", chunk)
        chunk = re.sub(r"(?<!\*)\*([^*\n]+?)\*(?!\*)", r"<em>\1</em>", chunk)
        chunk = re.sub(r"`([^`\n]+?)`", r"<code>\1</code>", chunk)
        out.append(chunk)
    html = "".join(out)
    return re.sub(
        r"\x00([a-zA-Z0-9_-]+)\x00([^\x00]*)\x00",
        r'<a class="ent" data-ent="\1">\2</a>',
        html,
    )


def is_meta_paragraph(raw: str) -> bool:
    text = raw.strip()
    return "剧透" in text[:24]


def is_source_note(raw: str) -> bool:
    text = raw.strip()
    return text.startswith("依据") or text.startswith("关键资料")


def split_title(text: str, separator: str) -> tuple[str, str]:
    if separator and separator in text:
        title, subtitle = text.split(separator, 1)
        return title.strip(), subtitle.strip()
    return text.strip(), ""


class ChapterBuilder:
    def __init__(
        self,
        project_dir: Path,
        config: dict,
        spec: dict,
        annotator: Annotator,
        source_dir: Path | None = None,
    ):
        self.project_dir = project_dir
        self.config = config
        self.spec = spec
        self.annotator = annotator
        self.source_dir = source_dir or (
            project_dir / config.get("sourceDir", "sources")
        )
        self.chapter = {
            "id": str(spec["id"]),
            "order": int(spec.get("order", 0)) or None,
            "displayNumber": spec.get("displayNumber"),
            "title": spec.get("title", ""),
            "subtitle": spec.get("subtitle", ""),
            "parts": [],
            "sources": [],
            "related": [],
            "hanzi": 0,
            "chars": 0,
        }
        self._sources: list[dict] = []
        self._related: list[dict] = []

    def new_part(self, title: str, part_id: str, full_title: str = "") -> dict:
        part = {"id": part_id, "title": title, "sections": []}
        if full_title and full_title != title:
            part["fullTitle"] = full_title
        self.chapter["parts"].append(part)
        return part

    def new_section(self, title: str, section_id: str) -> dict:
        if not self.chapter["parts"]:
            self.new_part("开篇", f"p{self.chapter['id']}-0")
        part = self.chapter["parts"][-1]
        section = {"id": section_id, "title": title, "blocks": []}
        part["sections"].append(section)
        return section

    def flush_paragraph(self, buf: list[str], get_section) -> None:
        if not buf:
            return
        raw = "".join(buf).strip()
        buf.clear()
        if not raw or HR_RE.match(raw):
            return
        section = get_section()
        if is_meta_paragraph(raw):
            kind = "note"
        elif is_source_note(raw):
            kind = "source"
        else:
            kind = "p"
        active = None if kind in ("note", "source") else self.annotator
        html = render_inline(
            raw,
            self._sources,
            self._related,
            active,
            self.chapter["id"],
            section["id"],
        )
        section["blocks"].append({"type": kind, "html": html, "text": raw})

    def flush_list(self, items: list[str], get_section) -> None:
        if not items:
            return
        section = get_section()
        rendered = [
            render_inline(
                item,
                self._sources,
                self._related,
                self.annotator,
                self.chapter["id"],
                section["id"],
            )
            for item in items
        ]
        section["blocks"].append({"type": "ul", "items": rendered})
        items.clear()

    def parse_file(self, path: Path, part_label: str = "") -> None:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
        paragraph: list[str] = []
        list_items: list[str] = []
        current_section: dict | None = None
        part_index = len(self.chapter["parts"])
        section_index = 0
        separator = self.spec.get(
            "titleSeparator", self.config.get("titleSeparator", "：")
        )

        def ensure_section() -> dict:
            nonlocal section_index, current_section
            if current_section is None:
                section_index += 1
                current_section = self.new_section(
                    "开篇",
                    f"s{self.chapter['id']}-{part_index}-{section_index}",
                )
            return current_section

        for line in lines:
            stripped = line.rstrip()
            if not stripped:
                self.flush_paragraph(paragraph, ensure_section)
                self.flush_list(list_items, ensure_section)
                continue

            heading = HEADING_RE.match(stripped)
            if heading:
                self.flush_paragraph(paragraph, ensure_section)
                self.flush_list(list_items, ensure_section)
                level = len(heading.group(1))
                text = heading.group(2).strip()

                if level == 1:
                    if not self.chapter["title"]:
                        title, subtitle = split_title(text, separator)
                        self.chapter["title"] = title
                        self.chapter["subtitle"] = subtitle
                    if self.spec.get("mode") == "files":
                        part_index = len(self.chapter["parts"])
                        current_section = None
                        part_title, part_subtitle = split_title(text, separator)
                        part = self.new_part(
                            part_label or part_title,
                            f"p{self.chapter['id']}-{part_index + 1}",
                            full_title=text,
                        )
                        if part_subtitle:
                            part["subtitle"] = part_subtitle
                    continue

                if level == 2:
                    part_index = len(self.chapter["parts"])
                    if self.spec.get("mode") == "files":
                        section_index += 1
                        current_section = self.new_section(
                            text,
                            f"s{self.chapter['id']}-{part_index}-{section_index}",
                        )
                    else:
                        current_section = None
                        self.new_part(
                            text,
                            f"p{self.chapter['id']}-{part_index + 1}",
                        )
                    continue

                section_index += 1
                current_section = self.new_section(
                    text,
                    f"s{self.chapter['id']}-{part_index}-{section_index}",
                )
                continue

            list_match = LIST_RE.match(stripped)
            if list_match:
                self.flush_paragraph(paragraph, ensure_section)
                list_items.append(list_match.group(1).strip())
                continue

            if stripped.startswith(">"):
                self.flush_paragraph(paragraph, ensure_section)
                self.flush_list(list_items, ensure_section)
                raw = stripped.lstrip("> ").strip()
                if raw:
                    section = ensure_section()
                    html = render_inline(
                        raw,
                        self._sources,
                        self._related,
                        self.annotator,
                        self.chapter["id"],
                        section["id"],
                    )
                    section["blocks"].append(
                        {"type": "quote", "html": html, "text": raw}
                    )
                continue

            if HR_RE.match(stripped):
                self.flush_paragraph(paragraph, ensure_section)
                self.flush_list(list_items, ensure_section)
                continue

            if list_items:
                list_items[-1] += stripped.strip()
                continue
            paragraph.append(stripped.strip())

        self.flush_paragraph(paragraph, ensure_section)
        self.flush_list(list_items, ensure_section)

    def build(self) -> dict:
        files = self.spec.get("files") or []
        if not files:
            raise SystemExit(f"chapter {self.spec['id']} has no files")
        labels = ["上篇", "中篇", "第三部", "第四部", "第五部", "第六部", "第七部"]
        for index, filename in enumerate(files):
            label = labels[index] if index < len(labels) else f"第{index + 1}部分"
            self.parse_file(self.source_dir / filename, label)

        def dedupe(items: list[dict]) -> list[dict]:
            seen = set()
            result = []
            for item in items:
                key = (item["label"], item["url"])
                if key in seen:
                    continue
                seen.add(key)
                result.append(item)
            return result

        self.chapter["sources"] = dedupe(self._sources)
        self.chapter["related"] = dedupe(self._related)
        total = 0
        chars_total = 0
        if self.spec.get("mode") != "files":
            total += count_hanzi(self.chapter["title"]) + count_hanzi(
                self.chapter["subtitle"]
            )
            chars_total += count_text_chars(
                self.chapter["title"]
            ) + count_text_chars(self.chapter["subtitle"])
        for part in self.chapter["parts"]:
            part_title = part.get("fullTitle", part["title"])
            total += count_hanzi(part_title)
            chars_total += count_text_chars(part_title)
            for section in part["sections"]:
                total += count_hanzi(section["title"])
                chars_total += count_text_chars(section["title"])
                for block in section["blocks"]:
                    if "html" in block:
                        text = strip_tags(block["html"])
                        total += count_hanzi(text)
                        chars_total += count_text_chars(text)
                    for item in block.get("items", []):
                        text = strip_tags(item)
                        total += count_hanzi(text)
                        chars_total += count_text_chars(text)
        self.chapter["hanzi"] = total
        self.chapter["chars"] = chars_total
        return self.chapter


def load_config(project_dir: Path) -> dict:
    path = project_dir / "project.json"
    if not path.exists():
        raise SystemExit(f"missing project.json: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def discover_chapters(project_dir: Path, config: dict) -> list[dict]:
    specs = config.get("chapters")
    if specs:
        for index, spec in enumerate(specs, 1):
            spec.setdefault("order", index)
            spec.setdefault("id", f"ch{index}")
            spec.setdefault("mode", "parts")
        return specs
    source_dir = project_dir / config.get("sourceDir", "sources")
    files = sorted(
        path
        for path in source_dir.glob("*.md")
        if path.name.lower() != "readme.md"
    )
    return [
        {
            "id": f"ch{index}",
            "order": index,
            "files": [path.name],
            "mode": "parts",
        }
        for index, path in enumerate(files, 1)
    ]


def infer_kind(config: dict) -> str:
    kind = str(config.get("kind") or "").lower()
    if kind in ("import", "retelling", "creation"):
        return kind
    if config.get("sourceDir") == "chapters" and "retoldDir" not in config:
        return "creation"
    if any(spec.get("retoldFiles") for spec in config.get("chapters", [])):
        return "retelling"
    return "import"


DEFAULT_MODE_LABELS = {"original": "原文", "retold": "复述", "creation": "创作"}


def _legacy_dir_for(mode: str, config: dict) -> str:
    kind = infer_kind(config)
    if kind == "creation":
        return str(config.get("sourceDir", "chapters"))
    if mode == "retold":
        return str(config.get("retoldDir", "retold"))
    return str(config.get("sourceDir", "sources"))


def resolve_variants(config: dict) -> list[dict]:
    """Return normalized variant descriptors: id, label, dir, primary.

    Projects may declare arbitrary variants (translation, abridged version,
    annotated version...). When the field is absent we synthesize the legacy
    import / retelling / creation shapes so old projects keep working.
    """
    raw = config.get("variants")
    labels = config.get("modeLabels") or {}
    if isinstance(raw, list):
        result: list[dict] = []
        seen: set[str] = set()
        for item in raw:
            if not isinstance(item, dict):
                continue
            variant_id = str(item.get("id") or "").strip()
            if not variant_id or variant_id in seen:
                continue
            seen.add(variant_id)
            result.append(
                {
                    "id": variant_id,
                    "label": str(
                        item.get("label") or labels.get(variant_id) or variant_id
                    ),
                    "dir": str(item.get("dir") or _legacy_dir_for(variant_id, config)),
                    "primary": bool(item.get("primary")),
                }
            )
        if result:
            primaries = [item for item in result if item["primary"]]
            if len(primaries) > 1:
                for item in primaries[1:]:
                    item["primary"] = False
            if not primaries:
                result[0]["primary"] = True
            return result

    kind = infer_kind(config)
    if kind == "creation":
        return [
            {
                "id": "retold",
                "label": labels.get("retold") or DEFAULT_MODE_LABELS["creation"],
                "dir": str(config.get("sourceDir", "chapters")),
                "primary": True,
            }
        ]
    if kind == "retelling":
        return [
            {
                "id": "original",
                "label": labels.get("original") or DEFAULT_MODE_LABELS["original"],
                "dir": str(config.get("sourceDir", "sources")),
                "primary": True,
            },
            {
                "id": "retold",
                "label": labels.get("retold") or DEFAULT_MODE_LABELS["retold"],
                "dir": str(config.get("retoldDir", "retold")),
                "primary": False,
            },
        ]
    return [
        {
            "id": "original",
            "label": labels.get("original") or DEFAULT_MODE_LABELS["original"],
            "dir": str(config.get("sourceDir", "sources")),
            "primary": True,
        }
    ]


def primary_mode(config: dict) -> str:
    """Return the mode that owns the project's main body text."""
    variants = resolve_variants(config)
    for variant in variants:
        if variant["primary"]:
            return variant["id"]
    declared = config.get("primaryMode")
    if declared and any(variant["id"] == str(declared) for variant in variants):
        return str(declared)
    return variants[0]["id"] if variants else "original"


def mode_labels(config: dict) -> dict[str, str]:
    labels = {variant["id"]: variant["label"] for variant in resolve_variants(config)}
    explicit = config.get("modeLabels")
    if isinstance(explicit, dict):
        for key, value in explicit.items():
            labels.setdefault(str(key), str(value))
    return labels


def variant_files(spec: dict, config: dict, mode: str) -> list[str]:
    files = spec.get("variantFiles")
    if isinstance(files, dict) and mode in files:
        return [str(name) for name in files.get(mode) or []]
    if mode == "retold" and spec.get("retoldFiles"):
        return [str(name) for name in spec.get("retoldFiles") or []]
    if mode == primary_mode(config):
        return [str(name) for name in spec.get("files") or []]
    return []


def spec_modes(spec: dict, config: dict) -> list[str]:
    variants = resolve_variants(config)
    primary = primary_mode(config)
    modes = [primary]
    for variant in variants:
        if variant["id"] == primary:
            continue
        if variant_files(spec, config, variant["id"]):
            modes.append(variant["id"])
    return modes


def resolve_default_mode(config: dict, spec: dict, modes: list[str]) -> str:
    for candidate in (spec.get("defaultMode"), config.get("defaultMode")):
        if candidate in modes:
            return candidate
    if "retold" in modes:
        return "retold"
    return modes[0]


def build_variant(
    project_dir: Path,
    config: dict,
    spec: dict,
    annotator: Annotator,
    mode: str,
) -> tuple[dict, Path, list[str]] | None:
    variant_config = next(
        (variant for variant in resolve_variants(config) if variant["id"] == mode),
        None,
    )
    files = variant_files(spec, config, mode)
    source_dir = project_dir / (
        variant_config["dir"] if variant_config else config.get("sourceDir", "sources")
    )
    if not files:
        return None
    missing = [name for name in files if not (source_dir / name).exists()]
    if missing:
        raise SystemExit(
            f"chapter {spec['id']} [{mode}]: missing source files in "
            f"{source_dir}: {', '.join(missing)}"
        )
    variant_spec = dict(spec)
    variant_spec["files"] = files
    variant_spec["_mode"] = mode
    annotator.start_chapter(str(spec["id"]))
    builder = ChapterBuilder(
        project_dir, config, variant_spec, annotator, source_dir
    )
    variant = builder.build()
    variant["mode"] = mode
    return variant, source_dir, files


def variant_payload(variant: dict) -> dict:
    return {
        "parts": variant["parts"],
        "sources": variant.get("sources", []),
        "related": variant.get("related", []),
        "hanzi": variant.get("hanzi", 0),
        "chars": variant.get("chars", 0),
        "title": variant.get("title", ""),
        "subtitle": variant.get("subtitle", ""),
    }


def chapter_variants(chapter: dict) -> dict[str, dict]:
    """Return {mode: variant-payload} for single- or dual-mode chapters."""
    variants = chapter.get("variants")
    if isinstance(variants, dict) and variants:
        return variants
    mode = str(chapter.get("defaultMode") or (chapter.get("modeNames") or ["original"])[0])
    return {
        mode: {
            "parts": chapter.get("parts", []),
            "sources": chapter.get("sources", []),
            "related": chapter.get("related", []),
            "hanzi": chapter.get("hanzi", 0),
            "chars": chapter.get("chars", 0),
            "title": chapter.get("title", ""),
            "subtitle": chapter.get("subtitle", ""),
        }
    }


def iter_sections(parts: list[dict]):
    for part in parts:
        for section in part.get("sections", []):
            yield part, section


def load_illustrations(project_dir: Path) -> list[dict]:
    path = project_dir / "content" / "illustrations.json"
    if not path.exists():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    images = data.get("images", []) if isinstance(data, dict) else data
    return [image for image in images if isinstance(image, dict)]


def image_block(image: dict) -> dict:
    src = image.get("file") or image.get("src") or ""
    return {
        "type": "image",
        "src": src,
        "alt": image.get("alt", ""),
        "caption": image.get("caption", ""),
        "credit": image.get("credit", ""),
        "license": image.get("license", ""),
        "sourceUrl": image.get("sourceUrl", ""),
        "width": image.get("width"),
        "height": image.get("height"),
        "imageId": image.get("id", ""),
    }


def pick_image_section(parts: list[dict], image: dict) -> dict | None:
    """Pick the best section for an unplaced image: keywords first, then start."""
    keywords = [str(item).strip() for item in image.get("keywords", []) if str(item).strip()]
    sections = [section for _, section in iter_sections(parts)]
    if keywords:
        ranked: list[tuple[int, dict]] = []
        for section in sections:
            text = section.get("title", "") + "".join(
                block.get("text", "") for block in section.get("blocks", [])
            )
            score = sum(text.count(keyword) for keyword in keywords)
            score += sum(5 for keyword in keywords if keyword in section.get("title", ""))
            if score > 0 and section.get("blocks"):
                ranked.append((score, section))
        if ranked:
            return max(ranked, key=lambda item: item[0])[1]
    return next((section for section in sections if section.get("blocks")), None)


def inject_illustrations(
    chapter: dict, images: list[dict], auto_place: bool = True
) -> list[str]:
    """Insert illustration blocks into the requested modes; return warnings."""
    warnings: list[str] = []
    chapter_images = [image for image in images if str(image.get("chapter", "")) == str(chapter["id"])]
    if not chapter_images:
        return warnings
    variants = chapter_variants(chapter)
    mode_names = list(variants.keys())
    for image in chapter_images:
        wanted = str(image.get("mode") or "both")
        targets = mode_names if wanted in ("both", "all", "") else [wanted]
        targets = [mode for mode in targets if mode in variants]
        if not targets:
            warnings.append(
                f"{chapter['id']}: image {image.get('id') or image.get('file')} "
                f"targets unavailable mode {wanted}"
            )
            continue
        section_id = str(image.get("section") or "")
        if not section_id:
            if not auto_place:
                warnings.append(
                    f"{chapter['id']}: image {image.get('id')} has no section "
                    "(autoPlace disabled; run place_illustrations.py)"
                )
                continue
            first = pick_image_section(variants[targets[0]]["parts"], image)
            if first is None:
                warnings.append(
                    f"{chapter['id']}: image {image.get('id')} has no section to attach"
                )
                continue
            section_id = first["id"]
            image["section"] = section_id
            method = "keyword" if image.get("keywords") else "start"
            warnings.append(
                f"{chapter['id']}: image {image.get('id') or image.get('file')} "
                f"auto-placed at {section_id} ({method}; run place_illustrations.py to rebalance)"
            )
        for mode in targets:
            target = next(
                (
                    section
                    for _, section in iter_sections(variants[mode]["parts"])
                    if section["id"] == section_id
                ),
                None,
            )
            if target is None:
                warnings.append(
                    f"{chapter['id']}/{mode}: image {image.get('id')} section {section_id} not found"
                )
                continue
            after = image.get("afterBlock")
            try:
                index = int(after) if after is not None else len(target["blocks"])
            except (TypeError, ValueError):
                index = len(target["blocks"])
            index = max(0, min(index, len(target["blocks"])))
            target["blocks"].insert(index, image_block(image))
    return warnings


def source_body(project_dir: Path, config: dict, spec: dict) -> str:
    source_dir = project_dir / config.get("sourceDir", "sources")
    return source_body_for(source_dir, spec["files"])


def source_body_for(source_dir: Path, files: list[str]) -> str:
    raw = "".join(
        (source_dir / filename).read_text(encoding="utf-8-sig")
        for filename in files
    )
    raw = re.sub(r"^#{1,4}\s+.*$", "", raw, flags=re.MULTILINE)
    raw = LINK_RE.sub(r"\1", raw)
    return normalize_for_fidelity(raw)


def parsed_body(chapter: dict) -> str:
    chunks: list[str] = []
    for part in chapter["parts"]:
        for section in part["sections"]:
            for block in section["blocks"]:
                if "html" in block:
                    chunks.append(strip_tags(block["html"]))
                chunks.extend(strip_tags(item) for item in block.get("items", []))
    return normalize_for_fidelity("".join(chunks))


def section_text(section: dict) -> str:
    chunks = [section["title"]]
    for block in section["blocks"]:
        if "text" in block:
            chunks.append(block["text"])
        chunks.extend(strip_tags(item) for item in block.get("items", []))
    return "".join(chunks)


def validate(
    chapters: list[dict],
    entities: dict,
    meta: dict,
    project_dir: Path | None = None,
    images: list[dict] | None = None,
    manual_links: dict | None = None,
    timeline: dict | None = None,
) -> list[str]:
    errors: list[str] = []
    entity_ids = {entity["id"] for entity in entities.get("entities", [])}
    section_ids: set[tuple[str, str]] = set()
    section_map: dict[tuple[str, str], list[dict]] = {}
    for chapter in chapters:
        for mode, variant in chapter_variants(chapter).items():
            for _, section in iter_sections(variant.get("parts", [])):
                key = (str(chapter["id"]), section["id"])
                section_ids.add(key)
                section_map.setdefault(key, []).append(section)

    for relation in entities.get("relations", []):
        if relation["from"] not in entity_ids:
            errors.append(f"relation from unknown entity: {relation['from']}")
        if relation["to"] not in entity_ids:
            errors.append(f"relation to unknown entity: {relation['to']}")

    for entity in entities.get("entities", []):
        for evidence in entity.get("evidence", []):
            chapter_id = str(evidence.get("chapter", ""))
            quote = str(evidence.get("quote", ""))
            matches = resolve_evidence_section(evidence, section_map)
            if not evidence.get("section"):
                if not matches:
                    errors.append(
                        f"{entity['id']}: evidence quote not found in "
                        f"{chapter_id}: {quote[:24]}"
                    )
                elif len(matches) > 1:
                    errors.append(
                        f"{entity['id']}: evidence quote is ambiguous in "
                        f"{chapter_id}: {', '.join(matches)}"
                    )
                continue
            key = (chapter_id, str(evidence["section"]))
            if key not in section_ids:
                errors.append(f"{entity['id']}: evidence section missing {key}")
            elif not any(
                quote in section_text(section) for section in section_map[key]
            ):
                errors.append(
                    f"{entity['id']}: quote not found in {key}: {quote[:24]}"
                )

    if manual_links:
        for link in manual_links.get("links", []):
            entity_id = str(link.get("entity", ""))
            chapter_id = str(link.get("chapter", ""))
            quote = str(link.get("quote", ""))
            target = str(link.get("target", ""))
            if entity_id not in entity_ids:
                errors.append(f"manual link: unknown entity {entity_id}")
            if not quote or not target:
                errors.append("manual link: quote and target are required")
                continue
            if target not in quote:
                errors.append(
                    f"manual link {entity_id}: target {target} not inside quote"
                )
                continue
            if link.get("section"):
                key = (chapter_id, str(link["section"]))
                if key not in section_ids:
                    errors.append(
                        f"manual link {entity_id}: section missing {key}"
                    )
                elif not any(
                    quote in section_text(section) for section in section_map[key]
                ):
                    errors.append(
                        f"manual link {entity_id}: quote not found in {key}"
                    )
            else:
                matches = locate_sections(section_map, chapter_id, quote)
                if not matches:
                    errors.append(
                        f"manual link {entity_id}: quote not found in {chapter_id}"
                    )
                elif len(matches) > 1:
                    errors.append(
                        f"manual link {entity_id}: quote is ambiguous in "
                        f"{chapter_id}: {', '.join(matches)}"
                    )

    if timeline is not None:
        errors.extend(validate_timeline(timeline, entities, chapters, section_map))

    for chapter_id, info in meta.items():
        cid = str(chapter_id)
        if cid not in {str(chapter["id"]) for chapter in chapters}:
            errors.append(f"meta for unknown chapter {chapter_id}")
            continue
        for entity_id in info.get("cast", []) + info.get("newTerms", []):
            if entity_id not in entity_ids:
                errors.append(f"meta chapter {chapter_id}: unknown entity {entity_id}")

    annotated_ids: set[str] = set()
    for chapter in chapters:
        for mode, variant in chapter_variants(chapter).items():
            annotated: set[str] = set()
            for _, section in iter_sections(variant.get("parts", [])):
                for block in section["blocks"]:
                    annotated.update(
                        re.findall(r'data-ent="([a-zA-Z0-9_-]+)"', block.get("html", ""))
                    )
                    for item in block.get("items", []):
                        annotated.update(
                            re.findall(r'data-ent="([a-zA-Z0-9_-]+)"', item)
                        )
            print(f"  {chapter['id']}[{mode}]: {len(annotated)} entities annotated")
            for entity_id in annotated:
                if entity_id not in entity_ids:
                    errors.append(
                        f"chapter {chapter['id']}[{mode}]: unknown annotated entity {entity_id}"
                    )
            annotated_ids.update(annotated)

    if images and project_dir is not None:
        errors.extend(validate_illustrations(project_dir, chapters, images))

    for entity_id in entity_ids:
        if entity_id not in annotated_ids:
            # Not an error: major entities may only appear in the atlas.
            pass
    return errors


def validate_illustrations(
    project_dir: Path, chapters: list[dict], images: list[dict]
) -> list[str]:
    errors: list[str] = []
    chapter_map = {str(chapter["id"]): chapter for chapter in chapters}
    seen_ids: set[str] = set()
    for image in images:
        image_id = str(image.get("id") or image.get("file") or image.get("src") or "")
        if not image_id:
            errors.append("illustration without id/file")
            continue
        if image_id in seen_ids:
            errors.append(f"duplicate illustration id: {image_id}")
        seen_ids.add(image_id)
        src = str(image.get("file") or image.get("src") or "")
        if not src:
            errors.append(f"illustration {image_id}: missing file")
        elif src.startswith(("http://", "https://")):
            errors.append(
                f"illustration {image_id}: remote src not allowed; download it locally"
            )
        elif not (project_dir / src).exists():
            errors.append(f"illustration {image_id}: file not found {src}")
        chapter = chapter_map.get(str(image.get("chapter", "")))
        if chapter is None:
            errors.append(f"illustration {image_id}: unknown chapter {image.get('chapter')}")
            continue
        modes = list(chapter_variants(chapter).keys())
        wanted = str(image.get("mode") or "both")
        targets = modes if wanted in ("both", "all", "") else [wanted]
        if not any(mode in modes for mode in targets):
            errors.append(
                f"illustration {image_id}: mode {wanted} unavailable in {chapter['id']}"
            )
        section_id = str(image.get("section") or "")
        if not section_id:
            errors.append(f"illustration {image_id}: no section assigned")
        elif not any(
            section["id"] == section_id
            for mode in targets
            if mode in chapter_variants(chapter)
            for _, section in iter_sections(chapter_variants(chapter)[mode]["parts"])
        ):
            errors.append(
                f"illustration {image_id}: section {section_id} not found in {chapter['id']}"
            )
        if "alt" not in image:
            errors.append(f"illustration {image_id}: missing alt text")
        if image.get("sourceUrl") and not image.get("credit"):
            errors.append(f"illustration {image_id}: web image needs credit")
        if image.get("sourceUrl") and not image.get("license"):
            errors.append(f"illustration {image_id}: web image needs license")
    return errors


def write_js(path: Path, variable: str, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    path.write_text(
        "/* generated by story-forge; do not edit */\n"
        f"window.{variable} = {text};\n",
        encoding="utf-8",
    )


def load_json_file(path: Path, fallback: object) -> object:
    if not path.exists():
        return fallback
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        raise SystemExit(f"invalid JSON in {path}: {error}") from error


def normalize_volumes(
    config: dict, specs: list[dict]
) -> tuple[list[dict], dict[str, str], list[str]]:
    """Normalize volume declarations and map chapter id -> volume id."""
    raw = config.get("volumes")
    if not isinstance(raw, list) or not raw:
        return [], {}, []
    chapter_ids = [str(spec.get("id")) for spec in specs]
    order_by_id = {
        str(spec.get("id")): int(spec.get("order") or 0) for spec in specs
    }
    warnings: list[str] = []
    volumes: list[dict] = []
    seen_ids: set[str] = set()
    for index, item in enumerate(raw):
        if not isinstance(item, dict):
            continue
        volume_id = str(item.get("id") or f"vol{index + 1}")
        if volume_id in seen_ids:
            warnings.append(f"duplicate volume id: {volume_id}")
            continue
        seen_ids.add(volume_id)
        declared = [str(chapter) for chapter in item.get("chapters") or []]
        members = [chapter for chapter in declared if chapter in chapter_ids]
        unknown = [chapter for chapter in declared if chapter not in chapter_ids]
        if unknown:
            warnings.append(
                f"volume {volume_id}: unknown chapters {', '.join(unknown)}"
            )
        start, end = item.get("from"), item.get("to")
        if not members and (start is not None or end is not None):
            try:
                low = int(start) if start is not None else None
                high = int(end) if end is not None else None
                members = [
                    chapter
                    for chapter in chapter_ids
                    if (low is None or order_by_id[chapter] >= low)
                    and (high is None or order_by_id[chapter] <= high)
                ]
            except (TypeError, ValueError):
                warnings.append(f"volume {volume_id}: invalid from/to")
        members.sort(key=lambda chapter: order_by_id.get(chapter, 0))
        volumes.append(
            {
                "id": volume_id,
                "title": str(item.get("title") or volume_id),
                "subtitle": str(item.get("subtitle") or ""),
                "order": int(item.get("order") or index + 1),
                "chapters": members,
            }
        )
    volumes.sort(key=lambda item: item["order"])

    chapter_to_volume: dict[str, str] = {}
    for volume in volumes:
        for chapter_id in volume["chapters"]:
            previous = chapter_to_volume.get(chapter_id)
            if previous and previous != volume["id"]:
                warnings.append(
                    f"chapter {chapter_id}: in multiple volumes "
                    f"({previous}, {volume['id']})"
                )
            chapter_to_volume.setdefault(chapter_id, volume["id"])

    by_id = {volume["id"]: volume for volume in volumes}
    for spec in specs:
        chapter_id = str(spec.get("id"))
        declared = spec.get("volume")
        if not declared:
            continue
        declared = str(declared)
        if declared not in by_id:
            warnings.append(f"chapter {chapter_id}: unknown volume {declared}")
            continue
        previous = chapter_to_volume.get(chapter_id)
        if previous and previous != declared:
            warnings.append(
                f"chapter {chapter_id}: chapter.volume {declared} conflicts with "
                f"volume membership {previous}"
            )
        chapter_to_volume[chapter_id] = declared
        if chapter_id not in by_id[declared]["chapters"]:
            by_id[declared]["chapters"].append(chapter_id)
            by_id[declared]["chapters"].sort(
                key=lambda item: order_by_id.get(item, 0)
            )
    return volumes, chapter_to_volume, warnings


def locate_sections(
    section_map: dict[tuple[str, str], list[dict]],
    chapter_id: str,
    quote: str,
) -> list[str]:
    """Return every section id in a chapter whose text contains the quote."""
    matches: set[str] = set()
    for (candidate_chapter, section_id), sections in section_map.items():
        if str(candidate_chapter) != str(chapter_id):
            continue
        if any(quote in section_text(section) for section in sections):
            matches.add(section_id)
    return sorted(matches)


def resolve_evidence_section(
    evidence: dict, section_map: dict[tuple[str, str], list[dict]]
) -> list[str]:
    """Fill evidence.section when omitted; return the matches (0, 1 or many)."""
    if evidence.get("section"):
        return [str(evidence["section"])]
    chapter_id = str(evidence.get("chapter", ""))
    quote = str(evidence.get("quote", ""))
    if not chapter_id or not quote:
        return []
    matches = locate_sections(section_map, chapter_id, quote)
    if len(matches) == 1:
        evidence["section"] = matches[0]
    return matches


def build_mentions(chapters: list[dict], entities: dict) -> dict[str, list[dict]]:
    """Index every section that mentions an entity (length >= 2 names only)."""
    names_by_entity: dict[str, list[str]] = {}
    for entity in entities.get("entities", []):
        names: list[str] = []
        candidates = [entity.get("name", "")] + list(entity.get("aliases") or [])
        for alias in candidates:
            alias = str(alias).strip()
            if len(alias) >= 2 and alias not in names:
                names.append(alias)
        if names:
            names_by_entity[str(entity["id"])] = sorted(
                names, key=len, reverse=True
            )
    if not names_by_entity:
        return {}

    mention_map: dict[str, dict[tuple[str, str], dict]] = {}
    for chapter in chapters:
        modes = chapter.get("modeNames") or []
        mode = chapter.get("defaultMode") or (modes[0] if modes else "")
        variants = chapter.get("variants")
        variant = (
            variants.get(mode)
            if isinstance(variants, dict) and mode in variants
            else chapter
        )
        for part in variant.get("parts") or []:
            for section in part.get("sections") or []:
                text = section_text(section)
                if not text:
                    continue
                for entity_id, names in names_by_entity.items():
                    pattern = re.compile("|".join(re.escape(name) for name in names))
                    count = sum(1 for _ in pattern.finditer(text))
                    if not count:
                        continue
                    key = (str(chapter["id"]), section["id"])
                    bucket = mention_map.setdefault(entity_id, {})
                    entry = bucket.get(key)
                    if entry:
                        entry["count"] += count
                    else:
                        bucket[key] = {
                            "chapter": str(chapter["id"]),
                            "section": section["id"],
                            "count": count,
                            "chapterOrder": int(chapter.get("order") or 0),
                        }
    return {
        entity_id: sorted(
            entries.values(), key=lambda item: (item["chapterOrder"], item["section"])
        )
        for entity_id, entries in mention_map.items()
    }


def validate_timeline(
    timeline: dict,
    entities: dict,
    chapters: list[dict],
    section_map: dict[tuple[str, str], list[dict]],
) -> list[str]:
    errors: list[str] = []
    events = timeline.get("events") if isinstance(timeline, dict) else []
    if events is None:
        return errors
    if not isinstance(events, list):
        return ["timeline: events must be a list"]
    entity_ids = {str(entity["id"]) for entity in entities.get("entities", [])}
    chapter_orders = {
        str(chapter["id"]): int(chapter.get("order") or 0) for chapter in chapters
    }
    event_ids: set[str] = set()
    for index, event in enumerate(events):
        if not isinstance(event, dict):
            errors.append(f"timeline event #{index + 1}: not an object")
            continue
        event_id = str(event.get("id") or "")
        if not event_id:
            errors.append(f"timeline event #{index + 1}: missing id")
        elif event_id in event_ids:
            errors.append(f"timeline: duplicate event id {event_id}")
        event_ids.add(event_id)
    for event in events:
        if not isinstance(event, dict):
            continue
        event_id = str(event.get("id") or index_label(events, event))
        for entity_id in event.get("entities") or []:
            if str(entity_id) not in entity_ids:
                errors.append(
                    f"timeline {event_id}: unknown entity {entity_id}"
                )
        chapter_id = str(event.get("chapter") or "")
        if chapter_id and chapter_id not in chapter_orders:
            errors.append(f"timeline {event_id}: unknown chapter {chapter_id}")
        for key in ("causes", "consequences"):
            for other in event.get(key) or []:
                if str(other) not in event_ids:
                    errors.append(
                        f"timeline {event_id}: unknown {key} reference {other}"
                    )
        for evidence in event.get("evidence") or []:
            matches = resolve_evidence_section(evidence, section_map)
            chapter = str(evidence.get("chapter") or chapter_id)
            if not evidence.get("section"):
                if not matches:
                    errors.append(
                        f"timeline {event_id}: evidence quote not found in {chapter}"
                    )
                elif len(matches) > 1:
                    errors.append(
                        f"timeline {event_id}: evidence quote is ambiguous in "
                        f"{chapter}: {', '.join(matches)}"
                    )
            else:
                key = (chapter, str(evidence.get("section")))
                if key not in section_map:
                    errors.append(
                        f"timeline {event_id}: evidence section missing {key}"
                    )
                elif not any(
                    str(evidence.get("quote", "")) in section_text(section)
                    for section in section_map[key]
                ):
                    errors.append(
                        f"timeline {event_id}: evidence quote not found in {key}"
                    )
        spoiler = event.get("spoilerFrom")
        if spoiler is not None and chapter_id in chapter_orders:
            try:
                if int(spoiler) > chapter_orders[chapter_id]:
                    errors.append(
                        f"timeline {event_id}: spoilerFrom {spoiler} is later than "
                        f"chapter {chapter_id}"
                    )
            except (TypeError, ValueError):
                errors.append(f"timeline {event_id}: spoilerFrom must be a number")
    errors.extend(validate_event_cycles(events))
    return errors


def index_label(events: list, event: dict) -> str:
    return f"#{events.index(event) + 1}"


def validate_event_cycles(events: list) -> list[str]:
    """Detect cycles in the directed cause -> event -> consequence graph."""
    graph: dict[str, list[str]] = {
        str(event["id"]): []
        for event in events
        if isinstance(event, dict) and event.get("id")
    }
    for event in events:
        if not isinstance(event, dict) or not event.get("id"):
            continue
        event_id = str(event["id"])
        for cause in event.get("causes") or []:
            graph.setdefault(str(cause), []).append(event_id)
        for consequence in event.get("consequences") or []:
            graph[event_id].append(str(consequence))
    visiting: set[str] = set()
    visited: set[str] = set()
    errors: list[str] = []

    def visit(node: str, path: list[str]) -> None:
        if node in visited:
            return
        if node in visiting:
            errors.append(
                f"timeline: cycle detected ({' -> '.join(path + [node])})"
            )
            return
        visiting.add(node)
        for neighbour in graph.get(node, []):
            if neighbour not in graph:
                continue
            visit(neighbour, path + [node])
        visiting.discard(node)
        visited.add(node)

    for node in graph:
        visit(node, [])
    return errors



def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    if len(sys.argv) < 2:
        raise SystemExit("usage: parse_chapters.py <project-dir> [--check]")
    project_dir = Path(sys.argv[1]).resolve()
    check_only = "--check" in sys.argv[2:]

    config = load_config(project_dir)
    content_dir = project_dir / "content"
    annotator = Annotator(content_dir)
    specs = discover_chapters(project_dir, config)
    if not specs:
        kind = infer_kind(config)
        policy = str(config.get("sourcePolicy") or "").lower()
        required = policy == "required" or (
            not policy and kind in ("import", "retelling")
        )
        if required:
            print(
                "error: no source chapters found. Run:\n"
                "  python scripts/story.py source-check <project> --json\n"
                "then search for the original text, import it with\n"
                "  python scripts/story.py ingest <project> <source>\n"
                "or add Markdown files to the source directory.",
                file=sys.stderr,
            )
            sys.exit(1)
        print(
            "warning: no chapters found; building an empty project shell",
            file=sys.stderr,
        )

    chapters: list[dict] = []
    fidelity_ok = True
    fidelity_by_mode: dict[str, bool] = {}
    warnings: list[str] = []
    images = load_illustrations(project_dir)
    volumes, chapter_to_volume, volume_warnings = normalize_volumes(config, specs)
    warnings.extend(volume_warnings)
    timeline = load_json_file(content_dir / "timeline.json", {"events": []})
    manual_links = load_json_file(content_dir / "manual_links.json", {"links": []})
    for spec in specs:
        modes = spec_modes(spec, config)
        variants: dict[str, dict] = {}
        sources_by_mode: dict[str, tuple[Path, list[str]]] = {}
        for mode in modes:
            built = build_variant(project_dir, config, spec, annotator, mode)
            if built is None:
                if mode != primary_mode(config):
                    warnings.append(
                        f"{spec['id']}: {mode} files missing; mode skipped"
                    )
                    continue
                raise SystemExit(f"chapter {spec['id']}: no files")
            variant, source_dir, files = built
            variants[mode] = variant
            sources_by_mode[mode] = (source_dir, files)
        if not variants:
            raise SystemExit(f"chapter {spec['id']}: no readable variant")
        actual_modes = list(variants)
        default_mode = resolve_default_mode(config, spec, actual_modes)
        chapter = (
            variants[default_mode]
            if len(actual_modes) == 1
            else dict(variants[default_mode])
        )
        chapter["modeNames"] = actual_modes
        chapter["defaultMode"] = default_mode
        chapter["hanziByMode"] = {mode: variant["hanzi"] for mode, variant in variants.items()}
        chapter["charsByMode"] = {
            mode: variant.get("chars", 0) for mode, variant in variants.items()
        }
        chapter["title"] = variants[default_mode].get("title") or spec.get("title", "")
        chapter["subtitle"] = variants[default_mode].get("subtitle") or spec.get("subtitle", "")
        if len(actual_modes) > 1:
            chapter["variants"] = {
                mode: variant_payload(variant) for mode, variant in variants.items()
            }
            for key in ("parts", "sources", "related"):
                chapter.pop(key, None)
            chapter["hanzi"] = variants[default_mode]["hanzi"]
            chapter["chars"] = variants[default_mode].get("chars", 0)
        else:
            chapter["hanzi"] = variants[actual_modes[0]]["hanzi"]
            chapter["chars"] = variants[actual_modes[0]].get("chars", 0)
        volume_id = chapter_to_volume.get(str(chapter["id"]))
        if volume_id:
            chapter["volume"] = volume_id
        warnings.extend(
            inject_illustrations(
                chapter,
                images,
                auto_place=bool(
                    (config.get("illustrations") or {}).get("autoPlace", True)
                ),
            )
        )
        chapters.append(chapter)

        for mode, variant in variants.items():
            source_dir, files = sources_by_mode[mode]
            source = source_body_for(source_dir, files)
            parsed = parsed_body(variant)
            ok = parsed == source
            fidelity_ok = fidelity_ok and ok
            fidelity_by_mode[f"{chapter['id']}:{mode}"] = ok
            print(
                f"{chapter['id']}[{mode}]: source={len(source)} parsed={len(parsed)} "
                f"diff={len(parsed) - len(source):+} fidelity={'OK' if ok else 'FAIL'}"
            )

    entities = json.loads(
        (content_dir / "entities.json").read_text(encoding="utf-8")
    ) if (content_dir / "entities.json").exists() else {"entities": [], "relations": []}
    meta = json.loads(
        (content_dir / "chapter_meta.json").read_text(encoding="utf-8")
    ) if (content_dir / "chapter_meta.json").exists() else {}
    recap = json.loads(
        (content_dir / "recap.json").read_text(encoding="utf-8")
    ) if (content_dir / "recap.json").exists() else {"lede": "", "eras": [], "whereYouAre": {}}
    worldview = json.loads(
        (content_dir / "worldview.json").read_text(encoding="utf-8")
    ) if (content_dir / "worldview.json").exists() else {"cards": []}

    print("\nvalidation:")
    errors = validate(
        chapters,
        entities,
        meta,
        project_dir,
        images,
        manual_links=manual_links if isinstance(manual_links, dict) else None,
        timeline=timeline if isinstance(timeline, dict) else None,
    )
    if errors:
        for error in errors[:40]:
            print(f"  - {error}")
        print(f"  {len(errors)} problem(s)")
    else:
        print("  all checks passed")
    if warnings:
        print("\nwarnings:")
        for warning in warnings[:20]:
            print(f"  - {warning}")
        if len(warnings) > 20:
            print(f"  ... {len(warnings) - 20} more")

    if check_only:
        print("\nRESULT:", "PASS" if fidelity_ok and not errors else "FAIL")
        sys.exit(0 if fidelity_ok and not errors else 1)

    ordered = sorted(chapters, key=lambda chapter: int(chapter["order"] or 0))
    ready = config.get("ready")
    if ready:
        ready_ids = [str(item) for item in ready]
    else:
        ready_ids = [str(chapter["id"]) for chapter in ordered if str(chapter["id"]) in meta]
        if not ready_ids:
            ready_ids = [str(chapter["id"]) for chapter in ordered]
    first_ready = next(
        (chapter for chapter in ordered if str(chapter["id"]) in ready_ids),
        ordered[0] if ordered else None,
    )
    orders = [int(chapter["order"]) for chapter in ordered if chapter.get("order")]
    chapter_range = (
        f"{min(orders)}—{max(orders)}" if orders else ""
    )
    story_config = {
        "slug": config.get("slug", project_dir.name),
        "title": config.get("title", ""),
        "subtitle": config.get("subtitle", ""),
        "description": config.get("description", ""),
        "lede": config.get("lede", ""),
        "eyebrow": config.get("eyebrow", ""),
        "brand": config.get("brand", {"mark": "STORY", "name": "ARCHIVE"}),
        "footerNote": config.get("footerNote", ""),
        "footerDetail": config.get("footerDetail", ""),
        "kind": infer_kind(config),
        "modes": [variant["id"] for variant in resolve_variants(config)],
        "variants": resolve_variants(config),
        "primaryMode": primary_mode(config),
        "modeLabels": mode_labels(config),
        "defaultMode": config.get("defaultMode")
        or (
            "retold"
            if any(
                variant["id"] == "retold" for variant in resolve_variants(config)
            )
            else primary_mode(config)
        ),
        "volumes": volumes,
        "illustrations": config.get("illustrations", {}),
        "accentPalette": config.get(
            "accentPalette",
            ["#e23a4e", "#7fd6d6", "#c9a227", "#d98c5f", "#6fbf8f", "#7a9fe2"],
        ),
        "firstChapterId": str(first_ready["id"]) if first_ready else None,
        "ready": ready_ids,
        "chapterRange": chapter_range,
    }

    data_dir = project_dir / config.get("dataDir", "site/data")
    write_js(data_dir / "config.js", "STORY_CONFIG", story_config)
    write_js(data_dir / "chapters.js", "STORY_CHAPTERS", chapters)
    write_js(data_dir / "entities.js", "STORY_ENTITIES", entities)
    write_js(data_dir / "meta.js", "STORY_META", meta)
    write_js(data_dir / "recap.js", "STORY_RECAP", recap)
    write_js(data_dir / "worldview.js", "STORY_WORLDVIEW", worldview)
    write_js(
        data_dir / "timeline.js",
        "STORY_TIMELINE",
        timeline if isinstance(timeline, dict) else {"events": []},
    )
    write_js(
        data_dir / "mentions.js",
        "STORY_MENTIONS",
        build_mentions(chapters, entities),
    )

    build_dir = project_dir / "build"
    build_dir.mkdir(parents=True, exist_ok=True)
    (build_dir / "chapters.json").write_text(
        json.dumps(chapters, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (build_dir / "parse_report.json").write_text(
        json.dumps(
            {
                "chapters": len(chapters),
                "fidelity": fidelity_ok,
                "fidelityByMode": fidelity_by_mode,
                "errors": errors,
                "warnings": warnings,
                "hanzi": sum(chapter["hanzi"] for chapter in chapters),
                "hanziByMode": {
                    mode: sum(
                        chapter.get("hanziByMode", {}).get(mode, 0)
                        for chapter in chapters
                        if mode in (chapter.get("modeNames") or [])
                    )
                    for mode in sorted(
                        {
                            mode
                            for chapter in chapters
                            for mode in (chapter.get("modeNames") or [])
                        }
                    )
                },
                "chars": sum(chapter.get("chars", 0) for chapter in chapters),
                "charsByMode": {
                    mode: sum(
                        chapter.get("charsByMode", {}).get(mode, 0)
                        for chapter in chapters
                        if mode in (chapter.get("modeNames") or [])
                    )
                    for mode in sorted(
                        {
                            mode
                            for chapter in chapters
                            for mode in (chapter.get("modeNames") or [])
                        }
                    )
                },
                "illustrations": len(images),
                "volumes": len(volumes),
                "timelineEvents": len(timeline.get("events", []))
                if isinstance(timeline, dict)
                else 0,
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("\nRESULT:", "PASS" if fidelity_ok and not errors else "FAIL")
    print(f"data: {data_dir}")
    if not fidelity_ok or errors:
        sys.exit(1)


if __name__ == "__main__":
    main()
