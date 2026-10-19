#!/usr/bin/env python3
"""Tests for engine/tools/ingest_sources.py.

All fixtures are generated in temporary directories; no network access.
Run from the plugin root:
    python -m unittest engine.tests.test_ingest -v
"""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
TOOL = ENGINE / "tools" / "ingest_sources.py"

CONTAINER_XML = """<?xml version="1.0"?>
<container version="1.0" xmlns="urn:oasis:names:tc:opendocument:xmlns:container">
  <rootfiles>
    <rootfile full-path="OEBPS/content.opf"
              media-type="application/oebps-package+xml"/>
  </rootfiles>
</container>
"""

OPF_XML = """<?xml version="1.0" encoding="utf-8"?>
<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id">
  <metadata xmlns:dc="http://purl.org/dc/elements/1.1/">
    <dc:title>测试书</dc:title>
  </metadata>
  <manifest>
    <item id="nav" href="nav.xhtml" media-type="application/xhtml+xml"
          properties="nav"/>
    <item id="b" href="part_b.xhtml" media-type="application/xhtml+xml"/>
    <item id="a" href="part_a.xhtml" media-type="application/xhtml+xml"/>
    <item id="img" href="images/pic.png" media-type="image/png"/>
  </manifest>
  <spine>
    <itemref idref="b"/>
    <itemref idref="a"/>
  </spine>
</package>
"""

NAV_XHTML = """<html xmlns="http://www.w3.org/1999/xhtml"
      xmlns:epub="http://www.idpf.org/2007/ops">
  <body>
    <nav epub:type="toc">
      <ol>
        <li><a href="part_b.xhtml">第二章 回声</a></li>
        <li><a href="part_a.xhtml">第一章 出发</a></li>
      </ol>
    </nav>
  </body>
</html>
"""

DOCX_DOCUMENT = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:document
    xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:body>
    <w:p><w:pPr><w:pStyle w:val="Heading1"/></w:pPr>
      <w:r><w:t>第一章 出发</w:t></w:r></w:p>
    <w:p><w:r><w:t>天还没亮。</w:t></w:r></w:p>
    <w:p><w:pPr><w:pStyle w:val="cn-heading"/></w:pPr>
      <w:r><w:t>第二章 抵达</w:t></w:r></w:p>
    <w:p><w:r><w:t>雨开始下。</w:t></w:r></w:p>
  </w:body>
</w:document>
"""

DOCX_STYLES = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles
    xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
  <w:style w:styleId="Heading1"><w:name w:val="heading 1"/></w:style>
  <w:style w:styleId="cn-heading"><w:name w:val="标题 1"/></w:style>
</w:styles>
"""

PNG_BYTES = bytes.fromhex(
    "89504e470d0a1a0a0000000d4948445200000001000000010806000000"
    "1f15c4890000000d49444154789c6360000002000154a24f5f00000000"
    "49454e44ae426082"
)


