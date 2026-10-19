#!/usr/bin/env python3
"""Tests for source availability / provenance checks."""
from __future__ import annotations

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parent.parent / "tools"


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def make_project(root: Path, kind: str = "retelling", with_source: bool = False) -> Path:
    project = root / "project"
    project.mkdir(parents=True)
    source_dir = "chapters" if kind == "creation" else "sources"
    config = {
        "slug": "source-test",
        "title": "测试作品",
        "kind": kind,
        "sourceDir": source_dir,
        "sourcePolicy": "optional" if kind == "creation" else "required",
    }
    if kind == "retelling":
        config["retoldDir"] = "retold"
    write_json(project / "project.json", config)
    (project / "content").mkdir()
    if with_source:
        (project / source_dir).mkdir()
        (project / source_dir / "01.md").write_text(
            "# 第一章\n\n正文。\n", encoding="utf-8"
        )
    return project


def run(project: Path, *flags: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOLS / "source_check.py"), str(project), *flags],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


class SourceCheckTests(unittest.TestCase):
    def test_missing_source_suggests_search(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp))
            result = run(project, "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            data = json.loads(result.stdout)
            self.assertEqual(data["next"], "search_original")
            self.assertFalse(data["present"])
            self.assertTrue(any("原文" in query for query in data["queries"]))

    def test_present_source_needs_provenance(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp), with_source=True)
            data = json.loads(run(project, "--json").stdout)
            self.assertEqual(data["next"], "record_provenance")

    def test_user_provided_source_is_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp), with_source=True)
            write_json(
                project / "content" / "source_provenance.json",
                {
                    "policy": "required",
                    "entries": [
                        {
                            "id": "source-1",
                            "title": "测试作品",
                            "kind": "primary-text",
                            "license": "user-provided",
                        }
                    ],
                },
            )
            data = json.loads(run(project, "--json").stdout)
            self.assertEqual(data["next"], "ready")
            self.assertEqual(data["provenance"]["rights"], "cleared")

    def test_creation_with_chapters_is_ready(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp), kind="creation", with_source=True)
            data = json.loads(run(project, "--json").stdout)
            self.assertEqual(data["next"], "ready")

    def test_creation_with_based_on_suggests_reference(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp), kind="creation")
            write_json(
                project / "project.json",
                {
                    "title": "同人新作",
                    "kind": "creation",
                    "sourceDir": "chapters",
                    "sourcePolicy": "optional",
                    "basedOn": "原作名",
                },
            )
            data = json.loads(run(project, "--json").stdout)
            self.assertEqual(data["next"], "search_reference")
            self.assertTrue(any("原作名" in query for query in data["queries"]))

    def test_write_template(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp))
            result = run(project, "--write-template")
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertTrue(
                (project / "content" / "source_provenance.json").is_file()
            )
            self.assertTrue((project / "sources" / "PROVENANCE.md").is_file())

    def test_strict_fails_when_source_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp))
            self.assertEqual(run(project, "--strict").returncode, 1)
            write_json(
                project / "content" / "source_provenance.json",
                {"policy": "required", "entries": []},
            )
            (project / "sources").mkdir(exist_ok=True)
            (project / "sources" / "01.md").write_text(
                "# 第一章\n\n正文。\n", encoding="utf-8"
            )
            # Still not ready: no provenance entries.
            self.assertEqual(run(project, "--strict").returncode, 1)

    def test_json_output_is_pure(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp))
            result = run(project, "--json")
            json.loads(result.stdout)

    def test_parse_fails_when_required_source_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp), kind="retelling")
            result = subprocess.run(
                [sys.executable, str(TOOLS / "parse_chapters.py"), str(project)],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(result.returncode, 1)
            self.assertIn("source-check", result.stdout + result.stderr)


if __name__ == "__main__":
    unittest.main()
