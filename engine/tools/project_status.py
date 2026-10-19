#!/usr/bin/env python3
"""Story Forge — project status report.

Usage:
    python project_status.py <project-dir> [--json] [--strict]

Reads project.json, content/*.json, the configured source files and the build
outputs (build/chapters.json, build/parse_report.json), then writes a single
deterministic report to build/status.json.

Design rules:
- Never execute the parser; this tool only inspects files.
- Degrade gracefully when build outputs are missing (stale/fidelity are null).
- Support both the legacy kind/sourceDir/retoldDir mode synthesis and the
  generalized project.variants / chapter.variantFiles shape.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

try:  # same tools directory when executed as a script
    from source_check import build_report as build_source_report
except ImportError:  # pragma: no cover - defensive
    build_source_report = None

HANZI_RE = re.compile(r"[一-鿿]")
KNOWN_KINDS = {"import", "retelling", "creation"}


class StatusError(Exception):
    """Fatal condition: missing core files or unreadable JSON."""


def count_hanzi(text: str) -> int:
    return len(HANZI_RE.findall(text))


def read_json(path: Path, default: Any = None) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise StatusError(f"无法读取 JSON 文件 {path}: {exc}") from exc


def as_dict_list(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, dict)]


def as_str_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


# ---------------------------------------------------------------------------
# Mode / variant synthesis (mirrors parse_chapters.py)
# ---------------------------------------------------------------------------


def project_variant_defs(config: dict[str, Any]) -> list[dict[str, Any]]:
    raw = config.get("variants")
    if not isinstance(raw, list):
        return []
    defs: list[dict[str, Any]] = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        variant_id = str(item.get("id") or "").strip()
        if not variant_id:
            continue
        variants = dict(item)
        variants["id"] = variant_id
        defs.append(variants)
    return defs


def infer_kind(config: dict[str, Any]) -> str:
    kind = str(config.get("kind") or "").lower()
    if kind in KNOWN_KINDS:
        return kind
    if config.get("sourceDir") == "chapters" and "retoldDir" not in config:
        return "creation"
    if any(
        isinstance(spec, dict) and spec.get("retoldFiles")
        for spec in config.get("chapters") or []
    ):
        return "retelling"
    return "import"


def primary_mode(config: dict[str, Any]) -> str:
    """Return the mode that owns the project's main body text."""
    defs = project_variant_defs(config)
    for variant in defs:
        if variant.get("primary"):
            return str(variant["id"])
    if defs:
        return str(defs[0]["id"])
    kind = str(config.get("kind") or "").lower()
    if kind == "creation":
        return "retold"
    if kind == "import":
        return "original"
    if config.get("sourceDir") == "chapters" and "retoldDir" not in config:
        return "retold"
    return str(config.get("primaryMode") or "original")


def variant_order(config: dict[str, Any]) -> list[str]:
    """Ordered variant ids: primary first, then project order / chapter keys."""
    defs = project_variant_defs(config)
    ids: list[str]
    if defs:
        ids = [str(variant["id"]) for variant in defs]
        primary = primary_mode(config)
        if primary in ids:
            ids.remove(primary)
        ids.insert(0, primary)
    else:
        primary = primary_mode(config)
        ids = [primary]
        for spec in as_dict_list(config.get("chapters")):
            retold = spec.get("retoldFiles")
            if retold and "retold" not in ids:
                ids.append("retold")
            variant_files = spec.get("variantFiles")
            if isinstance(variant_files, dict):
                for mode in variant_files:
                    mode_id = str(mode)
                    if mode_id not in ids:
                        ids.append(mode_id)
    return ids


def is_generalized(config: dict[str, Any], spec: dict[str, Any]) -> bool:
    return bool(project_variant_defs(config)) or isinstance(
        spec.get("variantFiles"), dict
    )


