#!/usr/bin/env python3
"""Story Forge — ingest source files into Markdown chapters.

Usage:
    python ingest_sources.py <project-dir> <source-path> \
        [--to DIR] [--dry-run] [--force] [--update-project] \
        [--extract-images] [--json]

Supported inputs: txt/text, md, epub, docx, html/htm, directories, and
pdf when the optional ``pypdf`` package is installed.

The tool only normalizes headings, paragraph spacing, repeated page
headers/footers, page numbers and trailing whitespace. Prose is never
rewritten. Every run plans its writes first: existing target files abort
the whole operation unless ``--force`` is given.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import posixpath
import re
import sys
import zipfile
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
import xml.etree.ElementTree as ET

HANZI_RE = re.compile(r"[一-鿿]")
MAX_TITLE_LEN = 60
TITLE_ENDINGS = "。！？；：，,"
REPORT_RELATIVE = Path("build") / "ingest_report.json"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".gif", ".svg", ".webp", ".bmp"}
SUPPORTED_EXTS = {
    ".txt": "txt",
    ".text": "txt",
    ".md": "md",
    ".markdown": "md",
    ".epub": "epub",
    ".docx": "docx",
    ".html": "html",
    ".htm": "html",
    ".pdf": "pdf",
}

# Chapter-title patterns. The spec allows Chinese, English and numeric forms.
CHINESE_CHAPTER_RE = re.compile(
    r"^第\s*[0-9零〇一二三四五六七八九十百千万两]+\s*[章回节卷部篇集]"
    r"(?:[\s:：·、.\-—].*)?$"
)
SPECIAL_CHAPTER_RE = re.compile(
    r"^(?:序章|序幕|楔子|引子|尾声|终章|后记|番外[0-9零〇一二三四五六七八九十百]*|序)"
    r"(?:[\s:：·、.\-—].*)?$"
)
ENGLISH_CHAPTER_RE = re.compile(
    r"^(?:(?:chapter|part)\s+(?:\d+|[ivxlcdm]+)\b.*"
    r"|prologue(?:\b.*)?|epilogue(?:\b.*)?)$",
    re.IGNORECASE,
)
NUMERIC_CHAPTER_RE = re.compile(
    r"^(?:\d{1,4}[.．、]?|[一二三四五六七八九十百]+[、.])$"
)
ATX_HEADING_RE = re.compile(r"^(#{1,6})\s+(.*?)\s*#*\s*$")
BARE_NUMBER_RE = re.compile(r"^\d{1,4}$")

NONBARE_PAGE_RES = (
    re.compile(r"^\s*[-–—]+\s*\d{1,4}\s*[-–—]*\s*$"),
    re.compile(r"^\s*\d{1,4}\s*[-–—]+\s*$"),
    re.compile(r"^\s*第\s*\d+\s*页(?:\s*[／/]?\s*共\s*\d+\s*页)?\s*$"),
    re.compile(r"^\s*(?:page|p\.)\s*\d+(?:\s*(?:/|of)\s*\d+)?\s*$", re.IGNORECASE),
    re.compile(r"^\s*\d{1,4}\s*[／/]\s*\d{1,4}\s*$"),
    re.compile(r"^\s*共\s*\d+\s*页\s*$"),
)

SKIP_HTML_TAGS = {"script", "style", "nav", "header", "footer", "noscript"}
BLOCK_HTML_TAGS = {
    "p", "div", "section", "article", "main", "aside", "li", "blockquote",
    "td", "th", "dd", "dt", "pre", "figure", "figcaption",
}
HEADING_TAG_RE = re.compile(r"^h([1-6])$")

DOCX_NS = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
OPF_NS = "{http://www.idpf.org/2007/opf}"
NCX_NS = "{http://www.daisy.org/z3986/2005/ncx/}"
DC_NS = "{http://purl.org/dc/elements/1.1/}"


class IngestError(Exception):
    """A user-facing ingestion failure."""


@dataclass
class Block:
    kind: str  # "heading" or "paragraph"
    text: str
    level: int = 0


@dataclass
class ParsedChapter:
    title: str
    blocks: list[Block]
    confidence: str = "high"


@dataclass
class ParsedImage:
    data: bytes
    ext: str
    origin: str


@dataclass
class ParseResult:
    format: str
    chapters: list[ParsedChapter]
    encoding: str | None = None
    warnings: list[str] = field(default_factory=list)
    input_hanzi: int = 0
    images: list[ParsedImage] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Small text helpers
# ---------------------------------------------------------------------------

def count_hanzi(text: str) -> int:
    return len(HANZI_RE.findall(text))


def normalize_title(text: str) -> str:
    text = text.strip()
    text = re.sub(r"^#{1,6}\s*", "", text)
    text = re.sub(r"\s+#+\s*$", "", text)
    text = re.sub(r"[ \t　]+", " ", text)
    return text.strip()


def is_heading_candidate(line: str) -> bool:
    text = line.strip()
    if not text or len(text) > MAX_TITLE_LEN:
        return False
    if text[-1] in TITLE_ENDINGS:
        return False
    return bool(
        CHINESE_CHAPTER_RE.match(text)
        or SPECIAL_CHAPTER_RE.match(text)
        or ENGLISH_CHAPTER_RE.match(text)
        or NUMERIC_CHAPTER_RE.match(text)
    )


def block_has_text(blocks: list[Block]) -> bool:
    return any(block.text.strip() for block in blocks)


def paragraph_count(chapter: ParsedChapter) -> int:
    return sum(
        1
        for block in chapter.blocks
        if block.kind == "paragraph" and block.text.strip()
    )


# ---------------------------------------------------------------------------
# Encoding detection
# ---------------------------------------------------------------------------

def decode_bytes(data: bytes) -> tuple[str, str, list[str]]:
    """Decode bytes, trying BOM, utf-8, gb18030, utf-16 and big5 in order."""
    warnings: list[str] = []
    if data.startswith(b"\xff\xfe\x00\x00") or data.startswith(b"\x00\x00\xfe\xff"):
        return data.decode("utf-32"), "utf-32", warnings
    if data.startswith(b"\xef\xbb\xbf"):
        return data[3:].decode("utf-8", errors="strict"), "utf-8-sig", warnings
    if data.startswith((b"\xff\xfe", b"\xfe\xff")):
        return data.decode("utf-16"), "utf-16", warnings

    for encoding in ("utf-8", "gb18030", "utf-16", "big5"):
        try:
            text = data.decode(encoding, errors="strict")
        except (UnicodeDecodeError, LookupError):
            continue
        if encoding == "utf-16" and data.count(b"\x00") * 8 < len(data):
            # utf-16 without a BOM is only plausible when NUL bytes are common.
            continue
        return text, encoding, warnings

    text = data.decode("utf-8", errors="replace")
    replaced = text.count("�")
    warnings.append(
        f"无法可靠识别文本编码，已用 utf-8 解码并替换了 {replaced} 个不可解码字节；"
        "请确认源文件编码。"
    )
    return text, "utf-8", warnings


# ---------------------------------------------------------------------------
# Page header / footer / page number cleanup
# ---------------------------------------------------------------------------

def _page_number_flags(lines: list[str]) -> list[bool]:
    stripped = [line.strip() for line in lines]
    counts = Counter(item for item in stripped if item)
    flags = [False] * len(stripped)
    for index, text in enumerate(stripped):
        if text and any(pattern.match(text) for pattern in NONBARE_PAGE_RES):
            flags[index] = True
    for index, text in enumerate(stripped):
        if not text or not BARE_NUMBER_RE.fullmatch(text):
            continue
        if counts[text] >= 2:
            flags[index] = True
        elif index > 0 and flags[index - 1]:
            flags[index] = True
        elif index + 1 < len(flags) and flags[index + 1]:
            flags[index] = True
    return flags


def _repeated_line_keys(lines: list[str]) -> set[str]:
    """Find running headers/footers: repeated short lines across the document."""
    positions: dict[str, list[int]] = defaultdict(list)
    for index, line in enumerate(lines):
        text = line.strip()
        if text:
            positions[text].append(index)
    total = max(1, len(lines))
    repeated: set[str] = set()
    for text, found in positions.items():
        if len(found) < 3 or not (3 <= len(text) <= 40):
            continue
        if is_heading_candidate(text):
            continue
        if text[-1] in "。！？!?…；;":
            continue
        if found[-1] - found[0] < total * 0.4:
            continue
        repeated.add(text)
    return repeated


def clean_plain_lines(lines: list[str]) -> tuple[list[str], list[str], int, int]:
    """Remove page numbers and repeated headers/footers; tidy blank runs."""
    lines = [line.rstrip() for line in lines]
    repeated = _repeated_line_keys(lines)
    page_flags = _page_number_flags(lines)
    kept: list[str] = []
    removed = 0
    removed_hanzi = 0
    samples: list[str] = []
    for index, line in enumerate(lines):
        text = line.strip()
        if text and (text in repeated or page_flags[index]):
            removed += 1
            removed_hanzi += count_hanzi(text)
            if len(samples) < 3:
                samples.append(text)
            continue
        kept.append(line)

    collapsed: list[str] = []
    previous_blank = False
    for line in kept:
        if line.strip():
            collapsed.append(line)
            previous_blank = False
        elif not previous_blank:
            collapsed.append("")
            previous_blank = True

    warnings: list[str] = []
    if removed:
        sample = "、".join(samples)
        warnings.append(
            f"已移除 {removed} 行重复页眉/页脚或页码"
            + (f"（示例：{sample}）。" if sample else "。")
        )
    return collapsed, warnings, removed, removed_hanzi


# ---------------------------------------------------------------------------
# Plain-text / Markdown chapter segmentation
# ---------------------------------------------------------------------------

def segment_plain_lines(lines: list[str], fallback_title: str) -> list[ParsedChapter]:
    headings = [
        index for index, line in enumerate(lines) if is_heading_candidate(line)
    ]
    if len(headings) >= 2:
        chapters: list[ParsedChapter] = []
        preface = [line.strip() for line in lines[: headings[0]] if line.strip()]
        if preface:
            chapters.append(
                ParsedChapter(
                    "前言",
                    [Block("paragraph", text) for text in preface],
                    "medium",
                )
            )
        for position, start in enumerate(headings):
            end = headings[position + 1] if position + 1 < len(headings) else len(lines)
            title = normalize_title(lines[start])
            body = [
                Block("paragraph", line.strip())
                for line in lines[start + 1:end]
                if line.strip()
            ]
            chapters.append(ParsedChapter(title, body, "high"))
        return chapters

    title = normalize_title(lines[headings[0]]) if headings else fallback_title
    single: list[Block] = []
    for index, line in enumerate(lines):
        if headings and index == headings[0]:
            continue
        if line.strip():
            single.append(Block("paragraph", line.strip()))
    return [ParsedChapter(title or fallback_title, single, "low")]


def parse_markdown_blocks(text: str) -> list[Block]:
    blocks: list[Block] = []
    buffer: list[str] = []

    def flush() -> None:
        if not buffer:
            return
        joined = "\n".join(line.rstrip() for line in buffer).strip("\n")
        buffer.clear()
        if joined.strip():
            blocks.append(Block("paragraph", joined))

    for line in text.splitlines():
        match = ATX_HEADING_RE.match(line)
        if match:
            flush()
            title = normalize_title(match.group(2))
            if title:
                blocks.append(Block("heading", title, len(match.group(1))))
            continue
        if not line.strip():
            flush()
            continue
        buffer.append(line)
    flush()
    return blocks


def pick_split_level(blocks: list[Block]) -> int | None:
    counts = Counter(block.level for block in blocks if block.kind == "heading")
    for level in sorted(counts):
        if counts[level] >= 2:
            return level
    return None


def normalize_body_blocks(blocks: list[Block], split_level: int) -> list[Block]:
    result: list[Block] = []
    for block in blocks:
        if block.kind == "heading":
            result.append(
                Block("heading", block.text, max(2, block.level - split_level + 1))
            )
        elif block.text.strip():
            result.append(block)
    return result


def choose_title_block(blocks: list[Block]) -> tuple[str, int | None]:
    for index, block in enumerate(blocks):
        if block.kind == "heading" and block.text.strip():
            return block.text.strip(), index
    for index, block in enumerate(blocks):
        if (
            block.kind == "paragraph"
            and "\n" not in block.text
            and is_heading_candidate(block.text)
        ):
            return normalize_title(block.text), index
    return "", None


def single_chapter(blocks: list[Block], fallback_title: str) -> ParsedChapter:
    title, index = choose_title_block(blocks)
    body = [block for position, block in enumerate(blocks) if position != index]
    return ParsedChapter(title or fallback_title, body, "low")


def split_blocks_by_level(
    blocks: list[Block], level: int, fallback_title: str
) -> list[ParsedChapter]:
    starts = [
        index
        for index, block in enumerate(blocks)
        if block.kind == "heading" and block.level == level
    ]
    if len(starts) < 2:
        return [single_chapter(blocks, fallback_title)]

    chapters: list[ParsedChapter] = []
    preface = blocks[: starts[0]]
    preface_has_paragraph = any(
        block.kind == "paragraph" and block.text.strip() for block in preface
    )
    if preface_has_paragraph:
        chapters.append(
            ParsedChapter("前言", normalize_body_blocks(preface, level), "medium")
        )
    for position, start in enumerate(starts):
        end = starts[position + 1] if position + 1 < len(starts) else len(blocks)
        title = blocks[start].text.strip() or fallback_title
        body = normalize_body_blocks(blocks[start + 1:end], level)
        if position == 0 and preface and not preface_has_paragraph:
            # Keep a book-title heading that sits above the chapter level.
            body = normalize_body_blocks(preface, level) + body
        chapters.append(ParsedChapter(title, body, "high"))
    return chapters


def chapters_from_blocks(blocks: list[Block], fallback_title: str) -> list[ParsedChapter]:
    level = pick_split_level(blocks)
    if level is not None:
        return split_blocks_by_level(blocks, level, fallback_title)
    return [single_chapter(blocks, fallback_title)]


def paragraphs_from_markdown_chapters(
    blocks: list[Block], fallback_title: str
) -> list[ParsedChapter]:
    level = pick_split_level(blocks)
    if level is not None:
        return split_blocks_by_level(blocks, level, fallback_title)
    plain_starts = {
        index
        for index, block in enumerate(blocks)
        if block.kind == "paragraph"
        and "\n" not in block.text
        and is_heading_candidate(block.text)
    }
    if len(plain_starts) >= 2:
        converted = [
            Block("heading", normalize_title(block.text), 1)
            if index in plain_starts
            else block
            for index, block in enumerate(blocks)
        ]
        return split_blocks_by_level(converted, 1, fallback_title)
    return [single_chapter(blocks, fallback_title)]


# ---------------------------------------------------------------------------
# Parsers: plain text and Markdown
# ---------------------------------------------------------------------------

def parse_text_file(path: Path) -> ParseResult:
    text, encoding, warnings = decode_bytes(path.read_bytes())
    if not text.strip():
        raise IngestError(f"no readable text in {path}")
    raw_hanzi = count_hanzi(text)
    lines, clean_warnings, _removed, _removed_hanzi = clean_plain_lines(
        text.splitlines()
    )
    warnings.extend(clean_warnings)
    chapters = segment_plain_lines(lines, path.stem)
    if len(chapters) == 1:
        warnings.append(
            "章节标题不足 2 个，整份文本作为一章处理（confidence: low）。"
        )
    return ParseResult("txt", chapters, encoding, warnings, raw_hanzi)


def parse_markdown_file(path: Path) -> ParseResult:
    text, encoding, warnings = decode_bytes(path.read_bytes())
    if not text.strip():
        raise IngestError(f"no readable text in {path}")
    chapters = paragraphs_from_markdown_chapters(
        parse_markdown_blocks(text), path.stem
    )
    if len(chapters) == 1:
        warnings.append(
            "章节标题不足 2 个，整份文本作为一章处理（confidence: low）。"
        )
    return ParseResult("md", chapters, encoding, warnings, count_hanzi(text))


# ---------------------------------------------------------------------------
# Parser: HTML
# ---------------------------------------------------------------------------

class StoryHTMLParser(HTMLParser):
    """Extract headings and paragraphs, skipping navigation/chrome content."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[Block] = []
        self.doc_title = ""
        self._buffer: list[str] = []
        self._skip_depth = 0
        self._heading_level = 0
        self._in_title = False
        self._pre_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = tag.lower()
        if name == "title":
            self._in_title = True
            return
        if name in SKIP_HTML_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        heading = HEADING_TAG_RE.match(name)
        if heading:
            self._flush_paragraph()
            self._heading_level = int(heading.group(1))
            return
        if name == "br":
            self._buffer.append("\n")
            return
        if name in BLOCK_HTML_TAGS:
            self._flush_paragraph()
            if name == "pre":
                self._pre_depth += 1

    def handle_startendtag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_endtag(self, tag: str) -> None:
        name = tag.lower()
        if name in SKIP_HTML_TAGS:
            if self._skip_depth:
                self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if name == "title":
            self._in_title = False
            return
        if HEADING_TAG_RE.match(name):
            text = self._take(flatten=True)
            if text:
                self.blocks.append(
                    Block("heading", text, self._heading_level or 1)
                )
            self._heading_level = 0
            return
        if name in BLOCK_HTML_TAGS:
            self._flush_paragraph()
            if name == "pre" and self._pre_depth:
                self._pre_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._in_title:
            self.doc_title += data
            return
        if self._skip_depth:
            return
        if data.strip() or self._buffer:
            self._buffer.append(data)

    def _take(self, flatten: bool = False) -> str:
        raw = "".join(self._buffer)
        self._buffer.clear()
        if flatten:
            return re.sub(r"\s+", " ", raw).strip()
        if self._pre_depth or "\n" in raw:
            return "\n".join(
                line.strip() for line in raw.splitlines() if line.strip()
            )
        return re.sub(r"\s+", " ", raw).strip()

    def _flush_paragraph(self) -> None:
        text = self._take()
        if text:
            self.blocks.append(Block("paragraph", text))


