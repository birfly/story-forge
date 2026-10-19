#!/usr/bin/env python3
"""Story Forge — content audit.

Validates authored content against parsed chapters: evidence, spoiler leaks,
relations, chapter metadata, mode alignment, illustrations, volumes/timeline,
unlinked high-frequency names, and annotation coverage.

Usage:
    python audit_content.py <project-dir> [--json] [--strict]

Outputs:
    build/audit_report.json

Exit codes:
    0  no errors (and no warnings under --strict)
    1  errors, or warnings when --strict is given
    2  usage error
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Iterator

HANZI_RE = re.compile(r"[一-鿿]")
TAG_RE = re.compile(r"<[^>]+>")
ENT_RE = re.compile(r"""data-ent=["']([^"']+)["']""")
NAME_RUN_RE = re.compile(r"[一-鿿]+")

MIN_EVIDENCE_HANZI = 6
MAX_IMAGE_BYTES = 2 * 1024 * 1024
CANDIDATE_MIN_COUNT = 6
CANDIDATE_MIN_CHAPTERS = 2
WORD_MIN = 2
WORD_MAX = 4

# Conservative filters for the unlinked-name heuristic.
STOP_CHARS = set(
    "的了着过是在有和与就都也又很把被从对向为以及而这那其之但并却只"
    "因所以可以还再才让使给于到地得吗呢吧啊呀哦嗯我你他她它们这那谁"
    "什怎没有不个些样时候现已经因为如果虽然然后就是还是只是而且或者"
    "于是出来起来进去看着知道"
)
STOP_WORDS = {
    "我们",
    "你们",
    "他们",
    "她们",
    "它们",
    "自己",
    "什么",
    "怎么",
    "这个",
    "那个",
    "这里",
    "那里",
    "时候",
    "现在",
    "已经",
    "可以",
    "因为",
    "所以",
    "但是",
    "如果",
    "虽然",
    "然后",
    "就是",
    "不是",
    "没有",
    "一个",
    "一些",
    "这样",
    "那样",
    "知道",
    "起来",
    "出来",
    "进去",
    "只是",
    "而且",
    "或者",
    "以及",
}


# ---------------------------------------------------------------- text helpers


def count_hanzi(text: str) -> int:
    return len(HANZI_RE.findall(text))


def strip_tags(html: str) -> str:
    return TAG_RE.sub("", html)


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def iter_sections(parts: Any) -> Iterator[dict[str, Any]]:
    if not isinstance(parts, list):
        return
    for part in parts:
        if not isinstance(part, dict):
            continue
        sections = part.get("sections", [])
        if not isinstance(sections, list):
            continue
        for section in sections:
            if isinstance(section, dict):
                yield section


def section_text(section: dict[str, Any]) -> str:
    chunks = [str(section.get("title", ""))]
    blocks = section.get("blocks", [])
    if not isinstance(blocks, list):
        return "".join(chunks)
    for block in blocks:
        if not isinstance(block, dict):
            continue
        text = block.get("text")
        if text is None:
            text = strip_tags(str(block.get("html", "")))
        chunks.append(str(text))
        items = block.get("items", [])
        if isinstance(items, list):
            chunks.extend(strip_tags(str(item)) for item in items)
    return "".join(chunks)


def variant_paragraphs(variant: dict[str, Any]) -> list[str]:
    paragraphs: list[str] = []
    for section in iter_sections(variant.get("parts", [])):
        blocks = section.get("blocks", [])
        if not isinstance(blocks, list):
            continue
        for block in blocks:
            if not isinstance(block, dict):
                continue
            if block.get("type") not in (None, "p"):
                continue
            text = block.get("text")
            if text is None:
                text = strip_tags(str(block.get("html", "")))
            text = str(text).strip()
            if text:
                paragraphs.append(text)
    return paragraphs


def chapter_variants(chapter: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return {mode: payload}; supports single-mode and generalized variants."""
    variants = chapter.get("variants")
    if isinstance(variants, dict) and variants:
        return {
            str(mode): variant
            for mode, variant in variants.items()
            if isinstance(variant, dict)
        }
    modes = chapter.get("modeNames")
    if not isinstance(modes, list) or not modes:
        modes = [chapter.get("defaultMode") or "original"]
    mode = str(chapter.get("defaultMode") or modes[0])
    return {
        mode: {
            "parts": chapter.get("parts", []),
            "hanzi": chapter.get("hanzi", 0),
        }
    }