def chapter_mode_files(
    config: dict[str, Any], spec: dict[str, Any]
) -> dict[str, list[str]]:
    """Return {mode: [filename, ...]} for one chapter spec."""
    primary = primary_mode(config)
    primary_files = as_str_list(spec.get("files"))
    variant_files: dict[str, list[str]] = {}
    raw_variant_files = spec.get("variantFiles")
    if isinstance(raw_variant_files, dict):
        for mode, files in raw_variant_files.items():
            if isinstance(files, list):
                variant_files[str(mode)] = as_str_list(files)
    retold_files = as_str_list(spec.get("retoldFiles"))
    if retold_files and "retold" not in variant_files:
        variant_files["retold"] = retold_files

    if not is_generalized(config, spec):
        if retold_files:
            # Mirrors parse_chapters.spec_modes: ["original", "retold"].
            return {"original": primary_files, "retold": retold_files}
        return {primary: primary_files}

    modes = variant_order(config)
    for mode in variant_files:
        if mode not in modes:
            modes.append(mode)
    result: dict[str, list[str]] = {}
    for mode in modes:
        if mode == primary:
            files = primary_files or variant_files.get(mode, [])
        else:
            files = variant_files.get(mode, [])
        result[mode] = files
    return result


def mode_dir(config: dict[str, Any], mode: str) -> Path:
    for variant in project_variant_defs(config):
        if variant["id"] == mode and variant.get("dir"):
            return Path(str(variant["dir"]))
    if mode == primary_mode(config):
        default_source = (
            "chapters" if infer_kind(config) == "creation" else "sources"
        )
        return Path(str(config.get("sourceDir") or default_source))
    if mode == "retold":
        return Path(str(config.get("retoldDir") or "retold"))
    return Path(mode)


def discover_specs(
    project_dir: Path, config: dict[str, Any]
) -> list[dict[str, Any]]:
    specs = config.get("chapters")
    if isinstance(specs, list) and specs:
        result: list[dict[str, Any]] = []
        for index, raw in enumerate(specs, 1):
            if not isinstance(raw, dict):
                continue
            spec = dict(raw)
            spec.setdefault("order", index)
            spec.setdefault("id", f"ch{index}")
            spec.setdefault("mode", "parts")
            result.append(spec)
        return result

    source_dir = project_dir / str(config.get("sourceDir") or "sources")
    if not source_dir.is_dir():
        return []
    files = sorted(
        path.name
        for path in source_dir.glob("*.md")
        if path.name.lower() != "readme.md"
    )
    return [
        {"id": f"ch{index}", "order": index, "files": [name], "mode": "parts"}
        for index, name in enumerate(files, 1)
    ]


# ---------------------------------------------------------------------------
# Build loading
# ---------------------------------------------------------------------------


def load_build(
    project_dir: Path,
) -> tuple[list[dict[str, Any]], dict[str, Any] | None, Path | None]:
    build_dir = project_dir / "build"
    chapters_raw = read_json(build_dir / "chapters.json", default=None)
    report_raw = read_json(build_dir / "parse_report.json", default=None)
    if chapters_raw is not None and not isinstance(chapters_raw, list):
        raise StatusError(f"build/chapters.json 格式错误：应为数组 ({build_dir})")
    if report_raw is not None and not isinstance(report_raw, dict):
        raise StatusError(f"build/parse_report.json 格式错误：应为对象 ({build_dir})")
    chapters = as_dict_list(chapters_raw)
    report = report_raw if isinstance(report_raw, dict) else None
    report_path = build_dir / "parse_report.json"
    return chapters, report, report_path if report is not None else None


def build_variant_payload(
    chapter_build: dict[str, Any], mode: str
) -> dict[str, Any] | None:
    variants = chapter_build.get("variants")
    if isinstance(variants, dict) and variants:
        payload = variants.get(mode)
        return payload if isinstance(payload, dict) else None
    mode_names = as_str_list(chapter_build.get("modeNames"))
    default = chapter_build.get("defaultMode")
    if mode_names and mode not in mode_names and mode != default:
        return None
    return chapter_build