def make_project(root: Path, config: dict | None = None) -> Path:
    project = root / "project"
    project.mkdir()
    base = {
        "kind": "import",
        "sourceDir": "sources",
        "title": "保留的项目标题",
        "illustrations": {"enabled": True, "dir": "assets/img"},
        "customField": "keep-me",
        "chapters": [],
    }
    if config:
        base.update(config)
    (project / "project.json").write_text(
        json.dumps(base, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return project


def run_tool(
    project: Path, source: Path, *args: str
) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOL), str(project), str(source), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def read_report(project: Path) -> dict:
    return json.loads(
        (project / "build" / "ingest_report.json").read_text(encoding="utf-8")
    )


def write_epub(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("mimetype", "application/epub+zip")
        archive.writestr("META-INF/container.xml", CONTAINER_XML)
        archive.writestr("OEBPS/content.opf", OPF_XML)
        archive.writestr("OEBPS/nav.xhtml", NAV_XHTML)
        archive.writestr(
            "OEBPS/part_b.xhtml",
            '<html><head><title>第二章 回声</title></head><body>'
            "<h1>第二章 回声</h1><p>雨声。</p></body></html>",
        )
        archive.writestr(
            "OEBPS/part_a.xhtml",
            '<html><head><title>第一章 出发</title></head><body>'
            "<h1>第一章 出发</h1><p>天亮。</p></body></html>",
        )
        archive.writestr("OEBPS/images/pic.png", PNG_BYTES)


def write_docx(path: Path) -> None:
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("[Content_Types].xml", "<Types/>")
        archive.writestr("word/document.xml", DOCX_DOCUMENT)
        archive.writestr("word/styles.xml", DOCX_STYLES)


def two_chapter_text() -> str:
    return "第一章 出发\n天还没亮。\n\n第二章 抵达\n雨开始下。\n"


class IngestTests(unittest.TestCase):
    def test_txt_chinese_chapters_and_report_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            source = root / "book.txt"
            source.write_text(two_chapter_text(), encoding="utf-8")

            result = run_tool(project, source)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            report = read_report(project)
            required = {
                "source",
                "format",
                "sha256",
                "encoding",
                "targetDir",
                "dryRun",
                "chapters",
                "warnings",
                "stats",
            }
            self.assertTrue(required.issubset(report))
            self.assertEqual(report["format"], "txt")
            self.assertEqual(report["encoding"], "utf-8")
            self.assertEqual(report["targetDir"], "sources")
            self.assertFalse(report["dryRun"])
            self.assertEqual(len(report["sha256"]), 64)
            self.assertEqual(len(report["chapters"]), 2)
            self.assertEqual(
                set(report["chapters"][0]),
                {"index", "title", "file", "hanzi", "paragraphs", "confidence"},
            )
            self.assertEqual(
                [chapter["title"] for chapter in report["chapters"]],
                ["第一章 出发", "第二章 抵达"],
            )
            self.assertEqual(
                [chapter["confidence"] for chapter in report["chapters"]],
                ["high", "high"],
            )
            self.assertEqual(
                set(report["stats"]),
                {"inputHanzi", "outputHanzi", "droppedRatio"},
            )
            self.assertGreater(report["stats"]["inputHanzi"], 0)
            self.assertEqual(
                report["stats"]["inputHanzi"], report["stats"]["outputHanzi"]
            )

            first = (project / "sources" / "01.md").read_text(encoding="utf-8")
            self.assertTrue(first.startswith("# 第一章 出发"))
            self.assertIn("天还没亮。", first)
            self.assertTrue((project / "sources" / "02.md").exists())

    def test_gbk_txt_is_decoded(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            source = root / "gbk.txt"
            source.write_bytes(two_chapter_text().encode("gbk"))

            result = run_tool(project, source, "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertEqual(payload["encoding"], "gb18030")
            self.assertEqual(
                [chapter["title"] for chapter in payload["chapters"]],
                ["第一章 出发", "第二章 抵达"],
            )
            content = (project / "sources" / "01.md").read_text(encoding="utf-8")
            self.assertIn("天还没亮。", content)

    def test_page_headers_footers_and_numbers_removed(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            lines = ["灯塔的最后一班", "第一章 出发"]
            for index in range(6):
                lines.append(f"第{index + 1}段正文在这里。")
                if index % 2 == 0:
                    lines.extend([f"- {index + 1} -", "灯塔的最后一班"])
            lines.extend(["第 9 页", "第二章 抵达", "雨开始下。"])
            source = root / "pages.txt"
            source.write_text("\n".join(lines), encoding="utf-8")

            result = run_tool(project, source, "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            warnings = "\n".join(payload["warnings"])
            self.assertIn("页眉", warnings)

            output = "".join(
                path.read_text(encoding="utf-8")
                for path in sorted((project / "sources").glob("*.md"))
            )
            self.assertNotIn("灯塔的最后一班", output)
            self.assertNotIn("- 3 -", output)
            self.assertNotIn("第 9 页", output)
            self.assertIn("第1段正文在这里。", output)
            self.assertIn("第二章 抵达", output)

    def test_dry_run_writes_nothing_and_prints_one_json_object(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            source = root / "book.txt"
            source.write_text(two_chapter_text(), encoding="utf-8")

            result = run_tool(project, source, "--dry-run", "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)  # fails if extra text is printed
            self.assertTrue(payload["dryRun"])
            self.assertEqual(len(payload["chapters"]), 2)
            self.assertFalse((project / "sources").exists())
            self.assertFalse((project / "build").exists())

    def test_overwrite_protection_then_force(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            source = root / "book.txt"
            source.write_text(two_chapter_text(), encoding="utf-8")
            target = project / "sources" / "01.md"
            target.parent.mkdir()
            target.write_text("ORIGINAL", encoding="utf-8")

            blocked = run_tool(project, source, "--json")
            self.assertEqual(blocked.returncode, 1)
            self.assertEqual(target.read_text(encoding="utf-8"), "ORIGINAL")
            self.assertFalse((project / "build" / "ingest_report.json").exists())
            payload = json.loads(blocked.stdout)
            self.assertTrue(
                any("conflict" in warning for warning in payload["warnings"])
            )

            forced = run_tool(project, source, "--force", "--json")
            self.assertEqual(forced.returncode, 0, forced.stderr)
            updated = target.read_text(encoding="utf-8")
            self.assertTrue(updated.startswith("# 第一章 出发"))
            self.assertTrue((project / "build" / "ingest_report.json").exists())

    def test_epub_spine_order_and_image_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            source = root / "book.epub"
            write_epub(source)

            result = run_tool(project, source, "--extract-images", "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["format"], "epub")
            self.assertEqual(
                [chapter["title"] for chapter in report["chapters"]],
                ["第二章 回声", "第一章 出发"],
            )
            self.assertEqual(report["images"], ["assets/img/epub-1.png"])
            self.assertTrue((project / "assets" / "img" / "epub-1.png").exists())
            first = (project / "sources" / "01.md").read_text(encoding="utf-8")
            self.assertTrue(first.startswith("# 第二章 回声"))
            self.assertIn("雨声。", first)

    def test_docx_heading_styles(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            source = root / "book.docx"
            write_docx(source)

            result = run_tool(project, source, "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["format"], "docx")
            self.assertEqual(
                [chapter["title"] for chapter in report["chapters"]],
                ["第一章 出发", "第二章 抵达"],
            )
            self.assertEqual(
                [chapter["confidence"] for chapter in report["chapters"]],
                ["high", "high"],
            )
            second = (project / "sources" / "02.md").read_text(encoding="utf-8")
            self.assertTrue(second.startswith("# 第二章 抵达"))
            self.assertIn("雨开始下。", second)

    def test_html_extraction_skips_chrome_and_converts_headings(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            source = root / "page.html"
            source.write_text(
                "<html><head><title>网页故事</title>"
                "<style>.x{color:red}</style>"
                '<script>var secret="SHOULD_NOT_APPEAR";</script></head>'
                "<body><nav>导航文字不应出现</nav>"
                "<header>页头不应出现</header>"
                "<h1>第一章 网页</h1><p>沈舟走进灯塔。</p>"
                "<h1>第二章 网页</h1><p>林岚在等他。</p>"
                "<footer>页脚不应出现</footer></body></html>",
                encoding="utf-8",
            )

            result = run_tool(project, source, "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["format"], "html")
            self.assertEqual(
                [chapter["title"] for chapter in report["chapters"]],
                ["第一章 网页", "第二章 网页"],
            )
            output = "".join(
                path.read_text(encoding="utf-8")
                for path in sorted((project / "sources").glob("*.md"))
            )
            self.assertIn("沈舟走进灯塔。", output)
            self.assertIn("林岚在等他。", output)
            for excluded in (
                "SHOULD_NOT_APPEAR",
                "导航文字不应出现",
                "页头不应出现",
                "页脚不应出现",
            ):
                self.assertNotIn(excluded, output)

    def test_update_project_merges_without_destroying_fields(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(
                root,
                {
                    "chapters": [
                        {
                            "id": "ch7",
                            "order": 7,
                            "title": "旧章",
                            "files": ["old.md"],
                            "mode": "parts",
                        }
                    ]
                },
            )
            source = root / "book.txt"
            source.write_text(two_chapter_text(), encoding="utf-8")

            result = run_tool(project, source, "--update-project", "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            config = json.loads(
                (project / "project.json").read_text(encoding="utf-8")
            )
            self.assertEqual(config["title"], "保留的项目标题")
            self.assertEqual(config["customField"], "keep-me")
            self.assertEqual(config["illustrations"], {"enabled": True, "dir": "assets/img"})
            chapters = config["chapters"]
            self.assertEqual(len(chapters), 3)
            self.assertEqual(chapters[0]["id"], "ch7")
            self.assertEqual(chapters[0]["order"], 7)
            self.assertEqual(chapters[1]["id"], "ch1")
            self.assertEqual(chapters[1]["order"], 8)
            self.assertEqual(chapters[1]["files"], ["01.md"])
            self.assertEqual(chapters[1]["title"], "第一章 出发")
            self.assertEqual(chapters[1]["mode"], "parts")
            self.assertEqual(chapters[2]["id"], "ch2")
            self.assertEqual(chapters[2]["order"], 9)

    def test_update_project_reingest_preserves_ids_and_order(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            source = root / "book.txt"
            source.write_text(two_chapter_text(), encoding="utf-8")

            first = run_tool(project, source, "--update-project", "--json")
            self.assertEqual(first.returncode, 0, first.stderr)
            before = json.loads(
                (project / "project.json").read_text(encoding="utf-8")
            )["chapters"]

            second = run_tool(
                project, source, "--force", "--update-project", "--json"
            )
            self.assertEqual(second.returncode, 0, second.stderr)
            after = json.loads(
                (project / "project.json").read_text(encoding="utf-8")
            )["chapters"]

            self.assertEqual(len(after), len(before))
            self.assertEqual(
                [(entry["id"], entry["order"], entry["files"]) for entry in after],
                [(entry["id"], entry["order"], entry["files"]) for entry in before],
            )

    def test_directory_input_sorted_and_to_override(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            source = root / "many"
            source.mkdir()
            (source / "a.txt").write_text(
                "第一章 A\n甲。\n第二章 B\n乙。\n", encoding="utf-8"
            )
            (source / "b.md").write_text(
                "# 第一章 C\n\n丙。\n\n# 第二章 D\n\n丁。\n",
                encoding="utf-8",
            )

            result = run_tool(project, source, "--to", "ingested", "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["format"], "directory")
            self.assertEqual(report["targetDir"], "ingested")
            self.assertEqual(len(report["chapters"]), 4)
            self.assertEqual(
                [chapter["title"] for chapter in report["chapters"]],
                ["第一章 A", "第二章 B", "第一章 C", "第二章 D"],
            )
            self.assertEqual(
                sorted(path.name for path in (project / "ingested").glob("*.md")),
                ["01.md", "02.md", "03.md", "04.md"],
            )
            self.assertFalse((project / "sources").exists())

    def test_missing_source_reports_json_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            project = make_project(root)
            result = run_tool(project, root / "missing.txt", "--json")
            self.assertEqual(result.returncode, 2)
            payload = json.loads(result.stdout)
            self.assertIn("error", payload)


if __name__ == "__main__":
    unittest.main()