def all_sections(chapter: dict[str, Any]) -> list[dict[str, Any]]:
    sections: list[dict[str, Any]] = []
    for variant in chapter_variants(chapter).values():
        sections.extend(iter_sections(variant.get("parts", [])))
    return sections


def all_section_ids(chapter: dict[str, Any]) -> set[str]:
    return {str(section.get("id", "")) for section in all_sections(chapter)}


def ordered_section_ids(variant: dict[str, Any]) -> list[str]:
    return [
        str(section.get("id", ""))
        for section in iter_sections(variant.get("parts", []))
    ]


def variant_hanzi(chapter: dict[str, Any], mode: str, variant: dict[str, Any]) -> float:
    by_mode = chapter.get("hanziByMode")
    if isinstance(by_mode, dict) and isinstance(by_mode.get(mode), (int, float)):
        return float(by_mode[mode])
    return float(
        sum(
            count_hanzi(section_text(section))
            for section in iter_sections(variant.get("parts", []))
        )
    )


def entity_names(entity: dict[str, Any]) -> list[str]:
    names: list[str] = []
    name = entity.get("name")
    if isinstance(name, str) and name:
        names.append(name)
    aliases = entity.get("aliases")
    if isinstance(aliases, list):
        for alias in aliases:
            if isinstance(alias, str) and alias and alias not in names:
                names.append(alias)
    return names


def primary_mode(project: dict[str, Any], chapter: dict[str, Any]) -> str:
    variants = chapter_variants(chapter)
    configured = project.get("variants")
    if isinstance(configured, list):
        for variant in configured:
            if isinstance(variant, dict) and variant.get("primary"):
                mode = str(variant.get("id") or "")
                if mode in variants:
                    return mode
    declared = project.get("primaryMode")
    if isinstance(declared, str) and declared in variants:
        return declared
    modes = project.get("modes")
    if isinstance(modes, list):
        for mode in modes:
            if str(mode) in variants:
                return str(mode)
    if "original" in variants:
        return "original"
    if "retold" in variants:
        return "retold"
    return next(iter(variants), "")


# --------------------------------------------------------------- file loading


def load_json(path: Path, errors: list[str], label: str) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{label} 读取失败：{exc}")
        return None


