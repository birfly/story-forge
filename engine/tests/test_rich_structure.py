#!/usr/bin/env python3
"""Integration tests for variants, volumes, timeline, mentions and evidence."""
from __future__ import annotations

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
TOOLS = ENGINE / "tools"
JS_VALUE = re.compile(r"window\.[A-Z_]+ = (.*);\s*$", re.S)


def write_json(path: Path, payload: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")


def read_js(path: Path) -> object:
    text = path.read_text(encoding="utf-8")
    match = JS_VALUE.search(text)
    if not match:
        raise AssertionError(f"not a generated data file: {path}")
    return json.loads(match.group(1))


def base_content(evidence: dict | None = None, manual: list[dict] | None = None) -> None:
    pass


def make_project(root: Path) -> Path:
    project = root / "project"
    project.mkdir(parents=True)
    config = {
        "slug": "rich",
        "title": "结构测试",
        "subtitle": "test",
        "kind": "retelling",
        "sourceDir": "sources",
        "retoldDir": "retold",
        "defaultMode": "original",
        "primaryMode": "original",
        "variants": [
            {"id": "original", "label": "原文", "dir": "sources", "primary": True},
            {"id": "retold", "label": "复述", "dir": "retold"},
            {"id": "en", "label": "English", "dir": "translations/en"},
        ],
        "modeLabels": {"original": "原文", "retold": "复述", "en": "English"},
        "volumes": [
            {"id": "vol1", "title": "第一卷 灯塔", "order": 1, "chapters": ["ch1"]}
        ],
        "chapters": [
            {
                "id": "ch1",
                "order": 1,
                "files": ["01.md"],
                "variantFiles": {"retold": ["01.md"], "en": ["01.en.md"]},
                "mode": "parts",
            }
        ],
        "ready": ["ch1"],
    }
    write_json(project / "project.json", config)

    source = (
        "# 第一章 接班：风暴前\n\n"
        "## 第一幕\n\n"
        "### 开场\n\n"
        "沈舟走进灯塔。雨还没下。\n"
    )
    retold = (
        "# 第一章 接班：风暴前\n\n"
        "## 第一幕\n\n"
        "### 开场\n\n"
        "沈舟推门进了灯塔。雨还没落下来。\n"
    )
    english = (
        "# Chapter 1: Before the Storm\n\n"
        "## Act One\n\n"
        "### Opening\n\n"
        "Shen Zhou walked into the lighthouse.\n"
    )
    for directory, filename, text in (
        (project / "sources", "01.md", source),
        (project / "retold", "01.md", retold),
        (project / "translations" / "en", "01.en.md", english),
    ):
        directory.mkdir(parents=True, exist_ok=True)
        (directory / filename).write_text(text, encoding="utf-8")

    write_json(
        project / "content" / "entities.json",
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
                    "evidence": [
                        {
                            "chapter": "ch1",
                            "quote": "沈舟走进灯塔",
                            "note": "登场",
                        }
                    ],
                },
                {
                    "id": "dengta",
                    "type": "location",
                    "name": "灯塔",
                    "aliases": ["灯塔"],
                    "tagline": "海岸边的灯塔",
                    "summary": "灯塔在海岸边。",
                    "spoilerFrom": 1,
                    "firstAppear": 1,
                    "icon": "塔",
                    "evidence": [],
                },
            ],
            "relations": [
                {
                    "from": "shenzhou",
                    "to": "dengta",
                    "label": "值守",
                    "kind": "contract",
                    "spoilerFrom": 1,
                }
            ],
        },
    )
    write_json(
        project / "content" / "manual_links.json",
        {
            "links": [
                {
                    "chapter": "ch1",
                    "quote": "走进灯塔",
                    "entity": "dengta",
                    "target": "灯塔",
                }
            ]
        },
    )
    write_json(
        project / "content" / "chapter_meta.json",
        {"ch1": {"hook": "接班。", "cast": ["shenzhou"], "takeaways": ["接班"]}},
    )
    write_json(project / "content" / "recap.json", {"eras": [], "whereYouAre": {}})
    write_json(project / "content" / "worldview.json", {"cards": []})
    write_json(project / "content" / "illustrations.json", {"images": []})
    write_json(
        project / "content" / "timeline.json",
        {
            "title": "事件线",
            "events": [
                {
                    "id": "ev1",
                    "title": "接班",
                    "summary": "沈舟接班。",
                    "chapter": "ch1",
                    "storyTime": "16:00",
                    "entities": ["shenzhou"],
                    "causes": [],
                    "consequences": [],
                    "spoilerFrom": 1,
                    "evidence": [{"chapter": "ch1", "quote": "沈舟走进灯塔"}],
                }
            ],
        },
    )
    return project


