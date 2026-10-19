#!/usr/bin/env python3
"""Integration tests for the three Story Forge modes and illustrations."""
from __future__ import annotations

import base64
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
TOOLS = ENGINE / "tools"
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAusB9Wl2n0kAAAAASUVORK5CYII="
)


def write_project(root: Path, kind: str, chapters: list[dict], source_dir: str,
                  retold_dir: str | None = None, images: list[dict] | None = None) -> Path:
    project = root / kind
    project.mkdir(parents=True)
    config = {
        "slug": kind,
        "title": f"{kind} test",
        "subtitle": "test",
        "description": "",
        "lede": "",
        "sourceDir": source_dir,
        "siteDir": "site",
        "dataDir": "site/data",
        "kind": kind,
        "modes": ["original"] if kind == "import" else (["original", "retold"] if kind == "retelling" else ["retold"]),
        "defaultMode": "original" if kind == "import" else "retold",
        "primaryMode": "retold" if kind == "creation" else "original",
        "modeLabels": {"original": "原文", "retold": "复述"},
        "illustrations": {"enabled": True, "dir": "assets/img", "maxPerChapter": 2},
        "chapters": chapters,
        "ready": [],
    }
    if retold_dir:
        config["retoldDir"] = retold_dir
    (project / "project.json").write_text(json.dumps(config, ensure_ascii=False), encoding="utf-8")
    content = project / "content"
    content.mkdir()
    (content / "entities.json").write_text(
        json.dumps(
            {
                "entities": [
                    {
                        "id": "shenzhou",
                        "type": "character",
                        "name": "沈舟",
                        "aliases": ["沈舟"],
                        "tagline": "守夜人",
                        "summary": "灯塔的守夜人。",
                        "spoilerFrom": 1,
                        "firstAppear": 1,
                        "icon": "沈",
                        "color": "#e23a4e",
                        "evidence": [
                            {
                                "chapter": "ch1",
                                "section": "sch1-0-1",
                                "quote": "沈舟走进灯塔",
                                "note": "登场",
                            }
                        ],
                    }
                ],
                "relations": [],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (content / "chapter_meta.json").write_text(
        json.dumps(
            {
                "ch1": {
                    "codename": "TEST",
                    "hook": "灯塔。",
                    "readingMinutes": 1,
                    "cast": ["shenzhou"],
                    "takeaways": ["沈舟走进灯塔"],
                    "newTerms": [],
                }
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (content / "recap.json").write_text(
        json.dumps({"eras": [], "whereYouAre": {}}, ensure_ascii=False), encoding="utf-8"
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
    (project / "assets" / "img").mkdir(parents=True)
    return project


def run(script: Path, project: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(script), str(project)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


class ModeTests(unittest.TestCase):
    def test_import_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = write_project(
                Path(tmp),
                "import",
                [{"id": "ch1", "order": 1, "title": "第一章", "files": ["01.md"]}],
                "sources",
            )
            (project / "sources" / "01.md").write_text(
                "# 第一章 测试\n\n## 第一幕\n\n### 场景一\n\n沈舟走进灯塔。\n",
                encoding="utf-8",
            )
            result = run(TOOLS / "parse_chapters.py", project)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            data = json.loads((project / "build" / "chapters.json").read_text(encoding="utf-8"))[0]
            self.assertEqual(data["modeNames"], ["original"])
            self.assertIn("parts", data)
            self.assertNotIn("variants", data)

    def test_retelling_dual_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = write_project(
                Path(tmp),
                "retelling",
                [
                    {
                        "id": "ch1",
                        "order": 1,
                        "title": "第一章",
                        "files": ["01.md"],
                        "retoldFiles": ["01.md"],
                    }
                ],
                "sources",
                "retold",
            )
            original = "# 第一章 测试\n\n## 第一幕\n\n### 场景一\n\n沈舟走进灯塔。林岚在等他。\n"
            retold = "# 第一章 测试\n\n## 第一幕\n\n### 场景一\n\n沈舟到灯塔接班。\n"
            (project / "sources" / "01.md").write_text(original, encoding="utf-8")
            (project / "retold" / "01.md").write_text(retold, encoding="utf-8")
            image = {
                "id": "img-1",
                "file": "assets/img/scene.png",
                "alt": "灯塔",
                "caption": "场景",
                "credit": "本地提供",
                "license": "user-provided",
                "sourceUrl": "",
                "chapter": "ch1",
                "section": "sch1-0-1",
                "afterBlock": 0,
                "mode": "both",
            }
            (project / "content" / "illustrations.json").write_text(
                json.dumps({"images": [image]}, ensure_ascii=False), encoding="utf-8"
            )
            (project / "assets" / "img" / "scene.png").write_bytes(PNG)
            result = run(TOOLS / "parse_chapters.py", project)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            data = json.loads((project / "build" / "chapters.json").read_text(encoding="utf-8"))[0]
            self.assertEqual(data["modeNames"], ["original", "retold"])
            self.assertIn("variants", data)
            self.assertNotIn("parts", data)
            for mode in ("original", "retold"):
                blocks = data["variants"][mode]["parts"][0]["sections"][0]["blocks"]
                self.assertEqual(blocks[0]["type"], "image")

    def test_creation_mode(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = write_project(
                Path(tmp),
                "creation",
                [{"id": "ch1", "order": 1, "title": "第一章", "files": ["01.md"]}],
                "chapters",
            )
            (project / "chapters" / "01.md").write_text(
                "# 第一章 测试\n\n## 第一幕\n\n### 场景一\n\n沈舟走进灯塔。\n",
                encoding="utf-8",
            )
            result = run(TOOLS / "parse_chapters.py", project)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            data = json.loads((project / "build" / "chapters.json").read_text(encoding="utf-8"))[0]
            self.assertEqual(data["modeNames"], ["retold"])
            self.assertIn("parts", data)

    def test_singlefile_inlines_images(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = write_project(
                Path(tmp),
                "retelling",
                [
                    {
                        "id": "ch1",
                        "order": 1,
                        "title": "第一章",
                        "files": ["01.md"],
                        "retoldFiles": ["01.md"],
                    }
                ],
                "sources",
                "retold",
                images=[
                    {
                        "id": "img-1",
                        "file": "assets/img/scene.png",
                        "alt": "灯塔",
                        "caption": "",
                        "credit": "本地提供",
                        "license": "user-provided",
                        "sourceUrl": "",
                        "chapter": "ch1",
                        "section": "sch1-0-1",
                        "afterBlock": 0,
                        "mode": "both",
                    }
                ],
            )
            (project / "sources" / "01.md").write_text(
                "# 第一章 测试\n\n## 第一幕\n\n### 场景一\n\n沈舟走进灯塔。\n", encoding="utf-8"
            )
            (project / "retold" / "01.md").write_text(
                "# 第一章 测试\n\n## 第一幕\n\n### 场景一\n\n沈舟到灯塔。\n", encoding="utf-8"
            )
            (project / "assets" / "img" / "scene.png").write_bytes(PNG)
            parsed = run(TOOLS / "parse_chapters.py", project)
            self.assertEqual(parsed.returncode, 0, parsed.stdout + parsed.stderr)
            built = subprocess.run(
                [sys.executable, str(TOOLS / "build_project.py"), str(project), "--single"],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(built.returncode, 0, built.stdout + built.stderr)
            html = (project / "dist" / "retelling.html").read_text(encoding="utf-8")
            self.assertIn("window.STORY_IMAGES=", html)
            self.assertIn('"assets/img/scene.png":"data:image/png;base64,', html)


if __name__ == "__main__":
    unittest.main()