def html_to_blocks(text: str) -> tuple[list[Block], str]:
    parser = StoryHTMLParser()
    parser.feed(text)
    parser.close()
    parser._flush_paragraph()
    return parser.blocks, re.sub(r"\s+", " ", parser.doc_title).strip()


def parse_html_bytes(
    data: bytes, fallback_title: str, fmt: str = "html"
) -> ParseResult:
    text, encoding, warnings = decode_bytes(data)
    blocks, doc_title = html_to_blocks(text)
    if not block_has_text(blocks):
        raise IngestError(f"no readable text in {fallback_title}")
    chapters = chapters_from_blocks(blocks, doc_title or fallback_title)
    if len(chapters) == 1:
        warnings.append(
            "章节标题不足 2 个，整份文本作为一章处理（confidence: low）。"
        )
    return ParseResult(fmt, chapters, encoding, warnings, count_hanzi(text))


def parse_html_file(path: Path) -> ParseResult:
    return parse_html_bytes(path.read_bytes(), path.stem, "html")


# ---------------------------------------------------------------------------
# Parser: DOCX
# ---------------------------------------------------------------------------

def _docx_style_map(archive: zipfile.ZipFile) -> dict[str, str]:
    styles: dict[str, str] = {}
    if "word/styles.xml" not in archive.namelist():
        return styles
    root = ET.fromstring(archive.read("word/styles.xml"))
    for style in root.iter(f"{DOCX_NS}style"):
        style_id = style.get(f"{DOCX_NS}styleId") or ""
        name_el = style.find(f"{DOCX_NS}name")
        name = name_el.get(f"{DOCX_NS}val", "") if name_el is not None else ""
        styles[style_id] = name or style_id
    return styles


