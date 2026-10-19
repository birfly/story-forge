#!/usr/bin/env python3
"""Story Forge — style lint and quantitative style metrics.

Flags aphoristic / abstract / over-interpretive phrasing in authored metadata,
then compares per-mode prose metrics against the primary mode baseline.

Evidence quotes are skipped: they are verbatim source text.

Usage:
    python style_lint.py <project-dir> [--strict] [--json] [--no-metrics]

Outputs:
    build/style_report.json

Exit codes:
    0  no errors (and no warnings under --strict)
    1  operational errors, or warnings when --strict is given
    2  usage error
"""
from __future__ import annotations

import json
import math
import re
import statistics
import sys
from pathlib import Path
from typing import Any, Iterator

HANZI_RE = re.compile(r"[一-鿿]")
SENTENCE_SPLIT_RE = re.compile(r"[。！？!?…]+")
LINK_RE = re.compile(r"\[([^\]]+)\]\(([^)\s]+)\)")
HR_RE = re.compile(r"^\s*(?:---|\*\*\*|___)\s*$")
TAG_RE = re.compile(r"<[^>]+>")

PUNCTUATION = "，。！？；：…"
DIALOGUE_MARKS = "「」『』“”"
LONG_SENTENCE_HANZI = 60

# Relative thresholds, from docs/improvements-spec.md section 三.
SENTENCE_DRIFT_LIMIT = 0.35
DIALOGUE_DRIFT_LIMIT = 0.50
DIALOGUE_ABS_LIMIT = 0.10
VERBATIM_SECTION_LIMIT = 0.80
META_SENTENCE_DRIFT_LIMIT = 0.50
META_LONG_SENTENCE_LIMIT = 0.30

# Patterns that usually signal a "copywriter voice" rather than the source voice.
BANNED = [
    (re.compile(r"不是.{0,14}而是"), "对称金句：不是 A 而是 B"),
    (re.compile(r"并非.{0,14}而是"), "对称金句：并非 A 而是 B"),
    (re.compile(r"与其说"), "对称金句：与其说"),
    (re.compile(r"真正的.{0,10}是"), "升华句：真正的 X 是 Y"),
    (re.compile(r"这正是"), "升华句：这正是……"),
    (re.compile(r"这意味着"), "升华句：这意味着"),
    (re.compile(r"才真正"), "升华句：才真正……"),
    (re.compile(r"某种意义上"), "抽象限定：某种意义上"),
    (re.compile(r"令人动容|意味深长|充满张力|令人唏嘘"), "空泛评价"),
    (re.compile(r"终于明白|终于学会|终于懂得"), "替角色下结论"),
]

# Softer warnings: legitimate in some stories, but worth re-reading.
SOFT = [
    (re.compile(r"宿命|救赎|命运|注定|时代的洪流|成长的完成|关系的重量"), "抽象大词"),
    (re.compile(r"困境|悖论|隐喻|象征"), "可能过度解释"),
]

SCAN_KEYS = {
    "tagline",
    "summary",
    "note",
    "hook",
    "epigraph",
    "takeaways",
    "body",
    "oneLiner",
    "lede",
    "title",
    "subtitle",
    "label",
    "beats",
    "checklist",
    "text",
    "caption",
    "alt",
}

# Only authored metadata is linted. Parsed chapter text must keep the source voice.
ALLOWED_FILES = {
    "entities.json",
    "chapter_meta.json",
    "recap.json",
    "worldview.json",
    "manual_links.json",
    "illustrations.json",
    "timeline.json",
}

AuthoredString = tuple[str, str, str]  # path, key, text


# ---------------------------------------------------------------- text helpers


def count_hanzi(text: str) -> int:
    return len(HANZI_RE.findall(text))


def strip_tags(html: str) -> str:
    return TAG_RE.sub("", html)


def split_sentences(text: str) -> list[str]:
    return [part.strip() for part in SENTENCE_SPLIT_RE.split(text) if part.strip()]


def percentile(values: list[int], quantile: float) -> float:
    """Nearest-rank percentile."""
    if not values:
        return 0.0
    ordered = sorted(values)
    rank = max(1, math.ceil(quantile * len(ordered)))
    return float(ordered[rank - 1])