def load_chapters(
    project: Path, errors: list[str]
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    path = project / "build" / "chapters.json"
    if not path.exists():
        errors.append("缺少 build/chapters.json：请先运行 parse")
        return [], {}
    data = load_json(path, errors, "build/chapters.json")
    if isinstance(data, dict):
        config = data.get("config")
        chapters = data.get("chapters")
        if not isinstance(chapters, list):
            errors.append("build/chapters.json 缺少 chapters 数组")
            return [], config if isinstance(config, dict) else {}
        return (
            [chapter for chapter in chapters if isinstance(chapter, dict)],
            config if isinstance(config, dict) else {},
        )
    if isinstance(data, list):
        return [chapter for chapter in data if isinstance(chapter, dict)], {}
    errors.append("build/chapters.json 结构无效：应为章节数组")
    return [], {}


# ---------------------------------------------------------------- check: evidence


def quote_length(quote: str) -> int:
    hanzi = count_hanzi(quote)
    return hanzi if hanzi else len(quote.strip())


def validate_evidence(
    owner: str,
    evidence_list: Any,
    chapter_index: dict[str, dict[str, Any]],
    errors: list[str],
    warnings: list[str],
    info: list[str],
    require_evidence: bool = True,
) -> int:
    evidence = evidence_list if isinstance(evidence_list, list) else []
    if require_evidence and not evidence:
        warnings.append(f"{owner}：没有任何证据")
        return 0

    seen_quotes: set[str] = set()
    for entry in evidence:
        if not isinstance(entry, dict):
            errors.append(f"{owner}：证据条目不是对象")
            continue
        quote = str(entry.get("quote") or "").strip()
        if not quote:
            warnings.append(f"{owner}：证据缺少引文")
            continue
        if quote_length(quote) < MIN_EVIDENCE_HANZI:
            warnings.append(f"{owner}：引文不足 {MIN_EVIDENCE_HANZI} 个汉字：{quote[:24]}")
        if quote in seen_quotes:
            warnings.append(f"{owner}：重复引文：{quote[:24]}")
        seen_quotes.add(quote)

        chapter_id = str(entry.get("chapter") or "")
        chapter = chapter_index.get(chapter_id)
        if chapter is None:
            errors.append(f"{owner}：证据引用未知章节 {chapter_id or '空'}")
            continue
        sections = all_sections(chapter)
        section_id = str(entry.get("section") or "")
        if section_id:
            matches = [
                section
                for section in sections
                if str(section.get("id", "")) == section_id
            ]
            if not matches:
                errors.append(f"{owner}：证据 section 不存在 {chapter_id}/{section_id}")
            elif not any(quote in section_text(section) for section in matches):
                errors.append(
                    f"{owner}：引文不匹配 {chapter_id}/{section_id}：{quote[:24]}"
                )
            continue

        hits: list[str] = []
        for section in sections:
            if quote in section_text(section):
                hit_id = str(section.get("id", ""))
                if hit_id not in hits:
                    hits.append(hit_id)
        if len(hits) == 1:
            info.append(
                f"{owner}：引文可唯一解析到 {chapter_id}/{hits[0]}：{quote[:24]}"
            )
        elif len(hits) > 1:
            errors.append(
                f"{owner}：引文在 {chapter_id} 中匹配多个小节 {hits}：{quote[:24]}"
            )
        else:
            errors.append(f"{owner}：引文无法在 {chapter_id} 中定位：{quote[:24]}")
    return len(evidence)


def check_entity_evidence(
    entities: list[dict[str, Any]],
    chapter_index: dict[str, dict[str, Any]],
    errors: list[str],
    warnings: list[str],
    info: list[str],
) -> int:
    total = 0
    for entity in entities:
        entity_id = str(entity.get("id") or "?")
        total += validate_evidence(
            f"实体 {entity_id}",
            entity.get("evidence"),
            chapter_index,
            errors,
            warnings,
            info,
            require_evidence=True,
        )
    return total


# ---------------------------------------------------------------- check: spoilers


def check_spoilers(
    entities: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    entity_index: dict[str, dict[str, Any]],
    warnings: list[str],
) -> None:
    for entity in entities:
        entity_id = str(entity.get("id") or "?")
        spoiler_from = safe_int(entity.get("spoilerFrom"))
        for field in ("summary", "tagline"):
            text = str(entity.get(field) or "")
            if not text:
                continue
            for other in entities:
                other_id = str(other.get("id") or "?")
                if other is entity:
                    continue
                if not any(name in text for name in entity_names(other)):
                    continue
                first_appear = safe_int(other.get("firstAppear"))
                other_spoiler = safe_int(other.get("spoilerFrom"))
                if first_appear > spoiler_from or other_spoiler > spoiler_from:
                    warnings.append(
                        f"实体 {entity_id} 的 {field} 提及 {other_id}，"
                        f"可能剧透（{other_id} firstAppear={first_appear}、"
                        f"spoilerFrom={other_spoiler}，当前 spoilerFrom={spoiler_from}）"
                    )

    for relation in relations:
        relation_from = str(relation.get("from") or "")
        relation_to = str(relation.get("to") or "")
        endpoints = [
            entity_index.get(relation_from),
            entity_index.get(relation_to),
        ]
        if any(endpoint is None for endpoint in endpoints):
            continue
        spoiler_from = safe_int(relation.get("spoilerFrom"))
        first_appears = [safe_int(endpoint.get("firstAppear")) for endpoint in endpoints]
        if spoiler_from < max(first_appears):
            warnings.append(
                f"关系 {relation_from} → {relation_to}"
                f"（{relation.get('label', '')}）的 spoilerFrom={spoiler_from} "
                f"小于端点 firstAppear={max(first_appears)}"
            )


# ----------------------------------------------------------------- check: relations


def check_relations(
    entities: list[dict[str, Any]],
    relations: list[dict[str, Any]],
    chapters: list[dict[str, Any]],
    project: dict[str, Any],
    errors: list[str],
    warnings: list[str],
) -> None:
    entity_ids = {str(entity.get("id") or "") for entity in entities}
    related: set[str] = set()
    seen: set[tuple[str, str, str]] = set()

    for relation in relations:
        relation_from = str(relation.get("from") or "")
        relation_to = str(relation.get("to") or "")
        label = str(relation.get("label") or "")
        if relation_from not in entity_ids:
            errors.append(f"关系 from 端点未知：{relation_from or '空'}")
        if relation_to not in entity_ids:
            errors.append(f"关系 to 端点未知：{relation_to or '空'}")
        if relation_from and relation_from == relation_to:
            warnings.append(f"关系自环：{relation_from}")
        key = (relation_from, relation_to, label)
        if key in seen:
            warnings.append(
                f"重复关系：{relation_from} → {relation_to}（{label}）"
            )
        seen.add(key)
        related.add(relation_from)
        related.add(relation_to)

    body_texts: list[str] = []
    for chapter in chapters:
        variants = chapter_variants(chapter)
        mode = primary_mode(project, chapter)
        variant = variants.get(mode) or next(iter(variants.values()), None)
        if variant is not None:
            body_texts.extend(variant_paragraphs(variant))
    body = "\n".join(body_texts)

    for entity in entities:
        entity_id = str(entity.get("id") or "")
        evidence = entity.get("evidence")
        has_evidence = isinstance(evidence, list) and bool(evidence)
        mentioned = any(name in body for name in entity_names(entity))
        if entity_id not in related and not has_evidence and not mentioned:
            warnings.append(f"实体 {entity_id} 完全孤立：无关系、无证据、无提及")


# --------------------------------------------------------- check: chapter metadata


def check_chapter_metadata(
    project: dict[str, Any],
    chapters: list[dict[str, Any]],
    meta: dict[str, Any],
    errors: list[str],
    warnings: list[str],
) -> None:
    declared_ready = project.get("ready")
    if isinstance(declared_ready, list) and declared_ready:
        ready_ids = [str(item) for item in declared_ready]
    else:
        ready_ids = [str(chapter.get("id") or "") for chapter in chapters]

    for chapter in chapters:
        chapter_id = str(chapter.get("id") or "")
        if chapter_id in ready_ids and chapter_id not in meta:
            warnings.append(f"ready 章节 {chapter_id} 缺 chapter_meta")
        info = meta.get(chapter_id)
        if isinstance(info, dict) and not info.get("cast"):
            warnings.append(f"章节 {chapter_id} 缺 cast")

        variants = chapter_variants(chapter)
        if not all_sections(chapter):
            errors.append(f"章节 {chapter_id} 正文为空或 0 小节")
            continue
        mode = primary_mode(project, chapter)
        variant = variants.get(mode)
        if variant is not None:
            hanzi = sum(
                count_hanzi(section_text(section))
                for section in iter_sections(variant.get("parts", []))
            )
            if hanzi == 0:
                errors.append(f"章节 {chapter_id} 正文为空（主模式 {mode}）")


# --------------------------------------------------------------- check: modes


def check_modes(
    project: dict[str, Any],
    chapters: list[dict[str, Any]],
    errors: list[str],
    warnings: list[str],
) -> None:
    for chapter in chapters:
        chapter_id = str(chapter.get("id") or "")
        variants = chapter_variants(chapter)
        primary = primary_mode(project, chapter)
        primary_variant = variants.get(primary)
        if primary_variant is None:
            continue
        primary_ids = ordered_section_ids(primary_variant)
        primary_hanzi = variant_hanzi(chapter, primary, primary_variant)

        for mode, variant in variants.items():
            if mode == primary:
                continue
            mode_ids = ordered_section_ids(variant)
            missing = [sid for sid in primary_ids if sid not in mode_ids]
            extra = [sid for sid in mode_ids if sid not in primary_ids]
            if missing or extra:
                details: list[str] = []
                if missing:
                    details.append(f"缺失 {missing}")
                if extra:
                    details.append(f"多余 {extra}")
                errors.append(
                    f"章节 {chapter_id}：模式 {mode} 与主模式 {primary} "
                    f"的 section 序列不一致（{'；'.join(details)}）"
                )
            elif primary_ids != mode_ids:
                errors.append(
                    f"章节 {chapter_id}：模式 {mode} 的 section 顺序"
                    f"与主模式 {primary} 不一致"
                )

            mode_hanzi = variant_hanzi(chapter, mode, variant)
            if primary_hanzi > 0:
                ratio = mode_hanzi / primary_hanzi
                if ratio < 0.5 or ratio > 1.5:
                    warnings.append(
                        f"章节 {chapter_id}：{mode}/{primary} 字数比 "
                        f"{ratio:.2f}，超出 0.5–1.5"
                    )


# ---------------------------------------------------------- check: illustrations


def check_illustrations(
    project: Path,
    chapter_index: dict[str, dict[str, Any]],
    errors: list[str],
    warnings: list[str],
) -> None:
    path = project / "content" / "illustrations.json"
    if not path.exists():
        return
    data = load_json(path, errors, "content/illustrations.json")
    if data is None:
        return
    images = data.get("images") if isinstance(data, dict) else data
    if not isinstance(images, list):
        errors.append("illustrations.json 结构无效：缺少 images 列表")
        return

    seen_files: set[str] = set()
    has_chapters = bool(chapter_index)
    for index, image in enumerate(images):
        if not isinstance(image, dict):
            errors.append(f"插图 #{index + 1} 不是对象")
            continue
        source = str(image.get("file") or image.get("src") or "")
        label = str(image.get("id") or source or f"#{index + 1}")

        if not source:
            errors.append(f"插图 {label}：缺少 file")
        elif source.startswith(("http://", "https://")):
            errors.append(f"插图 {label}：不允许远程地址 {source}")
        else:
            file_path = project / source
            if not file_path.exists():
                errors.append(f"插图 {label}：文件不存在 {source}")
            else:
                try:
                    if file_path.stat().st_size > MAX_IMAGE_BYTES:
                        warnings.append(f"插图 {label}：文件超过 2 MB（{source}）")
                except OSError as exc:
                    errors.append(f"插图 {label}：无法读取文件 {source}：{exc}")

        if not image.get("alt"):
            errors.append(f"插图 {label}：缺 alt 文本")
        if image.get("sourceUrl"):
            if not image.get("credit"):
                errors.append(f"插图 {label}：网页来源缺 credit")
            if not image.get("license"):
                errors.append(f"插图 {label}：网页来源缺 license")

        if source:
            if source in seen_files:
                warnings.append(f"插图 {label}：重复 file {source}")
            seen_files.add(source)

        chapter_id = str(image.get("chapter") or "")
        chapter = chapter_index.get(chapter_id)
        if chapter is None:
            if has_chapters:
                warnings.append(
                    f"插图 {label}：未被任何章节引用（chapter={chapter_id or '空'}）"
                )
            continue
        section_id = str(image.get("section") or "")
        if not section_id:
            errors.append(f"插图 {label}：未分配 section")
        elif section_id not in all_section_ids(chapter):
            errors.append(
                f"插图 {label}：section 不存在 {chapter_id}/{section_id}"
            )


# ------------------------------------------------------- check: volumes/timeline


def normalize_volumes(raw: Any) -> list[dict[str, Any]]:
    if isinstance(raw, list):
        return [volume for volume in raw if isinstance(volume, dict)]
    if isinstance(raw, dict):
        return [
            {"id": str(key), **value}
            for key, value in raw.items()
            if isinstance(value, dict)
        ]
    return []


def check_volumes(
    volumes_raw: Any,
    chapters: list[dict[str, Any]],
    errors: list[str],
) -> None:
    volumes = normalize_volumes(volumes_raw)
    chapter_index = {str(chapter.get("id") or ""): chapter for chapter in chapters}
    volume_ids: list[str] = []
    membership: dict[str, list[str]] = {}

    def add_member(chapter_id: str, volume_id: str, source: str) -> None:
        if chapter_id not in chapter_index:
            errors.append(f"卷册 {volume_id}（{source}）引用未知章节 {chapter_id}")
            return
        assigned = membership.setdefault(chapter_id, [])
        if volume_id not in assigned:
            assigned.append(volume_id)

    for volume in volumes:
        volume_id = str(volume.get("id") or "")
        if not volume_id:
            errors.append("卷册缺少 id")
            continue
        if volume_id in volume_ids:
            errors.append(f"卷册 id 重复：{volume_id}")
        volume_ids.append(volume_id)

        listed = volume.get("chapters")
        if isinstance(listed, list):
            seen_in_list: set[str] = set()
            for chapter_id in listed:
                chapter_key = str(chapter_id)
                if chapter_key in seen_in_list:
                    errors.append(
                        f"章节 {chapter_key} 重复归属卷册 {volume_id}"
                    )
                    continue
                seen_in_list.add(chapter_key)
                add_member(chapter_key, volume_id, "chapters")

        if "from" in volume or "to" in volume:
            start = safe_int(volume.get("from"))
            end = safe_int(volume.get("to"), 10**9)
            for chapter_id, chapter in chapter_index.items():
                order = safe_int(chapter.get("order"))
                if start <= order <= end:
                    add_member(chapter_id, volume_id, "from/to")

    for chapter_id, chapter in chapter_index.items():
        declared = chapter.get("volume")
        if not declared:
            continue
        volume_id = str(declared)
        if volume_id not in volume_ids:
            errors.append(f"章节 {chapter_id} 引用未知 volume id：{volume_id}")
            continue
        add_member(chapter_id, volume_id, "chapter.volume")

    for chapter_id, assigned in membership.items():
        if len(assigned) > 1:
            errors.append(f"章节 {chapter_id} 归属多个卷册：{assigned}")


def find_cycle(graph: dict[str, list[str]]) -> list[str] | None:
    state: dict[str, int] = {}
    stack: list[str] = []

    def visit(node: str) -> list[str] | None:
        state[node] = 1
        stack.append(node)
        for target in graph.get(node, []):
            if target not in graph:
                continue
            if state.get(target, 0) == 0:
                cycle = visit(target)
                if cycle:
                    return cycle
            elif state.get(target) == 1:
                start = stack.index(target)
                return stack[start:] + [target]
        stack.pop()
        state[node] = 2
        return None

    for node in graph:
        if state.get(node, 0) == 0:
            cycle = visit(node)
            if cycle:
                return cycle
    return None


def check_timeline(
    project: Path,
    chapter_index: dict[str, dict[str, Any]],
    entity_ids: set[str],
    errors: list[str],
    warnings: list[str],
    info: list[str],
) -> None:
    path = project / "content" / "timeline.json"
    if not path.exists():
        return
    data = load_json(path, errors, "content/timeline.json")
    if not isinstance(data, dict):
        if data is not None:
            errors.append("timeline.json 结构无效：应为对象")
        return
    events = data.get("events")
    if not isinstance(events, list):
        errors.append("timeline.json 缺少 events 列表")
        return

    event_ids: list[str] = []
    for event in events:
        if not isinstance(event, dict):
            errors.append("事件线条目不是对象")
            continue
        event_id = str(event.get("id") or "")
        if not event_id:
            errors.append("事件线事件缺少 id")
            continue
        if event_id in event_ids:
            errors.append(f"事件 id 重复：{event_id}")
        event_ids.append(event_id)

    event_id_set = set(event_ids)
    graph: dict[str, list[str]] = {}

    for event in events:
        if not isinstance(event, dict):
            continue
        event_id = str(event.get("id") or "")
        if not event_id:
            continue
        entities = event.get("entities")
        if isinstance(entities, list):
            for entity_id in entities:
                if str(entity_id) not in entity_ids:
                    errors.append(
                        f"事件 {event_id} 引用未知实体：{entity_id}"
                    )
        chapter_id = str(event.get("chapter") or "")
        chapter = chapter_index.get(chapter_id)
        if chapter_id and chapter is None:
            errors.append(f"事件 {event_id} 引用未知章节：{chapter_id}")
        if chapter is not None:
            spoiler_from = safe_int(event.get("spoilerFrom"))
            order = safe_int(chapter.get("order"))
            if spoiler_from > order:
                warnings.append(
                    f"事件 {event_id} 的 spoilerFrom={spoiler_from} "
                    f"大于锚点章节 {chapter_id} 的 order={order}"
                )

        graph.setdefault(event_id, [])
        causes = event.get("causes")
        consequences = event.get("consequences")
        for field, targets in (
            ("causes", causes if isinstance(causes, list) else []),
            ("consequences", consequences if isinstance(consequences, list) else []),
        ):
            for target in targets:
                target_id = str(target)
                if target_id not in event_id_set:
                    errors.append(
                        f"事件 {event_id} 的 {field} 引用未知事件：{target_id}"
                    )
                elif field == "causes":
                    # cause -> event
                    graph.setdefault(target_id, [])
                    if event_id not in graph[target_id]:
                        graph[target_id].append(event_id)
                elif target_id not in graph[event_id]:
                    # event -> consequence
                    graph[event_id].append(target_id)

        validate_evidence(
            f"事件 {event_id}",
            event.get("evidence"),
            chapter_index,
            errors,
            warnings,
            info,
            require_evidence=False,
        )

    cycle = find_cycle(graph)
    if cycle:
        errors.append(
            "事件线 causes/consequences 存在环："
            + " → ".join(cycle)
        )


# ------------------------------------------------------ check: name candidates


def known_name_set(entities: list[dict[str, Any]]) -> set[str]:
    names: set[str] = set()
    for entity in entities:
        names.update(entity_names(entity))
    return names


def candidate_is_noise(token: str, names: set[str]) -> bool:
    if token in STOP_WORDS:
        return True
    if any(char in STOP_CHARS for char in token):
        return True
    if token in names:
        return True
    if any(token in name for name in names):
        return True
    if any(name in token for name in names):
        return True
    return False


def find_candidate_names(
    project: dict[str, Any],
    chapters: list[dict[str, Any]],
    entities: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    names = known_name_set(entities)
    counts: dict[str, dict[str, Any]] = {}

    for chapter in chapters:
        chapter_id = str(chapter.get("id") or "")
        variants = chapter_variants(chapter)
        mode = primary_mode(project, chapter)
        variant = variants.get(mode) or next(iter(variants.values()), None)
        if variant is None:
            continue
        text = "\n".join(variant_paragraphs(variant))
        token_counts: dict[str, int] = {}
        for run in NAME_RUN_RE.findall(text):
            length = len(run)
            for size in range(WORD_MIN, WORD_MAX + 1):
                if length < size:
                    continue
                for start in range(length - size + 1):
                    token = run[start:start + size]
                    token_counts[token] = token_counts.get(token, 0) + 1
        for token, count in token_counts.items():
            if candidate_is_noise(token, names):
                continue
            record = counts.setdefault(token, {"count": 0, "chapters": set()})
            record["count"] += count
            record["chapters"].add(chapter_id)

    candidates = [
        {
            "name": token,
            "count": record["count"],
            "chapters": sorted(record["chapters"]),
        }
        for token, record in counts.items()
        if record["count"] >= CANDIDATE_MIN_COUNT
        and len(record["chapters"]) >= CANDIDATE_MIN_CHAPTERS
    ]
    candidates.sort(key=lambda item: (-item["count"], item["name"]))
    return candidates


# ------------------------------------------------------ check: annotation coverage


def count_annotations(variant: dict[str, Any]) -> int:
    total = 0
    for section in iter_sections(variant.get("parts", [])):
        for block in section.get("blocks", []):
            if not isinstance(block, dict):
                continue
            total += len(ENT_RE.findall(str(block.get("html", ""))))
            items = block.get("items")
            if isinstance(items, list):
                for item in items:
                    total += len(ENT_RE.findall(str(item)))
    return total


def check_annotation_coverage(
    project: dict[str, Any],
    chapters: list[dict[str, Any]],
    entities: list[dict[str, Any]],
    info: list[str],
) -> None:
    names = sorted(known_name_set(entities), key=len, reverse=True)
    pattern = re.compile("|".join(re.escape(name) for name in names)) if names else None

    for chapter in chapters:
        chapter_id = str(chapter.get("id") or "")
        variants = chapter_variants(chapter)
        mode = primary_mode(project, chapter)
        variant = variants.get(mode)
        if variant is None:
            continue
        annotated = count_annotations(variant)
        body = "\n".join(variant_paragraphs(variant))
        mentioned = len(pattern.findall(body)) if pattern else 0
        ratio = min(1.0, annotated / mentioned) if mentioned else 0.0
        info.append(
            f"章节 {chapter_id}：data-ent {annotated} 处 / 实体名出现 "
            f"{mentioned} 次（覆盖 {ratio:.0%}）"
        )


# --------------------------------------------------------------------- output


def build_stats(
    entities: list[dict[str, Any]], evidence_count: int
) -> dict[str, Any]:
    with_evidence = sum(
        1
        for entity in entities
        if isinstance(entity.get("evidence"), list) and entity.get("evidence")
    )
    coverage = round(with_evidence / len(entities), 4) if entities else 1.0
    return {
        "entities": len(entities),
        "evidence": evidence_count,
        "coverage": coverage,
    }


def print_human(project: Path, report: dict[str, Any]) -> None:
    stats = report["stats"]
    print(f"内容审计：{project}")
    print(
        f"实体 {stats['entities']} · 证据 {stats['evidence']} · "
        f"证据覆盖率 {stats['coverage']:.0%}"
    )
    print(
        f"错误 {len(report['errors'])} · 警告 {len(report['warnings'])} · "
        f"提示 {len(report['info'])} · 候选 {len(report['candidates'])}"
    )

    if report["errors"]:
        print("\n错误：")
        for item in report["errors"]:
            print(f"  - {item}")
    if report["warnings"]:
        print("\n警告：")
        for item in report["warnings"]:
            print(f"  - {item}")
    if report["info"]:
        print("\n提示：")
        for item in report["info"]:
            print(f"  - {item}")
    if report["candidates"]:
        print("\n未链接高频名候选：")
        for candidate in report["candidates"]:
            chapters = "、".join(candidate["chapters"])
            print(
                f"  - {candidate['name']} ×{candidate['count']}"
                f"（{chapters}）"
            )
    if report["errors"]:
        print("\n结果：失败")
    elif report["warnings"]:
        print("\n结果：通过（有警告）")
    else:
        print("\n结果：通过")


def write_report(project: Path, report: dict[str, Any], errors: list[str]) -> None:
    build_dir = project / "build"
    try:
        build_dir.mkdir(parents=True, exist_ok=True)
        (build_dir / "audit_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        errors.append(f"无法写入 build/audit_report.json：{exc}")


def force_utf8_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError, ValueError):
        pass


def empty_report(message: str) -> dict[str, Any]:
    return {
        "errors": [message],
        "warnings": [],
        "info": [],
        "candidates": [],
        "stats": {"entities": 0, "evidence": 0, "coverage": 1.0},
    }


def _utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def main(argv: list[str]) -> int:
    _utf8_stdio()
    if not argv:
        print(
            "usage: audit_content.py <project-dir> [--json] [--strict]",
            file=sys.stderr,
        )
        return 2
    project = Path(argv[0]).resolve()
    flags = argv[1:]
    strict = "--strict" in flags
    json_output = "--json" in flags

    if not project.is_dir():
        report = empty_report(f"项目目录不存在：{project}")
        if json_output:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print(report["errors"][0], file=sys.stderr)
        return 1

    errors: list[str] = []
    warnings: list[str] = []
    info: list[str] = []

    chapters, build_config = load_chapters(project, errors)
    project_data = load_json(project / "project.json", errors, "project.json")
    if not isinstance(project_data, dict):
        project_data = {}
    config: dict[str, Any] = dict(build_config)
    config.update(project_data)

    content = project / "content"
    entities_data = load_json(content / "entities.json", errors, "content/entities.json")
    if not isinstance(entities_data, dict):
        entities_data = {"entities": [], "relations": []}
    entities = [
        entity
        for entity in entities_data.get("entities", [])
        if isinstance(entity, dict)
    ]
    relations = [
        relation
        for relation in entities_data.get("relations", [])
        if isinstance(relation, dict)
    ]
    if not (content / "entities.json").exists():
        warnings.append("缺少 content/entities.json，实体相关检查已跳过")

    meta_data = load_json(content / "chapter_meta.json", errors, "content/chapter_meta.json")
    meta = meta_data if isinstance(meta_data, dict) else {}

    chapter_index = {str(chapter.get("id") or ""): chapter for chapter in chapters}
    entity_index = {str(entity.get("id") or ""): entity for entity in entities}
    entity_ids = set(entity_index)

    evidence_count = check_entity_evidence(
        entities, chapter_index, errors, warnings, info
    )
    check_spoilers(entities, relations, entity_index, warnings)
    check_relations(entities, relations, chapters, config, errors, warnings)
    check_chapter_metadata(config, chapters, meta, errors, warnings)
    check_modes(config, chapters, errors, warnings)
    check_illustrations(project, chapter_index, errors, warnings)
    check_volumes(config.get("volumes"), chapters, errors)
    check_timeline(project, chapter_index, entity_ids, errors, warnings, info)
    candidates = find_candidate_names(config, chapters, entities)
    check_annotation_coverage(config, chapters, entities, info)

    report: dict[str, Any] = {
        "errors": errors,
        "warnings": warnings,
        "info": info,
        "candidates": candidates,
        "stats": build_stats(entities, evidence_count),
    }
    write_report(project, report, errors)

    if json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_human(project, report)

    if errors:
        return 1
    if strict and warnings:
        return 1
    return 0


if __name__ == "__main__":
    force_utf8_stdout()
    sys.exit(main(sys.argv[1:]))