def build_mode_names(chapter_build: dict[str, Any]) -> list[str]:
    names = as_str_list(chapter_build.get("modeNames"))
    if names:
        return names
    variants = chapter_build.get("variants")
    if isinstance(variants, dict):
        return [str(key) for key in variants]
    default = chapter_build.get("defaultMode")
    if isinstance(default, str) and default:
        return [default]
    return []


def count_sections(parts: Any) -> int:
    if not isinstance(parts, list):
        return 0
    total = 0
    for part in parts:
        if isinstance(part, dict) and isinstance(part.get("sections"), list):
            total += len(part["sections"])
    return total


def section_ids(chapter_build: dict[str, Any], mode: str) -> list[str] | None:
    payload = build_variant_payload(chapter_build, mode)
    if payload is None:
        return None
    parts = payload.get("parts")
    if not isinstance(parts, list):
        return None
    ids: list[str] = []
    for part in parts:
        if not isinstance(part, dict):
            continue
        for section in part.get("sections") or []:
            if isinstance(section, dict) and section.get("id") is not None:
                ids.append(str(section["id"]))
    return ids


def preferred_parts(chapter_build: dict[str, Any]) -> Any:
    variants = chapter_build.get("variants")
    if isinstance(variants, dict) and variants:
        default = chapter_build.get("defaultMode")
        payload = variants.get(default) if isinstance(default, str) else None
        if not isinstance(payload, dict):
            payload = next(iter(variants.values()))
        return payload.get("parts") if isinstance(payload, dict) else None
    return chapter_build.get("parts")


# ---------------------------------------------------------------------------
# Staleness / fidelity
# ---------------------------------------------------------------------------


def sha256_file(path: Path) -> str | None:
    try:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()
    except OSError:
        return None


def recorded_hashes(report: dict[str, Any] | None) -> dict[str, str]:
    if not isinstance(report, dict):
        return {}
    merged: dict[str, str] = {}
    for key in ("sourceHashes", "hashes", "fileHashes", "sources", "files"):
        value = report.get(key)
        if not isinstance(value, dict):
            continue
        for raw_name, raw_value in value.items():
            digest: Any = raw_value
            if isinstance(raw_value, dict):
                digest = (
                    raw_value.get("sha256")
                    or raw_value.get("hash")
                    or raw_value.get("value")
                )
            if isinstance(digest, str) and digest:
                merged[str(raw_name).replace("\\", "/")] = digest.lower()
    return merged


def variant_stale(
    project_dir: Path,
    report: dict[str, Any] | None,
    report_path: Path | None,
    chapter_id: str,
    mode: str,
    source_dir: Path,
    files: list[str],
) -> bool | None:
    """True when sources are newer than (or differ from) the parse report."""
    if report is None or report_path is None:
        return None
    if not files:
        return False
    paths = [source_dir / name for name in files]
    if any(not path.is_file() for path in paths):
        # Missing sources are reported as present=false; do not call them stale.
        return False
    hashes = recorded_hashes(report)
    try:
        report_mtime = report_path.stat().st_mtime
    except OSError:
        report_mtime = None

    for name, path in zip(files, paths):
        rel: str | None = None
        try:
            rel = path.resolve().relative_to(project_dir.resolve()).as_posix()
        except (OSError, ValueError):
            rel = None
        candidates = [
            candidate
            for candidate in (
                rel,
                name,
                f"{chapter_id}:{mode}:{name}",
                f"{chapter_id}:{mode}",
                f"{mode}:{name}",
            )
            if candidate
        ]
        recorded = next(
            (hashes[candidate] for candidate in candidates if candidate in hashes),
            None,
        )
        if recorded:
            actual = sha256_file(path)
            if actual is None:
                return False
            if actual.lower() != recorded:
                return True
        elif report_mtime is not None:
            try:
                if path.stat().st_mtime > report_mtime:
                    return True
            except OSError:
                return False
    return False