def _docx_heading_level(style_value: str, style_map: dict[str, str]) -> int:
    candidates = {style_value, style_map.get(style_value, "")}
    for value in candidates:
        normalized = (
            (value or "")
            .strip()
            .replace(" ", "")
            .replace("　", "")
            .replace("-", "")
            .lower()
        )
        match = re.match(r"^(?:heading|标题)([1-6])$", normalized)
        if match:
            return int(match.group(1))
        if re.fullmatch(r"[1-6]", normalized):
            return int(normalized)
    return 0


def _docx_paragraph_text(paragraph: ET.Element) -> str:
    parts: list[str] = []
    for node in paragraph.iter():
        if node.tag == f"{DOCX_NS}t":
            parts.append(node.text or "")
        elif node.tag == f"{DOCX_NS}tab":
            parts.append("\t")
        elif node.tag in (f"{DOCX_NS}br", f"{DOCX_NS}cr"):
            parts.append("\n")
    return "".join(parts).strip()


def _docx_paragraph_level(paragraph: ET.Element, style_map: dict[str, str]) -> int:
    properties = paragraph.find(f"{DOCX_NS}pPr")
    if properties is None:
        return 0
    style = properties.find(f"{DOCX_NS}pStyle")
    if style is None:
        return 0
    return _docx_heading_level(style.get(f"{DOCX_NS}val", ""), style_map)