def run_parse(project: Path) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(TOOLS / "parse_chapters.py"), str(project)],
        capture_output=True,
        text=True,
        encoding="utf-8",
    )


class RichStructureTests(unittest.TestCase):
    def test_new_template_writes_variants_and_source_policy(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = Path(temp) / "new-project"
            result = subprocess.run(
                [
                    sys.executable,
                    str(ENGINE.parent / "scripts" / "story.py"),
                    "new",
                    str(project),
                    "--template",
                    "retelling",
                    "--title",
                    "Template Test",
                    "--slug",
                    "template-test",
                ],
                capture_output=True,
                text=True,
                encoding="utf-8",
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            config = json.loads(
                (project / "project.json").read_text(encoding="utf-8")
            )
            self.assertEqual(config["sourcePolicy"], "required")
            self.assertEqual(
                [variant["id"] for variant in config["variants"]],
                ["original", "retold"],
            )
            self.assertTrue(config["variants"][0]["primary"])
            self.assertTrue((project / "content" / "timeline.json").is_file())
            self.assertTrue(
                (project / "content" / "source_provenance.json").is_file()
            )

    def test_variants_volumes_timeline_mentions(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp))
            result = run_parse(project)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

            config = read_js(project / "site" / "data" / "config.js")
            self.assertEqual(config["modes"], ["original", "retold", "en"])
            self.assertEqual(config["primaryMode"], "original")
            self.assertEqual(config["modeLabels"]["en"], "English")
            self.assertEqual(config["volumes"][0]["chapters"], ["ch1"])

            chapters = read_js(project / "site" / "data" / "chapters.js")
            chapter = chapters[0]
            self.assertEqual(chapter["volume"], "vol1")
            self.assertEqual(chapter["modeNames"], ["original", "retold", "en"])
            self.assertEqual(set(chapter["variants"]), {"original", "retold", "en"})

            report = json.loads(
                (project / "build" / "parse_report.json").read_text(encoding="utf-8")
            )
            self.assertTrue(report["fidelity"])
            self.assertEqual(
                set(report["fidelityByMode"]),
                {"ch1:original", "ch1:retold", "ch1:en"},
            )

            entities = read_js(project / "site" / "data" / "entities.js")
            evidence = entities["entities"][0]["evidence"][0]
            self.assertEqual(evidence["section"], "sch1-0-1")

            timeline = read_js(project / "site" / "data" / "timeline.js")
            self.assertEqual(timeline["events"][0]["id"], "ev1")
            self.assertEqual(
                timeline["events"][0]["evidence"][0]["section"], "sch1-0-1"
            )

            mentions = read_js(project / "site" / "data" / "mentions.js")
            self.assertIn("shenzhou", mentions)
            self.assertEqual(mentions["shenzhou"][0]["chapter"], "ch1")

            generated = (project / "site" / "data" / "chapters.js").read_text(
                encoding="utf-8"
            )
            self.assertIn('data-ent=\\"dengta\\"', generated)

    def test_fidelity_normalization_covers_latin_text(self) -> None:
        from engine.tools import parse_chapters

        normalized = parse_chapters.normalize_for_fidelity(
            "Shen Zhou walked into the lighthouse."
        )
        self.assertEqual(normalized, "ShenZhouwalkedintothelighthouse")
        self.assertNotEqual(
            normalized,
            parse_chapters.normalize_for_fidelity(
                "Shen Zhou into the lighthouse."
            ),
        )
        self.assertEqual(
            parse_chapters.normalize_for_fidelity("沈舟走进灯塔。"), "沈舟走进灯塔"
        )

    def test_timeline_cycle_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp))
            write_json(
                project / "content" / "timeline.json",
                {
                    "events": [
                        {"id": "a", "title": "A", "causes": ["b"]},
                        {"id": "b", "title": "B", "causes": ["a"]},
                    ]
                },
            )
            result = run_parse(project)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("cycle", result.stdout)

    def test_manual_link_ambiguous_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp:
            project = make_project(Path(temp))
            source = (
                "# 第一章 接班\n\n"
                "## 第一幕\n\n"
                "### 开场\n\n"
                "沈舟走进灯塔。\n\n"
                "### 第二场\n\n"
                "沈舟又走进灯塔。\n"
            )
            (project / "sources" / "01.md").write_text(source, encoding="utf-8")
            (project / "retold" / "01.md").write_text(source, encoding="utf-8")
            result = run_parse(project)
            self.assertNotEqual(result.returncode, 0)
            self.assertIn("ambiguous", result.stdout)


if __name__ == "__main__":
    unittest.main()