def variant_fidelity(
    report: dict[str, Any] | None, chapter_id: str, mode: str, mode_count: int
) -> bool | None:
    if not isinstance(report, dict):
        return None
    by_mode = report.get("fidelityByMode")
    key = f"{chapter_id}:{mode}"
    if isinstance(by_mode, dict) and key in by_mode:
        return bool(by_mode[key])
    overall = report.get("fidelity")
    if isinstance(overall, bool):
        if overall:
            return True
        return overall if mode_count <= 1 else None
    return None


def source_hanzi(source_dir: Path, files: list[str]) -> int:
    total = 0
    for name in files:
        path = source_dir / name
        if not path.is_file():
            continue
        try:
            total += count_hanzi(path.read_text(encoding="utf-8-sig"))
        except (OSError, UnicodeDecodeError):
            continue
    return total


# ---------------------------------------------------------------------------
# Status assembly
# ---------------------------------------------------------------------------


def compute_ready_ids(
    config: dict[str, Any],
    specs: list[dict[str, Any]],
    meta: dict[str, Any],
) -> set[str]:
    configured = config.get("ready")
    if isinstance(configured, list) and configured:
        return {str(item) for item in configured}
    with_meta = [str(spec["id"]) for spec in specs if str(spec["id"]) in meta]
    if with_meta:
        return set(with_meta)
    return {str(spec["id"]) for spec in specs}


def volume_for_chapter(
    spec: dict[str, Any], order: int, config: dict[str, Any]
) -> str | None:
    volume = spec.get("volume")
    if isinstance(volume, str) and volume:
        return volume
    for raw in as_dict_list(config.get("volumes")):
        volume_id = raw.get("id")
        if volume_id is None:
            continue
        chapter_ids = as_str_list(raw.get("chapters"))
        if str(spec["id"]) in chapter_ids:
            return str(volume_id)
        try:
            lower = int(raw.get("from"))
            upper = int(raw.get("to"))
        except (TypeError, ValueError):
            continue
        if lower <= order <= upper:
            return str(volume_id)
    return None


def illustration_stats(
    images: list[dict[str, Any]],
) -> dict[str, int]:
    placed = 0
    missing_alt = 0
    missing_credit = 0
    for image in images:
        if str(image.get("section") or "").strip() or image.get("status") == "placed":
            placed += 1
        if not str(image.get("alt") or "").strip():
            missing_alt += 1
        if str(image.get("sourceUrl") or "").strip() and not str(
            image.get("credit") or ""
        ).strip():
            missing_credit += 1
    return {
        "total": len(images),
        "placed": placed,
        "unplaced": len(images) - placed,
        "missingAlt": missing_alt,
        "missingCredit": missing_credit,
    }