def _docx_core_title(archive: zipfile.ZipFile) -> str:
    if "docProps/core.xml" not in archive.namelist():
        return ""
    try:
        root = ET.fromstring(archive.read("docProps/core.xml"))
    except ET.ParseError:
        return ""
    title = root.find(f"{DC_NS}title")
    return (title.text or "").strip() if title is not None else ""


def parse_docx_file(path: Path) -> ParseResult:
    try:
        with zipfile.ZipFile(path) as archive:
            if "word/document.xml" not in archive.namelist():
                raise IngestError(f"invalid docx (missing word/document.xml): {path}")
            style_map = _docx_style_map(archive)
            root = ET.fromstring(archive.read("word/document.xml"))
            core_title = _docx_core_title(archive)
    except zipfile.BadZipFile as exc:
        raise IngestError(f"invalid docx archive: {path}") from exc
    except ET.ParseError as exc:
        raise IngestError(f"invalid docx XML: {path}") from exc

    body = root.find(f"{DOCX_NS}body")
    if body is None:
        raise IngestError(f"invalid docx (missing body): {path}")

    blocks: list[Block] = []
    paragraphs: list[ET.Element] = []
    for child in body:
        if child.tag == f"{DOCX_NS}p":
            paragraphs.append(child)
        elif child.tag == f"{DOCX_NS}tbl":
            paragraphs.extend(child.iter(f"{DOCX_NS}p"))

    for paragraph in paragraphs:
        text = _docx_paragraph_text(paragraph)
        if not text:
            continue
        level = _docx_paragraph_level(paragraph, style_map)
        if level:
            blocks.append(Block("heading", text, level))
        else:
            blocks.append(Block("paragraph", text))

    if not block_has_text(blocks):
        raise IngestError(f"no readable text in {path}")

    warnings: list[str] = []
    level = pick_split_level(blocks)
    if level is not None:
        chapters = split_blocks_by_level(blocks, level, path.stem)
    else:
        lines: list[str] = []
        for block in blocks:
            lines.extend(block.text.splitlines() or [""])
        chapters = segment_plain_lines(lines, core_title or path.stem)
        has_styled_heading = any(block.kind == "heading" for block in blocks)
        if len(chapters) >= 2 and not has_styled_heading:
            warnings.append(
                "未找到 Word 标题样式，已回退到章节标题正则识别。"
            )
    if len(chapters) == 1:
        warnings.append(
            "章节标题不足 2 个，整份文本作为一章处理（confidence: low）。"
        )
    input_hanzi = sum(count_hanzi(block.text) for block in blocks)
    return ParseResult("docx", chapters, None, warnings, input_hanzi)