def compute_metrics(paragraphs: list[str]) -> dict[str, Any]:
    """Compute the quantitative style metrics defined in the spec."""
    texts = [text for text in paragraphs if text and text.strip()]
    sentence_lengths: list[int] = []
    for text in texts:
        for sentence in split_sentences(text):
            hanzi = count_hanzi(sentence)
            if hanzi:
                sentence_lengths.append(hanzi)

    hanzi = sum(count_hanzi(text) for text in texts)
    paragraph_count = len(texts)
    sentence_count = len(sentence_lengths)

    dialogue_paragraphs = sum(
        1 for text in texts if is_dialogue_paragraph(text)
    )

    punctuation_counts = {mark: 0 for mark in PUNCTUATION}
    for text in texts:
        for char in text:
            if char in punctuation_counts:
                punctuation_counts[char] += 1
    punctuation_total = sum(punctuation_counts.values())

    joined = "".join(texts)
    first_person = len(re.findall(r"我们|我", joined))
    third_person = len(re.findall(r"他们|她们|他|她", joined))
    if first_person > third_person:
        person = "first"
    elif third_person > first_person:
        person = "third"
    else:
        person = "mixed"

    long_sentences = sum(1 for length in sentence_lengths if length > LONG_SENTENCE_HANZI)

    return {
        "hanzi": hanzi,
        "paragraphs": paragraph_count,
        "sentences": sentence_count,
        "avgSentenceHanzi": (
            round(sum(sentence_lengths) / sentence_count, 4)
            if sentence_count
            else 0.0
        ),
        "medianSentenceHanzi": (
            float(statistics.median(sentence_lengths)) if sentence_lengths else 0.0
        ),
        "p90SentenceHanzi": percentile(sentence_lengths, 0.9),
        "dialogueParagraphRatio": (
            round(dialogue_paragraphs / paragraph_count, 4)
            if paragraph_count
            else 0.0
        ),
        "avgParagraphHanzi": (
            round(hanzi / paragraph_count, 4) if paragraph_count else 0.0
        ),
        "punctuation": {
            mark: (round(count / punctuation_total, 4) if punctuation_total else 0.0)
            for mark, count in punctuation_counts.items()
        },
        "person": person,
        "longSentenceRatio": (
            round(long_sentences / sentence_count, 4) if sentence_count else 0.0
        ),
    }


def is_dialogue_paragraph(text: str) -> bool:
    return any(mark in text for mark in DIALOGUE_MARKS) or text.lstrip().startswith("——")


def relative_drift(value: float, baseline: float) -> float | None:
    if baseline == 0:
        return None
    return round((value - baseline) / baseline, 4)


# ------------------------------------------------------------- data traversal


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


def section_hanzi_map(variant: dict[str, Any]) -> dict[str, str]:
    """Map section id -> normalized hanzi sequence, for verbatim comparison."""
    result: dict[str, str] = {}
    for section in iter_sections(variant.get("parts", [])):
        section_id = str(section.get("id", ""))
        if section_id:
            result[section_id] = "".join(HANZI_RE.findall(section_text(section)))
    return result