def build_status(
    project_dir: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Return (status_payload, internal_flags)."""
    project_path = project_dir / "project.json"
    if not project_path.is_file():
        raise StatusError(f"缺少 project.json：{project_path}")
    content_dir = project_dir / "content"
    if not content_dir.is_dir():
        raise StatusError(f"缺少 content 目录：{content_dir}")

    config_raw = read_json(project_path, default=None)
    if not isinstance(config_raw, dict):
        raise StatusError(f"project.json 格式错误：应为对象 ({project_path})")
    config: dict[str, Any] = config_raw

    specs = discover_specs(project_dir, config)
    specs.sort(key=lambda spec: (to_int(spec.get("order")), str(spec["id"])))

    entities_data = read_json(
        content_dir / "entities.json",
        default={"entities": [], "relations": []},
    )
    if not isinstance(entities_data, dict):
        entities_data = {"entities": [], "relations": []}
    entities = as_dict_list(entities_data.get("entities"))
    relations = as_dict_list(entities_data.get("relations"))

    meta_raw = read_json(content_dir / "chapter_meta.json", default={})
    meta: dict[str, Any] = meta_raw if isinstance(meta_raw, dict) else {}

    recap = read_json(content_dir / "recap.json", default={})
    if not isinstance(recap, dict):
        recap = {}
    worldview = read_json(content_dir / "worldview.json", default={})
    if not isinstance(worldview, dict):
        worldview = {}
    timeline = read_json(content_dir / "timeline.json", default={})
    if not isinstance(timeline, dict):
        timeline = {}

    illustrations_raw = read_json(
        content_dir / "illustrations.json", default={"images": []}
    )
    if isinstance(illustrations_raw, dict):
        images = as_dict_list(illustrations_raw.get("images"))
    else:
        images = as_dict_list(illustrations_raw)

    build_chapters, report, report_path = load_build(project_dir)
    build_map: dict[str, dict[str, Any]] = {}
    for item in build_chapters:
        if item.get("id") is not None:
            build_map[str(item["id"])] = item
    build_present = bool(build_chapters) or report is not None

    by_type: dict[str, int] = {}
    entities_without_evidence = 0
    for entity in entities:
        entity_type = str(entity.get("type") or "unknown")
        by_type[entity_type] = by_type.get(entity_type, 0) + 1
        if not entity.get("evidence"):
            entities_without_evidence += 1

    ready_ids = compute_ready_ids(config, specs, meta)
    primary = primary_mode(config)
    ordered_modes = variant_order(config)

    chapter_entries: list[dict[str, Any]] = []
    available_modes: set[str] = set()
    missing_source_labels: list[str] = []
    stale_labels: list[str] = []
    alignment_issues: list[str] = []
    missing_meta_ids: list[str] = []
    unready_ids: list[str] = []
    missing_primary: list[str] = []

    for spec in specs:
        chapter_id = str(spec["id"])
        order = to_int(spec.get("order"))
        chapter_build = build_map.get(chapter_id)
        mode_files = chapter_mode_files(config, spec)

        variants: dict[str, dict[str, Any]] = {}
        for mode, files in mode_files.items():
            source_dir = project_dir / mode_dir(config, mode)
            present = bool(files) and all(
                (source_dir / name).is_file() for name in files
            )
            if present:
                available_modes.add(mode)
            if files and not present:
                missing = [
                    name for name in files if not (source_dir / name).is_file()
                ]
                if missing:
                    missing_source_labels.append(
                        f"{chapter_id}[{mode}]: {', '.join(missing)}"
                    )
            if not files and mode == primary:
                missing_primary.append(f"{chapter_id}[{mode}]")

            payload = (
                build_variant_payload(chapter_build, mode)
                if chapter_build is not None
                else None
            )
            hanzi = source_hanzi(source_dir, files)
            if isinstance(payload, dict) and isinstance(payload.get("hanzi"), int):
                hanzi = int(payload["hanzi"])
            fidelity = variant_fidelity(report, chapter_id, mode, len(mode_files))
            stale = variant_stale(
                project_dir, report, report_path, chapter_id, mode, source_dir, files
            )
            if stale:
                stale_labels.append(f"{chapter_id}[{mode}]")
            variants[mode] = {
                "files": files,
                "present": present,
                "hanzi": hanzi,
                "fidelity": fidelity,
                "stale": stale,
            }

        if chapter_build is not None:
            for mode in build_mode_names(chapter_build):
                if mode in mode_files or mode in variants:
                    available_modes.add(mode)

        sections = (
            count_sections(preferred_parts(chapter_build))
            if chapter_build is not None
            else 0
        )

        title = str(spec.get("title") or "")
        if not title and chapter_build is not None:
            title = str(chapter_build.get("title") or "")

        entry = {
            "id": chapter_id,
            "order": order,
            "title": title,
            "volume": volume_for_chapter(spec, order, config),
            "parsed": chapter_build is not None,
            "ready": chapter_id in ready_ids,
            "meta": chapter_id in meta,
            "sections": sections,
            "cast": len(as_str_list(meta.get(chapter_id, {}).get("cast")))
            if isinstance(meta.get(chapter_id), dict)
            else 0,
            "variants": variants,
            "illustrations": sum(
                1 for image in images if str(image.get("chapter")) == chapter_id
            ),
        }
        chapter_entries.append(entry)

        if chapter_id not in meta:
            missing_meta_ids.append(chapter_id)
        if chapter_id not in ready_ids:
            unready_ids.append(chapter_id)

        # Alignment checks need build output.
        if build_present:
            if chapter_build is None:
                alignment_issues.append(
                    f"章节 {chapter_id} 未出现在 build/chapters.json，请重新运行 parse"
                )
            else:
                built_modes = build_mode_names(chapter_build)
                present_modes = [
                    mode for mode, info in variants.items() if info["present"]
                ]
                for mode in present_modes:
                    if built_modes and mode not in built_modes:
                        alignment_issues.append(
                            f"章节 {chapter_id} 的 {mode} 变体未出现在 "
                            "build/chapters.json，请重新运行 parse"
                        )
                sequences: dict[str, list[str]] = {}
                for mode in present_modes:
                    ids = section_ids(chapter_build, mode)
                    if ids is not None:
                        sequences[mode] = ids
                ordered = list(sequences)
                if len(ordered) > 1:
                    base_mode = ordered[0]
                    for other in ordered[1:]:
                        if sequences[other] != sequences[base_mode]:
                            alignment_issues.append(
                                f"章节 {chapter_id} 的 {base_mode}/{other} "
                                "变体小节结构不一致（检查源文件标题层级）"
                            )

    modes: list[str] = []
    for mode in ordered_modes + sorted(available_modes):
        if mode in available_modes and mode not in modes:
            modes.append(mode)
    if not modes:
        modes = [primary]

    if report is not None and isinstance(report.get("hanzi"), int):
        project_hanzi = int(report["hanzi"])
    else:
        project_hanzi = sum(
            int(entry["variants"].get(primary, {}).get("hanzi") or 0)
            for entry in chapter_entries
        )

    parse_errors = as_str_list(report.get("errors")) if report else []
    parse_warnings = as_str_list(report.get("warnings")) if report else []
    fidelity_failed = bool(report and report.get("fidelity") is False)

    report_at: str | None = None
    if report_path is not None:
        try:
            report_at = datetime.fromtimestamp(
                report_path.stat().st_mtime
            ).isoformat(timespec="seconds")
        except OSError:
            report_at = None

    ill_stats = illustration_stats(images)

    status: dict[str, Any] = {
        "project": {
            "path": str(project_dir),
            "title": str(config.get("title") or ""),
            "kind": infer_kind(config),
            "modes": modes,
            "chapterCount": len(chapter_entries),
            "readyCount": sum(1 for entry in chapter_entries if entry["ready"]),
            "hanzi": project_hanzi,
        },
        "chapters": chapter_entries,
        "content": {
            "entities": len(entities),
            "byType": {key: by_type[key] for key in sorted(by_type)},
            "relations": len(relations),
            "entitiesWithoutEvidence": entities_without_evidence,
            "recapEras": len(as_dict_list(recap.get("eras"))),
            "worldviewCards": len(as_dict_list(worldview.get("cards"))),
            "timelineEvents": len(as_dict_list(timeline.get("events"))),
        },
        "illustrations": ill_stats,
        "build": {
            "parseReportAt": report_at,
            "errors": parse_errors,
            "warnings": parse_warnings,
        },
        "nextActions": [],
    }

    actions: list[str] = []
    project_label = str(project_dir)
    chapters_file_exists = (project_dir / "build" / "chapters.json").is_file()
    incomplete_build = build_present and (
        report is None or not chapters_file_exists
    )
    if not build_present:
        actions.append(
            "尚未生成构建数据：运行 "
            f"python scripts/story.py parse {project_label}"
        )
    elif report is None:
        actions.append(
            "缺少 build/parse_report.json：运行 "
            f"python scripts/story.py parse {project_label}"
        )
    elif not chapters_file_exists:
        actions.append(
            "缺少 build/chapters.json：运行 "
            f"python scripts/story.py parse {project_label}"
        )
    if parse_errors:
        actions.append(
            f"修复 parse 报告的 {len(parse_errors)} 个错误"
            "（见 build/parse_report.json）"
        )
    if fidelity_failed:
        actions.append(
            "正文保真校验失败：检查 build/parse_report.json 的差异，"
            "修复源文件后重新运行 parse"
        )
    if parse_warnings:
        actions.append(
            f"处理 parse 报告的 {len(parse_warnings)} 条警告"
            "（见 build/parse_report.json）"
        )
    if alignment_issues:
        actions.append("修复变体对齐：" + "；".join(dict.fromkeys(alignment_issues)))
    if missing_source_labels:
        actions.append(
            "以下章节变体缺少源文件，请补齐后重新 parse："
            + "，".join(dict.fromkeys(missing_source_labels))
        )
    if missing_primary:
        actions.append(
            "以下主变体没有声明源文件："
            + "，".join(dict.fromkeys(missing_primary))
        )
    if stale_labels:
        actions.append(
            "以下变体的源文件在 parse 后有改动，请重新运行 parse："
            + "，".join(dict.fromkeys(stale_labels))
        )
    if ill_stats["unplaced"]:
        actions.append(
            f"有 {ill_stats['unplaced']} 张插图尚未分配小节：运行 "
            f"python scripts/story.py place-images {project_label} --apply"
        )
    if entities_without_evidence:
        actions.append(
            f"有 {entities_without_evidence} 个实体缺少证据："
            "在 content/entities.json 中补充 chapter/section/quote"
        )
    if missing_meta_ids:
        actions.append(
            f"有 {len(missing_meta_ids)} 章缺少章节元数据"
            f"（{', '.join(missing_meta_ids)}）："
            "在 content/chapter_meta.json 中补充"
        )
    if unready_ids:
        actions.append(
            f"有 {len(unready_ids)} 章尚未标记为 ready"
            f"（{', '.join(unready_ids)}）：确认内容后更新 project.json 的 ready"
        )
    source_action_needed = False
    if build_source_report is not None:
        try:
            source_info = build_source_report(project_dir)
        except Exception:
            source_info = None
        if source_info:
            status["source"] = {
                key: source_info.get(key)
                for key in (
                    "policy",
                    "basedOn",
                    "sourceDir",
                    "present",
                    "fileCount",
                    "next",
                    "queries",
                    "provenance",
                )
            }
            if source_info["next"] in ("search_original", "search_reference"):
                source_action_needed = True
                queries = " / ".join(source_info.get("queries", [])[:3])
                actions.insert(
                    0,
                    "没有源文本：先用 WebSearch 搜索 "
                    f"{queries or source_info.get('title', '')}，"
                    f"再用 python scripts/story.py ingest {project_label} <source> 导入",
                )
            elif source_info["next"] in ("record_provenance", "confirm_rights"):
                source_action_needed = True
                actions.append(
                    "补全 content/source_provenance.json："
                    "登记来源、用途（primary-text / reference）与许可"
                )
    if not actions:
        actions.append(
            "项目状态正常：可以运行 "
            f"python scripts/story.py build {project_label}"
        )
    status["nextActions"] = actions

    warnings_present = bool(
        source_action_needed
        or parse_warnings
        or not build_present
        or incomplete_build
        or fidelity_failed
        or parse_errors
        or alignment_issues
        or missing_source_labels
        or missing_primary
        or stale_labels
        or ill_stats["unplaced"]
        or entities_without_evidence
        or missing_meta_ids
        or unready_ids
    )
    internal = {
        "errors": bool(parse_errors) or fidelity_failed,
        "warnings": warnings_present,
    }
    return status, internal


# ---------------------------------------------------------------------------
# Human output
# ---------------------------------------------------------------------------


def short(text: str, width: int = 24) -> str:
    return text if len(text) <= width else text[: width - 1] + "…"


def format_human(status: dict[str, Any]) -> str:
    project = status["project"]
    chapters = status["chapters"]
    content = status["content"]
    illustrations = status["illustrations"]
    build = status["build"]

    title = project["title"] or "(未命名)"
    lines = [
        f"项目：{title}  [{project['kind']}]",
        f"路径：{project['path']}",
        (
            f"模式：{', '.join(project['modes']) or '-'} | "
            f"章节：{project['chapterCount']} | "
            f"可读：{project['readyCount']} | "
            f"正文：{project['hanzi']} 字"
        ),
        "",
        "章节矩阵：",
        "  序  章节     标题                     状态   字数   小节  人物  插图",
    ]
    for entry in chapters:
        primary_mode_id = project["modes"][0] if project["modes"] else ""
        variant = entry["variants"].get(primary_mode_id, {})
        if not variant and entry["variants"]:
            variant = next(iter(entry["variants"].values()))
        hanzi = int(variant.get("hanzi") or 0)
        state = "ready" if entry["ready"] else "待续"
        if not entry["meta"]:
            state += "*"
        lines.append(
            f"  {entry['order']:<3} {short(entry['id'], 8):<8} "
            f"{short(entry['title'], 24):<24} {state:<6} "
            f"{hanzi:<6} {entry['sections']:<4} {entry['cast']:<4} "
            f"{entry['illustrations']}"
        )
        details: list[str] = []
        for mode, info in entry["variants"].items():
            marker = "OK" if info["present"] else "缺失"
            extras: list[str] = []
            if info["stale"] is True:
                extras.append("源文件已更新")
            if info["fidelity"] is False:
                extras.append("保真失败")
            suffix = f"，{'，'.join(extras)}" if extras else ""
            details.append(f"{mode} {info['hanzi']}字 {marker}{suffix}")
        if details:
            lines.append("       变体：" + " / ".join(details))

    lines.extend(
        [
            "",
            "内容覆盖：",
            (
                f"  实体 {content['entities']}（"
                + (", ".join(f"{k} {v}" for k, v in content["byType"].items()) or "无")
                + f"）| 关系 {content['relations']} | "
                f"无证据 {content['entitiesWithoutEvidence']}"
            ),
            (
                f"  前情 {content['recapEras']} 个时代 | "
                f"世界观 {content['worldviewCards']} 张卡 | "
                f"时间线 {content['timelineEvents']} 个事件"
            ),
            (
                f"插图：共 {illustrations['total']}，已放置 {illustrations['placed']}，"
                f"未放置 {illustrations['unplaced']}，"
                f"缺 alt {illustrations['missingAlt']}，"
                f"缺 credit {illustrations['missingCredit']}"
            ),
            (
                f"构建：parse 报告 {build['parseReportAt'] or '未生成'} | "
                f"错误 {len(build['errors'])} | 警告 {len(build['warnings'])}"
            ),
            "",
            "下一步：",
        ]
    )
    for action in status["nextActions"]:
        lines.append(f"  - {action}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Story Forge 项目状态报告（写入 build/status.json）"
    )
    parser.add_argument("project", help="项目目录")
    parser.add_argument("--json", action="store_true", help="只输出 JSON 对象")
    parser.add_argument(
        "--strict", action="store_true", help="有警告时也返回退出码 1"
    )
    return parser.parse_args(argv)


def _utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    _utf8_stdio()
    args = parse_args(sys.argv[1:] if argv is None else argv)
    project_dir = Path(args.project).resolve()
    try:
        status, internal = build_status(project_dir)
    except StatusError as exc:
        print(f"status: {exc}", file=sys.stderr)
        return 1

    build_dir = project_dir / "build"
    try:
        build_dir.mkdir(parents=True, exist_ok=True)
        (build_dir / "status.json").write_text(
            json.dumps(status, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError as exc:
        print(f"status: 无法写入 build/status.json: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(status, ensure_ascii=False, indent=2))
    else:
        print(format_human(status))

    if internal["errors"]:
        return 1
    if args.strict and internal["warnings"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
