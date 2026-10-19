#!/usr/bin/env python3
"""CLI-level integration tests: entrypoint, templates, failure exit codes."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent.parent
CLI = PLUGIN / "scripts" / "story.py"

CHAPTER = (
    "# 第一章 测试\n\n"
    "## 第一幕\n\n"
    "### 开场\n\n"
    "沈舟走进灯塔。雨还没下。\n"
)


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(CLI), *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


def write_json(path: Path, payload: object) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


class CliFailureTests(unittest.TestCase):
    def test_missing_project_exits_nonzero(self) -> None:
        missing = str(Path(tempfile.gettempdir()) / "story-forge-no-such-project")
        for command in (
            "parse",
            "build",
            "verify",
            "status",
            "audit",
            "style",
            "source-check",
            "single",
            "place-images",
            "fetch-images",
        ):
            result = run(command, missing)
            self.assertNotEqual(
                result.returncode,
                0,
                f"{command} returned 0 for a missing project\n{result.stdout}\n{result.stderr}",
            )

    def test_invalid_json_exits_nonzero(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "bad-json"
            self.assertEqual(run("new", str(project), "--template", "import").returncode, 0)
            (project / "content" / "entities.json").write_text("{", encoding="utf-8")
            (project / "sources" / "01.md").write_text(CHAPTER, encoding="utf-8")
            result = run("parse", str(project))
            self.assertNotEqual(result.returncode, 0)


class CliEndToEndTests(unittest.TestCase):
    def _new(self, root: Path, template: str) -> Path:
        project = root / template
        result = run(
            "new",
            str(project),
            "--template",
            template,
            "--title",
            f"{template} test",
            "--slug",
            template,
        )
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return project

    def test_import_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = self._new(Path(temp), "import")
            (project / "sources" / "01.md").write_text(CHAPTER, encoding="utf-8")
            self.assertEqual(run("build", str(project), "--single").returncode, 0)
            self.assertTrue((project / "dist" / "import.html").is_file())
            self.assertEqual(run("verify", str(project)).returncode, 0)

    def test_retelling_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = self._new(Path(temp), "retelling")
            (project / "sources" / "01.md").write_text(CHAPTER, encoding="utf-8")
            (project / "retold" / "01.md").write_text(
                CHAPTER.replace("雨还没下。", "雨还没有落下来。"),
                encoding="utf-8",
            )
            config = json.loads((project / "project.json").read_text(encoding="utf-8"))
            config["chapters"] = [
                {
                    "id": "ch1",
                    "order": 1,
                    "files": ["01.md"],
                    "retoldFiles": ["01.md"],
                    "mode": "parts",
                }
            ]
            write_json(project / "project.json", config)
            self.assertEqual(run("build", str(project), "--single").returncode, 0)
            report = json.loads(
                (project / "build" / "parse_report.json").read_text(encoding="utf-8")
            )
            self.assertTrue(report["fidelityByMode"]["ch1:original"])
            self.assertTrue(report["fidelityByMode"]["ch1:retold"])
            self.assertEqual(run("verify", str(project)).returncode, 0)

    def test_creation_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = self._new(Path(temp), "creation")
            (project / "chapters" / "01.md").write_text(CHAPTER, encoding="utf-8")
            self.assertEqual(run("build", str(project), "--single").returncode, 0)
            self.assertTrue((project / "dist" / "creation.html").is_file())
            self.assertEqual(run("verify", str(project)).returncode, 0)

    def test_built_site_includes_new_pages_and_stays_offline(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = self._new(Path(temp), "creation")
            (project / "chapters" / "01.md").write_text(CHAPTER, encoding="utf-8")
            self.assertEqual(run("build", str(project), "--single").returncode, 0)

            index = (project / "site" / "index.html").read_text(encoding="utf-8")
            for asset in (
                "data/timeline.js",
                "data/mentions.js",
                "assets/js/timeline.js",
                "assets/js/glossary.js",
                "assets/css/pages.css",
            ):
                self.assertIn(asset, index)

            single = (project / "dist" / "creation.html").read_text(encoding="utf-8")
            for marker in (
                "STORY_TIMELINE",
                "STORY_MENTIONS",
                "timeline-page",
                "glossary-page",
                "findPath",
            ):
                self.assertIn(marker, single)
            for forbidden in (
                '<script src="http',
                '<link rel="stylesheet" href="http',
                '<img src="http',
            ):
                self.assertNotIn(forbidden, single)


if __name__ == "__main__":
    unittest.main()