def chapter_variants(chapter: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return {mode: payload} for current and generalized chapter shapes."""
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


# -------------------------------------------------------------- config loading


def load_json(path: Path, errors: list[str], label: str) -> Any | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return None
    except (OSError, json.JSONDecodeError) as exc:
        errors.append(f"{label} 读取失败：{exc}")
        return None


def infer_kind(config: dict[str, Any]) -> str:
    kind = str(config.get("kind") or "").lower()
    if kind in ("import", "retelling", "creation"):
        return kind
    if config.get("sourceDir") == "chapters" and "retoldDir" not in config:
        return "creation"
    return "import"


def primary_mode(config: dict[str, Any]) -> str:
    variants = config.get("variants")
    if isinstance(variants, list):
        for variant in variants:
            if isinstance(variant, dict) and variant.get("primary") and variant.get("id"):
                return str(variant["id"])
    kind = infer_kind(config)
    if kind == "creation":
        return "retold"
    if kind == "import":
        return "original"
    return str(config.get("primaryMode") or "original")


def config_modes(config: dict[str, Any]) -> list[str]:
    variants = config.get("variants")
    if isinstance(variants, list):
        modes = [
            str(variant["id"])
            for variant in variants
            if isinstance(variant, dict) and variant.get("id")
        ]
        if modes:
            return modes
    declared = config.get("modes")
    if isinstance(declared, list) and declared:
        return [str(mode) for mode in declared]
    return [primary_mode(config)]


def variant_dir(config: dict[str, Any], mode: str, primary: str) -> str:
    variants = config.get("variants")
    if isinstance(variants, list):
        for variant in variants:
            if isinstance(variant, dict) and str(variant.get("id")) == mode:
                if variant.get("dir"):
                    return str(variant["dir"])
    if mode == primary:
        return str(config.get("sourceDir", "sources"))
    if mode == "retold":
        return str(config.get("retoldDir", "retold"))
    return str(config.get("sourceDir", "sources"))


def files_for_mode(spec: dict[str, Any], mode: str, primary: str) -> list[str]:
    variant_files = spec.get("variantFiles")
    if isinstance(variant_files, dict):
        files = variant_files.get(mode)
        if isinstance(files, list):
            return [str(name) for name in files]
    if mode == "retold" and isinstance(spec.get("retoldFiles"), list):
        return [str(name) for name in spec["retoldFiles"]]
    files = spec.get("files")
    if isinstance(files, list):
        return [str(name) for name in files]
    return []


def discover_specs(project: Path, config: dict[str, Any]) -> list[dict[str, Any]]:
    specs = config.get("chapters")
    if isinstance(specs, list) and specs:
        return [spec for spec in specs if isinstance(spec, dict)]
    source_dir = project / str(config.get("sourceDir", "sources"))
    return [
        {"id": f"ch{index}", "order": index, "files": [path.name]}
        for index, path in enumerate(
            sorted(
                path
                for path in source_dir.glob("*.md")
                if path.name.lower() != "readme.md"
            ),
            1,
        )
    ]


def markdown_paragraphs(path: Path, errors: list[str]) -> list[str]:
    try:
        raw = path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        errors.append(f"源文件读取失败 {path.name}：{exc}")
        return []
    paragraphs: list[str] = []
    for block in re.split(r"\n\s*\n", raw):
        lines = [line.rstrip() for line in block.splitlines() if line.strip()]
        if not lines or all(line.lstrip().startswith("#") for line in lines):
            continue
        if all(HR_RE.match(line) for line in lines):
            continue
        body = "".join(
            line.lstrip("> ").strip()
            for line in lines
            if not line.lstrip().startswith("#")
        )
        body = LINK_RE.sub(r"\1", body).strip()
        if body:
            paragraphs.append(body)
    return paragraphs


def synthetic_chapters(
    project: Path,
    config: dict[str, Any],
    modes: list[str],
    primary: str,
    errors: list[str],
) -> list[dict[str, Any]]:
    """Build parsed-like chapters from Markdown when build/chapters.json is absent."""
    chapters: list[dict[str, Any]] = []
    for index, spec in enumerate(discover_specs(project, config), 1):
        chapter_id = str(spec.get("id") or f"ch{index}")
        variants: dict[str, dict[str, Any]] = {}
        for mode in modes:
            directory = project / variant_dir(config, mode, primary)
            sections: list[dict[str, Any]] = []
            for file_index, name in enumerate(files_for_mode(spec, mode, primary)):
                path = directory / name
                if not path.exists():
                    continue
                paragraphs = markdown_paragraphs(path, errors)
                if not paragraphs:
                    continue
                sections.append(
                    {
                        "id": f"f{file_index}",
                        "title": "",
                        "blocks": [
                            {"type": "p", "text": paragraph}
                            for paragraph in paragraphs
                        ],
                    }
                )
            if sections:
                variants[mode] = {
                    "parts": [{"id": f"p{chapter_id}", "sections": sections}],
                    "hanzi": sum(
                        count_hanzi(section_text(section))
                        for section in sections
                    ),
                }
        if variants:
            chapters.append(
                {
                    "id": chapter_id,
                    "order": spec.get("order", index),
                    "modeNames": list(variants),
                    "variants": variants,
                }
            )
    return chapters


def ordered_mode_names(chapters: list[dict[str, Any]]) -> list[str]:
    modes: list[str] = []
    for chapter in chapters:
        for mode in chapter_variants(chapter):
            if mode not in modes:
                modes.append(mode)
    return modes


# ------------------------------------------------------------ metadata scan


def collect(value: Any, key: str, path: str, out: list[AuthoredString]) -> None:
    if key == "quote":
        return
    if isinstance(value, str):
        if key in SCAN_KEYS:
            out.append((path, key, value))
        return
    if isinstance(value, list):
        for item in value:
            collect(item, key, path, out)
        return
    if isinstance(value, dict):
        for child_key, child in value.items():
            collect(child, child_key, f"{path}.{child_key}", out)


def collect_authored_strings(
    project: Path, config: dict[str, Any], errors: list[str]
) -> list[AuthoredString]:
    strings: list[AuthoredString] = []
    content = project / "content"
    for path in sorted(content.glob("*.json")):
        if path.name not in ALLOWED_FILES:
            continue
        data = load_json(path, errors, path.name)
        if data is None:
            continue
        collect(data, "", path.name, strings)
    volumes = config.get("volumes")
    if isinstance(volumes, list) and volumes:
        collect(volumes, "volumes", "project.json.volumes", strings)
    return strings


# ------------------------------------------------------------ metric analysis


def choose_parsed_primary(config: dict[str, Any], modes: list[str]) -> str:
    preferred = primary_mode(config)
    if preferred in modes:
        return preferred
    declared = config.get("modes")
    if isinstance(declared, list):
        for mode in declared:
            if str(mode) in modes:
                return str(mode)
    return modes[0]


def aggregate_metrics(
    chapters: list[dict[str, Any]], mode: str
) -> dict[str, Any]:
    paragraphs: list[str] = []
    for chapter in chapters:
        variants = chapter_variants(chapter)
        variant = variants.get(mode)
        if variant is not None:
            paragraphs.extend(variant_paragraphs(variant))
    return compute_metrics(paragraphs)


def analyse_chapters(
    chapters: list[dict[str, Any]],
    primary: str,
    baseline: dict[str, Any],
    warnings: list[str],
) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    baseline_sentence = float(baseline.get("avgSentenceHanzi", 0.0))
    baseline_dialogue = float(baseline.get("dialogueParagraphRatio", 0.0))

    for chapter in chapters:
        chapter_id = str(chapter.get("id", ""))
        variants = chapter_variants(chapter)
        primary_variant = variants.get(primary)
        primary_sections = (
            section_hanzi_map(primary_variant) if primary_variant is not None else {}
        )
        for mode, variant in variants.items():
            if mode == primary:
                continue
            paragraphs = variant_paragraphs(variant)
            metrics = compute_metrics(paragraphs)
            drift: dict[str, float] = {}
            sentence_value = float(metrics["avgSentenceHanzi"])
            dialogue_value = float(metrics["dialogueParagraphRatio"])

            sentence_drift = relative_drift(sentence_value, baseline_sentence)
            if sentence_drift is not None:
                drift["avgSentenceHanzi"] = sentence_drift
                if abs(sentence_drift) > SENTENCE_DRIFT_LIMIT:
                    warnings.append(
                        f"{chapter_id}[{mode}]：平均句长漂移 {sentence_drift:+.0%}"
                        f"（{sentence_value:.1f} vs 基线 {baseline_sentence:.1f}）"
                    )

            dialogue_drift = relative_drift(dialogue_value, baseline_dialogue)
            if dialogue_drift is not None:
                drift["dialogueParagraphRatio"] = dialogue_drift
                if (
                    abs(dialogue_drift) > DIALOGUE_DRIFT_LIMIT
                    and abs(dialogue_value - baseline_dialogue) > DIALOGUE_ABS_LIMIT
                ):
                    warnings.append(
                        f"{chapter_id}[{mode}]：对话段落比例漂移 {dialogue_drift:+.0%}"
                        f"（{dialogue_value:.2f} vs 基线 {baseline_dialogue:.2f}）"
                    )
            elif dialogue_value > DIALOGUE_ABS_LIMIT:
                # Baseline has no dialogue; any meaningful dialogue is an infinite drift.
                warnings.append(
                    f"{chapter_id}[{mode}]：对话段落比例 {dialogue_value:.2f}，"
                    f"基线为 {baseline_dialogue:.2f}"
                )

            verbatim = verbatim_section_ratio(primary_sections, variant)
            if verbatim is not None and verbatim > VERBATIM_SECTION_LIMIT:
                warnings.append(
                    f"{chapter_id}[{mode}]：与原文逐字相同的小节占比 "
                    f"{verbatim:.0%}，疑似未复述"
                )

            entries.append(
                {
                    "chapter": chapter_id,
                    "mode": mode,
                    "avgSentenceHanzi": metrics["avgSentenceHanzi"],
                    "dialogueParagraphRatio": metrics["dialogueParagraphRatio"],
                    "drift": drift,
                }
            )
    return entries


def verbatim_section_ratio(
    primary_sections: dict[str, str], variant: dict[str, Any]
) -> float | None:
    if not primary_sections:
        return None
    other_sections = section_hanzi_map(variant)
    compared = 0
    identical = 0
    for section_id, primary_text in primary_sections.items():
        other_text = other_sections.get(section_id)
        if not primary_text or not other_text:
            continue
        compared += 1
        if primary_text == other_text:
            identical += 1
    if compared == 0:
        return None
    return identical / compared


def analyse_metadata(
    strings: list[AuthoredString],
    baseline: dict[str, Any],
    warnings: list[str],
) -> dict[str, Any]:
    texts = [text for _, _, text in strings]
    metrics = compute_metrics(texts)
    if not texts:
        return {"strings": 0, "metrics": metrics}

    baseline_sentence = float(baseline.get("avgSentenceHanzi", 0.0))
    metadata_sentence = float(metrics["avgSentenceHanzi"])
    drift = relative_drift(metadata_sentence, baseline_sentence)
    if drift is not None and abs(drift) > META_SENTENCE_DRIFT_LIMIT:
        warnings.append(
            f"元数据平均句长漂移 {drift:+.0%}"
            f"（{metadata_sentence:.1f} vs 基线 {baseline_sentence:.1f}）"
        )
    if float(metrics["longSentenceRatio"]) > META_LONG_SENTENCE_LIMIT:
        warnings.append(
            "元数据长句比例 "
            f"{metrics['longSentenceRatio']:.0%}（阈值 30%）"
        )
    return {"strings": len(texts), "metrics": metrics}


def regex_warnings(strings: list[AuthoredString]) -> list[str]:
    warnings: list[str] = []
    for path, key, text in strings:
        for pattern, label in BANNED:
            if pattern.search(text):
                warnings.append(f"[硬] {label} · {path} · {key}：{text[:100]}")
        for pattern, label in SOFT:
            if pattern.search(text):
                warnings.append(f"[软] {label} · {path} · {key}：{text[:100]}")
    return warnings


# --------------------------------------------------------------------- output


def format_metrics(metrics: dict[str, Any]) -> str:
    return (
        f"汉字 {metrics['hanzi']} · 段落 {metrics['paragraphs']} · "
        f"句子 {metrics['sentences']} · 平均句长 {metrics['avgSentenceHanzi']:.1f} · "
        f"中位句长 {metrics['medianSentenceHanzi']:.1f} · "
        f"P90 {metrics['p90SentenceHanzi']:.1f} · "
        f"对话段落比 {metrics['dialogueParagraphRatio']:.2f} · "
        f"长句比 {metrics['longSentenceRatio']:.0%} · 人称 {metrics['person']}"
    )


def print_human(
    report: dict[str, Any],
    string_count: int,
    content: Path,
    no_metrics: bool,
) -> None:
    print(f"扫描 {string_count} 条作者元数据：{content}")
    if not no_metrics:
        baseline = report.get("baseline")
        if baseline:
            print(
                f"\n基线（{baseline['mode']}）："
                f"{format_metrics(baseline['metrics'])}"
            )
        else:
            print("\n基线：不可用")
        modes = report.get("modes", {})
        if modes:
            print("\n各模式指标：")
            for mode, metrics in modes.items():
                print(f"  {mode}: {format_metrics(metrics)}")
        chapters = report.get("chapters", [])
        if chapters:
            print("\n章节漂移：")
            for entry in chapters:
                parts = [
                    f"{entry['chapter']}[{entry['mode']}] "
                    f"平均句长 {entry['avgSentenceHanzi']:.1f}",
                    f"对话比 {entry['dialogueParagraphRatio']:.2f}",
                ]
                for name, value in entry.get("drift", {}).items():
                    parts.append(f"{name} {value:+.0%}")
                print("  " + " · ".join(parts))
        metadata = report.get("metadata") or {}
        if metadata.get("strings"):
            print(
                f"\n元数据：{metadata['strings']} 条 · "
                f"{format_metrics(metadata['metrics'])}"
            )

    errors = report.get("errors", [])
    warnings = report.get("warnings", [])
    if errors:
        print(f"\n错误 {len(errors)} 项：")
        for item in errors:
            print(f"  - {item}")
    if warnings:
        print(f"\n问题 {len(warnings)} 项：")
        for item in warnings[:80]:
            print(f"  - {item}")
        if len(warnings) > 80:
            print(f"  ... 另有 {len(warnings) - 80} 项")
    if not errors and not warnings:
        print("\n未发现问题。")


def write_report(project: Path, report: dict[str, Any], errors: list[str]) -> None:
    build_dir = project / "build"
    try:
        build_dir.mkdir(parents=True, exist_ok=True)
        (build_dir / "style_report.json").write_text(
            json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
        )
    except OSError as exc:
        errors.append(f"无法写入 build/style_report.json：{exc}")


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
            "usage: style_lint.py <project-dir> [--strict] [--json] [--no-metrics]",
            file=sys.stderr,
        )
        return 2
    project = Path(argv[0]).resolve()
    flags = argv[1:]
    strict = "--strict" in flags
    json_output = "--json" in flags
    no_metrics = "--no-metrics" in flags

    if not project.is_dir():
        return fail_missing_project(
            project, json_output, f"项目目录不存在：{project}"
        )

    errors: list[str] = []
    warnings: list[str] = []

    config = load_json(project / "project.json", errors, "project.json")
    if not isinstance(config, dict):
        config = {}

    strings = collect_authored_strings(project, config, errors)
    warnings.extend(regex_warnings(strings))

    if no_metrics:
        report: dict[str, Any] = {
            "baseline": None,
            "modes": {},
            "chapters": [],
            "metadata": {},
            "errors": errors,
            "warnings": warnings,
        }
        write_report(project, report, errors)
        if json_output:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print_human(report, len(strings), project / "content", no_metrics)
        return exit_code(errors, warnings, strict)

    build = load_json(project / "build" / "chapters.json", errors, "build/chapters.json")
    if isinstance(build, dict):
        build = build.get("chapters")
    chapters: list[dict[str, Any]] = [
        chapter for chapter in (build or []) if isinstance(chapter, dict)
    ]
    if not chapters:
        modes = config_modes(config)
        chapters = synthetic_chapters(
            project, config, modes, primary_mode(config), errors
        )
        if not chapters:
            warnings.append(
                "没有可用的章节数据：未找到 build/chapters.json，也未能从源文读取正文"
            )

    modes = ordered_mode_names(chapters)
    if not modes:
        modes = config_modes(config)
    primary = choose_parsed_primary(config, modes) if modes else primary_mode(config)

    modes_report = {
        mode: aggregate_metrics(chapters, mode) for mode in modes
    }
    baseline_metrics = modes_report.get(primary, compute_metrics([]))

    chapter_entries = analyse_chapters(chapters, primary, baseline_metrics, warnings)
    metadata_report = analyse_metadata(strings, baseline_metrics, warnings)

    report = {
        "baseline": {"mode": primary, "metrics": baseline_metrics},
        "modes": modes_report,
        "chapters": chapter_entries,
        "metadata": metadata_report,
        "errors": errors,
        "warnings": warnings,
    }
    write_report(project, report, errors)

    if json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_human(report, len(strings), project / "content", no_metrics)
    return exit_code(errors, warnings, strict)


def force_utf8_stdout() -> None:
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except (AttributeError, OSError, ValueError):
        pass


def exit_code(errors: list[str], warnings: list[str], strict: bool) -> int:
    if errors:
        return 1
    if strict and warnings:
        return 1
    return 0


def fail_missing_project(
    project: Path, json_output: bool, message: str
) -> int:
    report = {
        "baseline": None,
        "modes": {},
        "chapters": [],
        "metadata": {},
        "errors": [message],
        "warnings": [],
    }
    if json_output:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(message, file=sys.stderr)
    return 1


if __name__ == "__main__":
    force_utf8_stdout()
    sys.exit(main(sys.argv[1:]))