# ---------------------------------------------------------------------------
# Parser: EPUB
# ---------------------------------------------------------------------------

@dataclass
class TocEntry:
    path: str
    fragment: str
    title: str


@dataclass
class SpineDoc:
    path: str
    blocks: list[Block]
    doc_title: str


class NavHTMLParser(HTMLParser):
    """Collect anchors from the EPUB nav document's first toc nav."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.entries: list[tuple[str, str]] = []
        self._nav_depth = 0
        self._anchor_href: str | None = None
        self._buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        name = tag.lower()
        values = {key: value or "" for key, value in attrs}
        if name == "nav":
            nav_type = (values.get("epub:type") or values.get("type") or "").lower()
            if "toc" in nav_type or self._nav_depth == 0:
                self._nav_depth += 1
        elif name == "a" and self._nav_depth:
            self._anchor_href = values.get("href")
            self._buffer = []

    def handle_endtag(self, tag: str) -> None:
        name = tag.lower()
        if name == "a" and self._anchor_href is not None:
            title = re.sub(r"\s+", " ", "".join(self._buffer)).strip()
            if title and self._anchor_href:
                self.entries.append((self._anchor_href, title))
            self._anchor_href = None
            self._buffer = []
        elif name == "nav" and self._nav_depth:
            self._nav_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._anchor_href is not None:
            self._buffer.append(data)


def _resolve_epub_href(base_file: str, href: str) -> tuple[str, str]:
    href = href.split("?", 1)[0]
    fragment = ""
    if "#" in href:
        href, fragment = href.split("#", 1)
    resolved = posixpath.normpath(
        posixpath.join(posixpath.dirname(base_file), href)
    )
    return resolved, fragment


def _epub_nav_entries(
    archive: zipfile.ZipFile, nav_path: str
) -> list[TocEntry]:
    if nav_path not in archive.namelist():
        return []
    text, _encoding, _warnings = decode_bytes(archive.read(nav_path))
    parser = NavHTMLParser()
    parser.feed(text)
    parser.close()
    entries: list[TocEntry] = []
    for href, title in parser.entries:
        path, fragment = _resolve_epub_href(nav_path, href)
        entries.append(TocEntry(path, fragment, title))
    return entries


def _epub_ncx_entries(
    archive: zipfile.ZipFile, ncx_path: str
) -> list[TocEntry]:
    if ncx_path not in archive.namelist():
        return []
    try:
        root = ET.fromstring(archive.read(ncx_path))
    except ET.ParseError:
        return []
    entries: list[TocEntry] = []
    for nav_point in root.iter(f"{NCX_NS}navPoint"):
        label = nav_point.find(f"{NCX_NS}navLabel/{NCX_NS}text")
        content = nav_point.find(f"{NCX_NS}content")
        if content is None:
            continue
        src = content.get("src", "")
        title = (label.text or "").strip() if label is not None else ""
        if not src:
            continue
        path, fragment = _resolve_epub_href(ncx_path, src)
        entries.append(TocEntry(path, fragment, title))
    return entries


def _read_epub_toc(
    archive: zipfile.ZipFile,
    manifest: dict[str, dict[str, str]],
    opf_path: str,
    toc_id: str,
) -> list[TocEntry]:
    nav_item = next(
        (
            item
            for item in manifest.values()
            if "nav" in (item.get("properties") or "").split()
        ),
        None,
    )
    if nav_item is not None:
        nav_path, _fragment = _resolve_epub_href(opf_path, nav_item["href"])
        entries = _epub_nav_entries(archive, nav_path)
        if entries:
            return entries

    ncx_item = manifest.get(toc_id)
    if ncx_item is None:
        ncx_item = next(
            (
                item
                for item in manifest.values()
                if item.get("media-type") == "application/x-dtbncx+xml"
            ),
            None,
        )
    if ncx_item is None:
        return []
    ncx_path, _fragment = _resolve_epub_href(opf_path, ncx_item["href"])
    return _epub_ncx_entries(archive, ncx_path)


def _strip_leading_toc_heading(blocks: list[Block], title: str) -> list[Block]:
    if not blocks:
        return blocks
    first = blocks[0]
    if first.kind == "heading" and normalize_title(first.text) == normalize_title(title):
        return blocks[1:]
    return blocks


def _merge_continuation(
    chapters: list[ParsedChapter], blocks: list[Block], split_level: int | None
) -> None:
    if chapters:
        transformed = normalize_body_blocks(blocks, split_level or 1)
        chapters[-1].blocks.extend(transformed)


def parse_epub_file(path: Path, extract_images: bool = False) -> ParseResult:
    warnings: list[str] = []
    images: list[ParsedImage] = []
    try:
        with zipfile.ZipFile(path) as archive:
            names = set(archive.namelist())
            if "META-INF/container.xml" not in names:
                raise IngestError(f"invalid epub (missing META-INF/container.xml): {path}")
            container = ET.fromstring(archive.read("META-INF/container.xml"))
            rootfile = container.find(".//{*}rootfile")
            if rootfile is None:
                raise IngestError(f"invalid epub (no rootfile): {path}")
            opf_path = rootfile.get("full-path", "")
            if not opf_path or opf_path not in names:
                raise IngestError(f"invalid epub (missing OPF {opf_path}): {path}")

            package = ET.fromstring(archive.read(opf_path))
            title_el = package.find(f".//{DC_NS}title")
            book_title = (title_el.text or "").strip() if title_el is not None else ""

            manifest: dict[str, dict[str, str]] = {}
            for item in package.iter(f"{OPF_NS}item"):
                item_id = item.get("id", "")
                manifest[item_id] = {
                    "href": item.get("href", ""),
                    "media-type": item.get("media-type", ""),
                    "properties": item.get("properties", ""),
                }

            spine = package.find(f".//{OPF_NS}spine")
            spine_ids = (
                [ref.get("idref", "") for ref in spine.findall(f"{OPF_NS}itemref")]
                if spine is not None
                else []
            )
            toc_id = spine.get("toc", "") if spine is not None else ""
            toc_entries = _read_epub_toc(
                archive, manifest, opf_path, toc_id
            )

            docs: list[SpineDoc] = []
            for idref in spine_ids:
                item = manifest.get(idref)
                if item is None:
                    continue
                href = item["href"]
                if not href:
                    continue
                if not (
                    "html" in item["media-type"]
                    or href.lower().endswith((".xhtml", ".html", ".htm"))
                ):
                    continue
                doc_path, _fragment = _resolve_epub_href(opf_path, href)
                if doc_path not in names:
                    warnings.append(f"epub spine item missing: {doc_path}")
                    continue
                text, _encoding, doc_warnings = decode_bytes(archive.read(doc_path))
                warnings.extend(doc_warnings)
                blocks, doc_title = html_to_blocks(text)
                docs.append(SpineDoc(doc_path, blocks, doc_title))

            if not docs:
                raise IngestError(f"no readable spine documents in {path}")

            if extract_images:
                for name in sorted(names):
                    extension = Path(name).suffix.lower()
                    if extension in IMAGE_EXTS and not name.startswith("META-INF/"):
                        images.append(
                            ParsedImage(
                                archive.read(name), extension.lstrip("."), name
                            )
                        )
    except zipfile.BadZipFile as exc:
        raise IngestError(f"invalid epub archive: {path}") from exc
    except ET.ParseError as exc:
        raise IngestError(f"invalid epub XML: {path}") from exc

    all_blocks = [block for doc in docs for block in doc.blocks]
    if not block_has_text(all_blocks):
        raise IngestError(f"no readable text in {path}")

    toc_by_path: dict[str, list[TocEntry]] = defaultdict(list)
    for entry in toc_entries:
        toc_by_path[entry.path].append(entry)
    toc_targets = [doc for doc in docs if doc.path in toc_by_path]

    chapters: list[ParsedChapter] = []
    if len(toc_targets) >= 2:
        fallback_level = pick_split_level(all_blocks)
        for doc in docs:
            if doc.path in toc_by_path:
                title = (
                    toc_by_path[doc.path][0].title
                    or doc.doc_title
                    or Path(doc.path).stem
                )
                body = _strip_leading_toc_heading(doc.blocks, title)
                body = normalize_body_blocks(body, fallback_level or 1)
                chapters.append(ParsedChapter(title, body, "high"))
            else:
                _merge_continuation(chapters, doc.blocks, fallback_level)
    else:
        chapters = chapters_from_blocks(
            all_blocks, book_title or path.stem
        )

    if not chapters:
        chapters = [single_chapter(all_blocks, book_title or path.stem)]
    if len(chapters) == 1:
        warnings.append(
            "章节标题不足 2 个，整份文本作为一章处理（confidence: low）。"
        )
    input_hanzi = sum(count_hanzi(block.text) for block in all_blocks)
    return ParseResult("epub", chapters, None, warnings, input_hanzi, images)


# ---------------------------------------------------------------------------
# Parser: PDF (optional pypdf)
# ---------------------------------------------------------------------------

def parse_pdf_file(path: Path) -> ParseResult:
    try:
        from pypdf import PdfReader
    except ImportError as exc:
        raise IngestError(
            "PDF 摄取需要可选依赖 pypdf。请先运行 "
            "`python -m pip install pypdf` 后重试，"
            "或先把 PDF 转换为 txt/epub/docx。"
        ) from exc

    warnings: list[str] = []
    try:
        reader = PdfReader(str(path))
        pages = [page.extract_text() or "" for page in reader.pages]
    except Exception as exc:  # pypdf raises several concrete error types
        raise IngestError(f"failed to read PDF {path}: {exc}") from exc

    text = "\n".join(pages)
    readable = count_hanzi(text) + len(re.findall(r"[A-Za-z0-9]", text))
    if readable < 20:
        warnings.append("PDF 无文本层，需要 OCR 后再导入。")
        raise IngestError(
            "PDF 无文本层，需要 OCR 后再导入（扫描版 PDF 不能直接提取文字）。"
        )

    lines, clean_warnings, _removed, _removed_hanzi = clean_plain_lines(
        text.splitlines()
    )
    warnings.extend(clean_warnings)
    chapters = segment_plain_lines(lines, path.stem)
    if len(chapters) == 1:
        warnings.append(
            "章节标题不足 2 个，整份文本作为一章处理（confidence: low）。"
        )
    return ParseResult("pdf", chapters, None, warnings, count_hanzi(text))


# ---------------------------------------------------------------------------
# Source dispatch and hashing
# ---------------------------------------------------------------------------

def parse_file(path: Path, extract_images: bool = False) -> ParseResult:
    extension = path.suffix.lower()
    fmt = SUPPORTED_EXTS.get(extension)
    if fmt is None:
        supported = ", ".join(sorted(set(SUPPORTED_EXTS)))
        raise IngestError(
            f"unsupported source format {extension or '(none)'}: {path}\n"
            f"supported: {supported}"
        )
    if fmt == "txt":
        return parse_text_file(path)
    if fmt == "md":
        return parse_markdown_file(path)
    if fmt == "epub":
        return parse_epub_file(path, extract_images)
    if fmt == "docx":
        return parse_docx_file(path)
    if fmt == "html":
        return parse_html_file(path)
    return parse_pdf_file(path)


def collect_directory_files(directory: Path) -> list[Path]:
    files = [
        path
        for path in directory.rglob("*")
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTS
    ]
    return sorted(files, key=lambda item: (item.name.lower(), item.as_posix()))


def parse_source(source: Path, extract_images: bool = False) -> ParseResult:
    if source.is_dir():
        files = collect_directory_files(source)
        if not files:
            supported = ", ".join(sorted(set(SUPPORTED_EXTS)))
            raise IngestError(
                f"no supported source files in {source} (supported: {supported})"
            )
        chapters: list[ParsedChapter] = []
        warnings: list[str] = []
        encodings: set[str] = set()
        images: list[ParsedImage] = []
        input_hanzi = 0
        for path in files:
            relative = path.relative_to(source).as_posix()
            try:
                result = parse_file(path, extract_images)
            except IngestError as exc:
                if path.suffix.lower() == ".pdf":
                    warnings.append(f"{relative}: skipped ({exc})")
                    continue
                raise
            warnings.extend(f"{relative}: {warning}" for warning in result.warnings)
            chapters.extend(result.chapters)
            input_hanzi += result.input_hanzi
            images.extend(result.images)
            if result.encoding:
                encodings.add(result.encoding)
        if not chapters:
            raise IngestError(f"no readable text in directory {source}")
        encoding = (
            next(iter(encodings))
            if len(encodings) == 1
            else ("mixed" if encodings else None)
        )
        return ParseResult(
            "directory", chapters, encoding, warnings, input_hanzi, images
        )

    if not source.exists():
        raise IngestError(f"source not found: {source}")
    return parse_file(source, extract_images)


def sha256_source(source: Path) -> str:
    digest = hashlib.sha256()
    if source.is_dir():
        for path in collect_directory_files(source):
            digest.update(path.relative_to(source).as_posix().encode("utf-8"))
            digest.update(b"\x00")
            digest.update(path.read_bytes())
            digest.update(b"\x00")
    else:
        digest.update(source.read_bytes())
    return digest.hexdigest()


# ---------------------------------------------------------------------------
# Rendering and planning
# ---------------------------------------------------------------------------

def render_chapter(chapter: ParsedChapter) -> str:
    lines = [f"# {chapter.title}".rstrip()]
    for block in chapter.blocks:
        if block.kind == "heading":
            level = max(2, min(6, block.level))
            lines.append("")
            lines.append("#" * level + " " + block.text.strip())
        else:
            text = block.text.strip("\n").rstrip()
            if text.strip():
                lines.append("")
                lines.append(text)
    return "\n".join(lines).rstrip() + "\n"


def project_relative(project: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(project.resolve()).as_posix()
    except ValueError:
        return path.resolve().as_posix()


def resolve_target_dir(project: Path, config: dict, to_option: str) -> Path:
    if to_option:
        candidate = Path(to_option)
        return candidate if candidate.is_absolute() else project / candidate
    source_dir = config.get("sourceDir")
    if not source_dir:
        kind = str(config.get("kind") or "").lower()
        source_dir = "chapters" if kind == "creation" else "sources"
    return project / source_dir


def merge_project_chapters(config: dict, specs: list[dict]) -> dict:
    merged = dict(config)
    existing = [dict(entry) for entry in (config.get("chapters") or [])]
    by_file: dict[str, dict] = {}
    for entry in existing:
        for filename in entry.get("files", []):
            by_file.setdefault(str(filename), entry)

    used_ids = {str(entry.get("id")) for entry in existing if entry.get("id")}
    max_order = max(
        [int(entry.get("order") or 0) for entry in existing] + [0]
    )
    next_id = 1
    for spec in specs:
        filename = spec["file"]
        existing_entry = by_file.get(filename)
        if existing_entry is not None:
            existing_entry["title"] = spec["title"]
            existing_entry.setdefault("mode", "parts")
            continue
        while f"ch{next_id}" in used_ids:
            next_id += 1
        max_order += 1
        entry = {
            "id": f"ch{next_id}",
            "order": max_order,
            "title": spec["title"],
            "files": [filename],
            "mode": "parts",
        }
        used_ids.add(entry["id"])
        next_id += 1
        existing.append(entry)
        by_file[filename] = entry
    merged["chapters"] = existing
    return merged


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_report(
    source: Path,
    parse_result: ParseResult,
    project: Path,
    target_dir: Path,
    dry_run: bool,
    chapter_specs: list[dict],
    image_paths: list[str],
    output_hanzi: int,
) -> dict:
    input_hanzi = parse_result.input_hanzi
    dropped_ratio = (
        max(0.0, 1.0 - output_hanzi / input_hanzi) if input_hanzi else 0.0
    )
    warnings = list(parse_result.warnings)
    if input_hanzi and output_hanzi / input_hanzi < 0.98:
        warnings.append(
            f"输出正文汉字 {output_hanzi} / 输入 {input_hanzi}"
            f"（丢失 {dropped_ratio:.2%}），主要来自页眉页脚、页码清理与标题归一。"
        )
    return {
        "source": str(source),
        "format": parse_result.format,
        "sha256": sha256_source(source),
        "encoding": parse_result.encoding,
        "targetDir": project_relative(project, target_dir),
        "dryRun": dry_run,
        "chapters": chapter_specs,
        "warnings": warnings,
        "stats": {
            "inputHanzi": input_hanzi,
            "outputHanzi": output_hanzi,
            "droppedRatio": round(dropped_ratio, 6),
        },
        "images": image_paths,
    }


def print_human_summary(
    report: dict, project: Path, writes: list[tuple[Path, bytes]]
) -> None:
    print(f"source: {report['source']} ({report['format']}, {report['encoding'] or 'binary'})")
    print(f"target: {report['targetDir']}")
    print(f"chapters: {len(report['chapters'])}")
    for chapter in report["chapters"]:
        print(
            f"  {chapter['file']}  {chapter['title']}  "
            f"{chapter['hanzi']} hanzi / {chapter['paragraphs']} paragraphs  "
            f"[{chapter['confidence']}]"
        )
    stats = report["stats"]
    print(
        f"stats: input {stats['inputHanzi']} hanzi -> output "
        f"{stats['outputHanzi']} hanzi (dropped {stats['droppedRatio']:.2%})"
    )
    if report["warnings"]:
        print("warnings:")
        for warning in report["warnings"]:
            print(f"  - {warning}")
    if report["images"]:
        print("images:")
        for path in report["images"]:
            print(f"  - {path}")
    if report["dryRun"]:
        print("dry-run: no files written")
        print(f"planned writes: {len(writes)}")
        for path, _content in writes:
            print(f"  - {project_relative(project, path)}")
    else:
        print("wrote:")
        for path, _content in writes:
            print(f"  - {project_relative(project, path)}")


def run(args: argparse.Namespace) -> int:
    project = Path(args.project).resolve()
    source = Path(args.source).resolve()
    if not project.is_dir():
        raise IngestError(f"project directory not found: {project}")
    config_path = project / "project.json"
    if not config_path.exists():
        raise IngestError(f"missing project.json: {config_path}")
    try:
        config = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise IngestError(f"cannot read project.json: {exc}") from exc

    target_dir = resolve_target_dir(project, config, args.to)
    parse_result = parse_source(source, args.extract_images)

    chapter_specs: list[dict] = []
    chapter_writes: list[tuple[Path, bytes]] = []
    output_hanzi = 0
    for index, chapter in enumerate(parse_result.chapters, 1):
        filename = f"{index:02d}.md"
        content = render_chapter(chapter)
        hanzi = count_hanzi(content)
        output_hanzi += hanzi
        chapter_specs.append(
            {
                "index": index,
                "title": chapter.title,
                "file": filename,
                "hanzi": hanzi,
                "paragraphs": paragraph_count(chapter),
                "confidence": chapter.confidence,
            }
        )
        chapter_writes.append((target_dir / filename, content.encode("utf-8")))

    image_writes: list[tuple[Path, bytes]] = []
    image_paths: list[str] = []
    if args.extract_images:
        for index, image in enumerate(parse_result.images, 1):
            filename = f"epub-{index}.{image.ext}"
            path = project / "assets" / "img" / filename
            image_writes.append((path, image.data))
            image_paths.append(project_relative(project, path))

    report = build_report(
        source,
        parse_result,
        project,
        target_dir,
        args.dry_run,
        chapter_specs,
        image_paths,
        output_hanzi,
    )

    if args.update_project and args.to:
        configured = project / str(config.get("sourceDir") or "sources")
        if target_dir.resolve() != configured.resolve():
            report["warnings"].append(
                f"--to {args.to} 与 project.json 的 sourceDir 不同；"
                "project.json 的 sourceDir 未修改。"
            )

    writes = chapter_writes + image_writes
    conflicts = [path for path, _content in writes if path.exists()]
    if conflicts and not args.force and not args.dry_run:
        report["warnings"].extend(
            f"conflict: {project_relative(project, path)}" for path in conflicts
        )
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print_human_summary(report, project, writes)
            print("conflicts (use --force to overwrite):", file=sys.stderr)
            for path in conflicts:
                print(f"  - {project_relative(project, path)}", file=sys.stderr)
            print("aborted: no files written", file=sys.stderr)
        return 1

    if conflicts and args.dry_run and not args.force:
        report["warnings"].extend(
            f"dry-run conflict: {project_relative(project, path)} exists"
            for path in conflicts
        )

    if args.dry_run:
        if args.json:
            print(json.dumps(report, ensure_ascii=False, indent=2))
        else:
            print_human_summary(report, project, writes)
        return 0

    for path, content in writes:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(content)

    report_path = project / REPORT_RELATIVE
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )

    if args.update_project:
        merged = merge_project_chapters(config, chapter_specs)
        config_path.write_text(
            json.dumps(merged, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print_human_summary(report, project, writes + [(report_path, b"")])
        if args.update_project:
            print(f"project: updated {config_path}")
    return 0


def _force_utf8_streams() -> None:
    """Windows consoles default to the locale codepage; Story Forge is UTF-8."""
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")  # type: ignore[attr-defined]
        except (AttributeError, ValueError):
            pass


def main(argv: list[str] | None = None) -> int:
    _force_utf8_streams()
    parser = argparse.ArgumentParser(
        prog="ingest_sources.py",
        description=(
            "Ingest txt/md/epub/docx/html sources into Story Forge Markdown "
            "chapters. PDF requires the optional pypdf package."
        ),
    )
    parser.add_argument("project", help="Story Forge project directory")
    parser.add_argument("source", help="source file or directory")
    parser.add_argument("--to", default="", help="target directory (override)")
    parser.add_argument("--dry-run", action="store_true", help="plan only")
    parser.add_argument(
        "--force", action="store_true", help="overwrite existing target files"
    )
    parser.add_argument(
        "--update-project", action="store_true", help="merge chapters into project.json"
    )
    parser.add_argument(
        "--extract-images", action="store_true", help="copy EPUB images"
    )
    parser.add_argument("--json", action="store_true", help="print JSON only")
    args = parser.parse_args(argv)

    try:
        return run(args)
    except IngestError as exc:
        if args.json:
            print(json.dumps({"error": str(exc)}, ensure_ascii=False))
        else:
            print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    sys.exit(main())
