#!/usr/bin/env python3
"""Tests for engine/tools/project_status.py."""
from __future__ import annotations

import hashlib
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Any

ENGINE = Path(__file__).resolve().parent.parent
TOOLS = ENGINE / "tools"
STATUS = TOOLS / "project_status.py"
PARSE = TOOLS / "parse_chapters.py"

CHAPTER_MD = "# 第一章 测试\n\n## 第一幕\n\n### 场景一\n\n{body}\n"


def run_script(
    script: Path, project: Path, *args: str
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, str(script), str(project), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )


def make_project(
    root: Path,
    *,
    kind: str = "import",
    chapters: list[dict[str, Any]],
    source_dir: str = "sources",
    retold_dir: str | None = None,
    ready: list[str] | None = None,
    entities: list[dict[str, Any]] | None = None,
    relations: list[dict[str, Any]] | None = None,
    chapter_meta: dict[str, Any] | None = None,
    images: list[dict[str, Any]] | None = None,
    variants: list[dict[str, Any]] | None = None,
    volumes: list[dict[str, Any]] | None = None,
    title: str = "测试项目",
) -> Path:
    project = root / "proj"
    project.mkdir(parents=True)
    config: dict[str, Any] = {
        "slug": "proj",
        "title": title,
        "subtitle": "",
        "description": "",
        "lede": "",
        "sourceDir": source_dir,
        "siteDir": "site",
        "dataDir": "site/data",
        "kind": kind,
        "modes": ["original"]
        if kind == "import"
        else (["original", "retold"] if kind == "retelling" else ["retold"]),
        "defaultMode": "original" if kind == "import" else "retold",
        "primaryMode": "retold" if kind == "creation" else "original",
        "modeLabels": {"original": "原文", "retold": "复述"},
        "chapters": chapters,
        "ready": ready or [],
    }
    if retold_dir:
        config["retoldDir"] = retold_dir
    if variants is not None:
        config["variants"] = variants
    if volumes is not None:
        config["volumes"] = volumes
    (project / "project.json").write_text(
        json.dumps(config, ensure_ascii=False), encoding="utf-8"
    )

    content = project / "content"
    content.mkdir()
    (content / "entities.json").write_text(
        json.dumps(
            {"entities": entities or [], "relations": relations or []},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (content / "chapter_meta.json").write_text(
        json.dumps(chapter_meta or {}, ensure_ascii=False), encoding="utf-8"
    )
    (content / "recap.json").write_text(
        json.dumps({"eras": []}, ensure_ascii=False), encoding="utf-8"
    )
    (content / "worldview.json").write_text(
        json.dumps({"cards": []}, ensure_ascii=False), encoding="utf-8"
    )
    (content / "illustrations.json").write_text(
        json.dumps({"images": images or []}, ensure_ascii=False), encoding="utf-8"
    )

    (project / source_dir).mkdir(parents=True)
    if retold_dir:
        (project / retold_dir).mkdir()
    for variant in variants or []:
        directory = variant.get("dir")
        if directory:
            (project / str(directory)).mkdir(parents=True, exist_ok=True)
    return project


def parse_project(project: Path) -> subprocess.CompletedProcess[str]:
    return run_script(PARSE, project)


def status_json(
    project: Path, *args: str
) -> tuple[subprocess.CompletedProcess[str], dict[str, Any]]:
    result = run_script(STATUS, project, "--json", *args)
    if not result.stdout.strip():
        return result, {}
    return result, json.loads(result.stdout)


class StatusMissingBuildTests(unittest.TestCase):
    def test_missing_build_degrades(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(
                Path(tmp),
                chapters=[{"id": "ch1", "order": 1, "files": ["01.md"]}],
                ready=["ch1"],
                chapter_meta={"ch1": {"cast": []}},
            )
            (project / "sources" / "01.md").write_text(
                CHAPTER_MD.format(body="沈舟走进灯塔。"), encoding="utf-8"
            )

            result = run_script(STATUS, project, "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)

            self.assertEqual(data["project"]["chapterCount"], 1)
            self.assertEqual(data["project"]["readyCount"], 1)
            self.assertGreater(data["project"]["hanzi"], 0)
            chapter = data["chapters"][0]
            self.assertFalse(chapter["parsed"])
            self.assertIsNone(chapter["variants"]["original"]["stale"])
            self.assertIsNone(chapter["variants"]["original"]["fidelity"])
            self.assertIsNone(data["build"]["parseReportAt"])
            self.assertEqual(data["build"]["errors"], [])
            self.assertEqual(data["build"]["warnings"], [])
            self.assertTrue(
                any("parse" in action for action in data["nextActions"])
            )
            self.assertTrue((project / "build" / "status.json").is_file())
            written = json.loads(
                (project / "build" / "status.json").read_text(encoding="utf-8")
            )
            self.assertEqual(written, data)

    def test_partial_build_outputs_are_reported(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(
                Path(tmp),
                chapters=[{"id": "ch1", "order": 1, "files": ["01.md"]}],
                ready=["ch1"],
                chapter_meta={"ch1": {"cast": []}},
            )
            (project / "sources" / "01.md").write_text(
                CHAPTER_MD.format(body="沈舟走进灯塔。"), encoding="utf-8"
            )
            parsed = parse_project(project)
            self.assertEqual(parsed.returncode, 0, parsed.stdout + parsed.stderr)
            (project / "build" / "parse_report.json").unlink()

            result, data = status_json(project)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(data["chapters"][0]["parsed"])
            self.assertIsNone(data["build"]["parseReportAt"])
            self.assertTrue(
                any("parse_report" in action for action in data["nextActions"])
            )
            self.assertTrue(
                data["chapters"][0]["variants"]["original"]["stale"] is None
            )

    def test_creation_mode_is_synthesized(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(
                Path(tmp),
                kind="creation",
                chapters=[{"id": "ch1", "order": 1, "files": ["01.md"]}],
                source_dir="chapters",
                ready=["ch1"],
                chapter_meta={"ch1": {"cast": []}},
            )
            (project / "chapters" / "01.md").write_text(
                CHAPTER_MD.format(body="沈舟走进灯塔。"), encoding="utf-8"
            )

            result, data = status_json(project)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(data["project"]["kind"], "creation")
            self.assertEqual(data["project"]["modes"], ["retold"])
            self.assertEqual(
                list(data["chapters"][0]["variants"]), ["retold"]
            )
            self.assertTrue(data["chapters"][0]["variants"]["retold"]["present"])


class StatusAfterParseTests(unittest.TestCase):
    def test_ready_versus_unready_and_volumes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(
                Path(tmp),
                chapters=[
                    {"id": "ch1", "order": 1, "files": ["01.md"], "volume": "vol1"},
                    {"id": "ch2", "order": 2, "files": ["02.md"]},
                ],
                ready=["ch1"],
                chapter_meta={"ch1": {"cast": []}},
                volumes=[
                    {"id": "vol1", "title": "第一卷", "order": 1, "chapters": ["ch1"]}
                ],
            )
            (project / "sources" / "01.md").write_text(
                CHAPTER_MD.format(body="沈舟走进灯塔。"), encoding="utf-8"
            )
            (project / "sources" / "02.md").write_text(
                CHAPTER_MD.format(body="林岚在等他。"), encoding="utf-8"
            )

            parsed = parse_project(project)
            self.assertEqual(parsed.returncode, 0, parsed.stdout + parsed.stderr)

            result, data = status_json(project)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(data["project"]["chapterCount"], 2)
            self.assertEqual(data["project"]["readyCount"], 1)
            self.assertEqual(data["project"]["modes"], ["original"])
            self.assertIsNotNone(data["build"]["parseReportAt"])

            ch1, ch2 = data["chapters"]
            self.assertTrue(ch1["parsed"])
            self.assertTrue(ch1["ready"])
            self.assertTrue(ch1["meta"])
            self.assertEqual(ch1["volume"], "vol1")
            self.assertEqual(ch1["cast"], 0)
            self.assertGreater(ch1["sections"], 0)
            self.assertTrue(ch1["variants"]["original"]["fidelity"])

            self.assertTrue(ch2["parsed"])
            self.assertFalse(ch2["ready"])
            self.assertFalse(ch2["meta"])
            self.assertIsNone(ch2["volume"])

            self.assertTrue(
                any("ready" in action for action in data["nextActions"])
            )
            self.assertTrue(
                any("章节元数据" in action for action in data["nextActions"])
            )

    def test_missing_evidence_is_counted(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(
                Path(tmp),
                chapters=[{"id": "ch1", "order": 1, "files": ["01.md"]}],
                ready=["ch1"],
                chapter_meta={"ch1": {"cast": []}},
                entities=[
                    {"id": "a", "type": "character", "name": "甲", "evidence": []},
                    {
                        "id": "b",
                        "type": "term",
                        "name": "乙",
                        "evidence": [{"chapter": "ch1", "section": "s", "quote": "乙"}],
                    },
                ],
            )
            (project / "sources" / "01.md").write_text(
                CHAPTER_MD.format(body="甲和乙。"), encoding="utf-8"
            )

            result, data = status_json(project)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(data["content"]["entities"], 2)
            self.assertEqual(data["content"]["byType"], {"character": 1, "term": 1})
            self.assertEqual(data["content"]["entitiesWithoutEvidence"], 1)
            self.assertTrue(
                any("缺少证据" in action for action in data["nextActions"])
            )

    def test_illustration_counts(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            images = [
                {
                    "id": "img-1",
                    "chapter": "ch1",
                    "section": "sch1-0-1",
                    "alt": "灯塔",
                    "credit": "本地提供",
                    "sourceUrl": "",
                },
                {"id": "img-2", "chapter": "ch1", "alt": ""},
                {
                    "id": "img-3",
                    "chapter": "ch2",
                    "section": "sch2-0-1",
                    "alt": "海面",
                    "credit": "",
                    "sourceUrl": "https://example.com/a.jpg",
                },
            ]
            project = make_project(
                Path(tmp),
                chapters=[
                    {"id": "ch1", "order": 1, "files": ["01.md"]},
                    {"id": "ch2", "order": 2, "files": ["02.md"]},
                ],
                ready=["ch1", "ch2"],
                chapter_meta={"ch1": {"cast": []}, "ch2": {"cast": []}},
                images=images,
            )
            (project / "sources" / "01.md").write_text(
                CHAPTER_MD.format(body="甲。"), encoding="utf-8"
            )
            (project / "sources" / "02.md").write_text(
                CHAPTER_MD.format(body="乙。"), encoding="utf-8"
            )

            result, data = status_json(project)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                data["illustrations"],
                {
                    "total": 3,
                    "placed": 2,
                    "unplaced": 1,
                    "missingAlt": 1,
                    "missingCredit": 1,
                },
            )
            self.assertEqual(data["chapters"][0]["illustrations"], 2)
            self.assertEqual(data["chapters"][1]["illustrations"], 1)
            self.assertTrue(
                any("未分配小节" in action for action in data["nextActions"])
            )


class StatusExitCodeTests(unittest.TestCase):
    def test_strict_warnings_exit_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(
                Path(tmp),
                chapters=[{"id": "ch1", "order": 1, "files": ["01.md"]}],
                ready=["ch1"],
                chapter_meta={},
            )
            (project / "sources" / "01.md").write_text(
                CHAPTER_MD.format(body="沈舟走进灯塔。"), encoding="utf-8"
            )

            loose = run_script(STATUS, project)
            self.assertEqual(loose.returncode, 0, loose.stderr)

            strict = run_script(STATUS, project, "--strict")
            self.assertEqual(strict.returncode, 1)
            self.assertTrue((project / "build" / "status.json").is_file())

    def test_missing_project_json_exits_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "empty"
            project.mkdir()
            result = run_script(STATUS, project, "--json")
            self.assertEqual(result.returncode, 1)
            self.assertIn("project.json", result.stderr)
            self.assertEqual(result.stdout.strip(), "")

    def test_missing_content_dir_exits_one(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = Path(tmp) / "proj"
            project.mkdir()
            (project / "project.json").write_text(
                json.dumps({"title": "x", "chapters": []}), encoding="utf-8"
            )
            result = run_script(STATUS, project, "--json")
            self.assertEqual(result.returncode, 1)
            self.assertIn("content", result.stderr)


class StatusOutputTests(unittest.TestCase):
    def test_json_output_is_pure(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(
                Path(tmp),
                chapters=[{"id": "ch1", "order": 1, "files": ["01.md"]}],
                ready=["ch1"],
                chapter_meta={"ch1": {"cast": []}},
            )
            (project / "sources" / "01.md").write_text(
                CHAPTER_MD.format(body="沈舟走进灯塔。"), encoding="utf-8"
            )

            result = run_script(STATUS, project, "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(result.stdout.strip().startswith("{"))
            json.loads(result.stdout)  # entire stdout must be one JSON object
            self.assertNotIn("项目：", result.stdout)
            self.assertNotIn("下一步", result.stdout)

    def test_human_output_sections(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(
                Path(tmp),
                chapters=[{"id": "ch1", "order": 1, "files": ["01.md"]}],
                ready=["ch1"],
                chapter_meta={"ch1": {"cast": []}},
            )
            (project / "sources" / "01.md").write_text(
                CHAPTER_MD.format(body="沈舟走进灯塔。"), encoding="utf-8"
            )

            result = run_script(STATUS, project)
            self.assertEqual(result.returncode, 0, result.stderr)
            for heading in ("项目：", "章节矩阵：", "内容覆盖：", "下一步："):
                self.assertIn(heading, result.stdout)
            self.assertIn("ch1", result.stdout)


class StalenessTests(unittest.TestCase):
    def test_newer_source_marks_variant_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(
                Path(tmp),
                chapters=[
                    {"id": "ch1", "order": 1, "files": ["01.md"]},
                    {"id": "ch2", "order": 2, "files": ["02.md"]},
                ],
                ready=["ch1", "ch2"],
                chapter_meta={"ch1": {"cast": []}, "ch2": {"cast": []}},
            )
            source1 = project / "sources" / "01.md"
            source1.write_text(CHAPTER_MD.format(body="沈舟走进灯塔。"), encoding="utf-8")
            (project / "sources" / "02.md").write_text(
                CHAPTER_MD.format(body="林岚在等他。"), encoding="utf-8"
            )
            parsed = parse_project(project)
            self.assertEqual(parsed.returncode, 0, parsed.stdout + parsed.stderr)

            report_path = project / "build" / "parse_report.json"
            report_mtime = report_path.stat().st_mtime
            future = report_mtime + 60
            os.utime(source1, (future, future))

            result, data = status_json(project)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(
                data["chapters"][0]["variants"]["original"]["stale"]
            )
            self.assertFalse(
                data["chapters"][1]["variants"]["original"]["stale"]
            )
            self.assertTrue(
                any("重新运行 parse" in action for action in data["nextActions"])
            )

    def test_recorded_hash_takes_precedence_over_mtime(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(
                Path(tmp),
                chapters=[{"id": "ch1", "order": 1, "files": ["01.md"]}],
                ready=["ch1"],
                chapter_meta={"ch1": {"cast": []}},
            )
            source = project / "sources" / "01.md"
            source.write_text(CHAPTER_MD.format(body="沈舟走进灯塔。"), encoding="utf-8")
            parsed = parse_project(project)
            self.assertEqual(parsed.returncode, 0, parsed.stdout + parsed.stderr)

            digest = hashlib.sha256(source.read_bytes()).hexdigest()
            report_path = project / "build" / "parse_report.json"
            report = json.loads(report_path.read_text(encoding="utf-8"))
            report["sourceHashes"] = {"sources/01.md": digest}
            report_path.write_text(
                json.dumps(report, ensure_ascii=False), encoding="utf-8"
            )

            report_mtime = report_path.stat().st_mtime
            future = report_mtime + 60
            os.utime(source, (future, future))

            _, data = status_json(project)
            self.assertFalse(
                data["chapters"][0]["variants"]["original"]["stale"]
            )

            source.write_text(
                CHAPTER_MD.format(body="沈舟走进灯塔。新增一行。"),
                encoding="utf-8",
            )
            _, changed = status_json(project)
            self.assertTrue(
                changed["chapters"][0]["variants"]["original"]["stale"]
            )

    def test_missing_source_is_not_stale(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(
                Path(tmp),
                chapters=[{"id": "ch1", "order": 1, "files": ["01.md"]}],
                ready=["ch1"],
                chapter_meta={"ch1": {"cast": []}},
            )
            source = project / "sources" / "01.md"
            source.write_text(CHAPTER_MD.format(body="沈舟走进灯塔。"), encoding="utf-8")
            parsed = parse_project(project)
            self.assertEqual(parsed.returncode, 0, parsed.stdout + parsed.stderr)

            source.unlink()
            result, data = status_json(project)
            self.assertEqual(result.returncode, 0, result.stderr)
            variant = data["chapters"][0]["variants"]["original"]
            self.assertFalse(variant["present"])
            self.assertIs(variant["stale"], False)
            self.assertTrue(
                any("缺少源文件" in action for action in data["nextActions"])
            )


class GeneralizedVariantsTests(unittest.TestCase):
    def test_project_variants_and_variant_files(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = make_project(
                Path(tmp),
                kind="retelling",
                chapters=[
                    {
                        "id": "ch1",
                        "order": 1,
                        "files": ["01.md"],
                        "variantFiles": {
                            "retold": ["01.md"],
                            "en": ["01.en.md"],
                        },
                    }
                ],
                source_dir="sources",
                retold_dir="retold",
                ready=["ch1"],
                chapter_meta={"ch1": {"cast": []}},
                variants=[
                    {
                        "id": "original",
                        "label": "原文",
                        "dir": "sources",
                        "primary": True,
                    },
                    {"id": "retold", "label": "复述", "dir": "retold"},
                    {
                        "id": "en",
                        "label": "English",
                        "dir": "translations/en",
                    },
                ],
            )
            (project / "sources" / "01.md").write_text(
                CHAPTER_MD.format(body="沈舟走进灯塔。"), encoding="utf-8"
            )
            (project / "retold" / "01.md").write_text(
                CHAPTER_MD.format(body="沈舟到灯塔接班。"), encoding="utf-8"
            )
            (project / "translations" / "en" / "01.en.md").write_text(
                "# Chapter One\n\n## Act One\n\n### Scene One\n\nShen Zhou enters.\n",
                encoding="utf-8",
            )

            result, data = status_json(project)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(
                data["project"]["modes"], ["original", "retold", "en"]
            )
            variants = data["chapters"][0]["variants"]
            self.assertEqual(list(variants), ["original", "retold", "en"])
            self.assertEqual(variants["original"]["files"], ["01.md"])
            self.assertEqual(variants["retold"]["files"], ["01.md"])
            self.assertEqual(variants["en"]["files"], ["01.en.md"])
            self.assertTrue(all(info["present"] for info in variants.values()))
            self.assertGreater(variants["original"]["hanzi"], 0)
            self.assertGreater(variants["retold"]["hanzi"], 0)


if __name__ == "__main__":
    unittest.main()
