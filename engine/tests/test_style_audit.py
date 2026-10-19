#!/usr/bin/env python3
"""Tests for Story Forge style metrics and content audit."""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ENGINE = Path(__file__).resolve().parent.parent
TOOLS = ENGINE / "tools"
if str(TOOLS) not in sys.path:
    sys.path.insert(0, str(TOOLS))

import audit_content  # noqa: E402
import style_lint  # noqa: E402

HANZI_RE = re.compile(r"[一-鿿]")


# ------------------------------------------------------------------ fixtures


def write_project(
    root: Path,
    chapters: list[dict] | None,
    *,
    project: dict | None = None,
    entities: dict | None = None,
    meta: dict | None = None,
    illustrations: list[dict] | None = None,
    timeline: dict | None = None,
    files: dict[str, str] | None = None,
) -> Path:
    project_dir = root / "proj"
    project_dir.mkdir(parents=True, exist_ok=True)
    config = {
        "slug": "test",
        "title": "测试项目",
        "sourceDir": "sources",
        "siteDir": "site",
        "dataDir": "site/data",
        "chapters": [],
    }
    config.update(project or {})
    (project_dir / "project.json").write_text(
        json.dumps(config, ensure_ascii=False), encoding="utf-8"
    )
    content = project_dir / "content"
    content.mkdir(exist_ok=True)
    (content / "entities.json").write_text(
        json.dumps(
            entities if entities is not None else {"entities": [], "relations": []},
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (content / "chapter_meta.json").write_text(
        json.dumps(meta if meta is not None else {}, ensure_ascii=False),
        encoding="utf-8",
    )
    if illustrations is not None:
        (content / "illustrations.json").write_text(
            json.dumps({"images": illustrations}, ensure_ascii=False),
            encoding="utf-8",
        )
    if timeline is not None:
        (content / "timeline.json").write_text(
            json.dumps(timeline, ensure_ascii=False), encoding="utf-8"
        )
    if chapters is not None:
        build = project_dir / "build"
        build.mkdir(exist_ok=True)
        (build / "chapters.json").write_text(
            json.dumps(chapters, ensure_ascii=False), encoding="utf-8"
        )
    for relative, text in (files or {}).items():
        path = project_dir / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return project_dir


def make_variant(sections: dict[str, list[str]]) -> dict:
    rendered = [
        {
            "id": section_id,
            "title": "",
            "blocks": [
                {"type": "p", "text": text, "html": text} for text in texts
            ],
        }
        for section_id, texts in sections.items()
    ]
    return {"parts": [{"id": "p1", "title": "", "sections": rendered}]}


def count_hanzi(texts: dict[str, list[str]]) -> int:
    return sum(
        len(HANZI_RE.findall(text))
        for texts_for_section in texts.values()
        for text in texts_for_section
    )


def make_chapter(
    chapter_id: str,
    order: int,
    modes: dict[str, dict[str, list[str]]],
    default_mode: str | None = None,
) -> dict:
    variants = {mode: make_variant(sections) for mode, sections in modes.items()}
    hanzi_by_mode = {
        mode: count_hanzi(sections) for mode, sections in modes.items()
    }
    base = {
        "id": chapter_id,
        "order": order,
        "title": chapter_id,
        "subtitle": "",
    }
    if len(variants) == 1:
        mode = next(iter(variants))
        return {
            **base,
            "modeNames": [mode],
            "defaultMode": mode,
            "parts": variants[mode]["parts"],
            "hanzi": hanzi_by_mode[mode],
            "hanziByMode": hanzi_by_mode,
        }
    default = default_mode or list(variants)[-1]
    return {
        **base,
        "modeNames": list(variants),
        "defaultMode": default,
        "variants": variants,
        "hanzi": hanzi_by_mode[default],
        "hanziByMode": hanzi_by_mode,
    }


def make_entity(
    entity_id: str,
    name: str,
    *,
    spoiler: int = 1,
    first: int = 1,
    summary: str = "",
    tagline: str = "",
    aliases: list[str] | None = None,
    evidence: list[dict] | None = None,
) -> dict:
    return {
        "id": entity_id,
        "type": "character",
        "name": name,
        "aliases": aliases if aliases is not None else [name],
        "tagline": tagline,
        "summary": summary,
        "spoilerFrom": spoiler,
        "firstAppear": first,
        "evidence": evidence or [],
    }


def evidence(chapter: str, section: str | None, quote: str) -> dict:
    entry = {"chapter": chapter, "quote": quote}
    if section is not None:
        entry["section"] = section
    return entry


def run_tool(
    script: str, project: Path, *flags: str
) -> subprocess.CompletedProcess[str]:
    env = dict(os.environ)
    env["PYTHONIOENCODING"] = "utf-8"
    return subprocess.run(
        [sys.executable, str(TOOLS / script), str(project), *flags],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
        timeout=60,
    )


def joined(items: list[str]) -> str:
    return "\n".join(items)


# --------------------------------------------------------------- style metrics


class StyleMetricTests(unittest.TestCase):
    def test_compute_metrics_arithmetic(self) -> None:
        metrics = style_lint.compute_metrics(
            ["我们走吧。他们留下。", "「好。」"]
        )
        self.assertEqual(metrics["hanzi"], 9)
        self.assertEqual(metrics["paragraphs"], 2)
        self.assertEqual(metrics["sentences"], 3)
        self.assertAlmostEqual(metrics["avgSentenceHanzi"], 3.0)
        self.assertAlmostEqual(metrics["medianSentenceHanzi"], 4.0)
        self.assertAlmostEqual(metrics["p90SentenceHanzi"], 4.0)
        self.assertAlmostEqual(metrics["dialogueParagraphRatio"], 0.5)
        self.assertAlmostEqual(metrics["avgParagraphHanzi"], 4.5)
        self.assertAlmostEqual(metrics["punctuation"]["。"], 1.0)
        self.assertEqual(metrics["person"], "mixed")
        self.assertAlmostEqual(metrics["longSentenceRatio"], 0.0)

    def test_person_detection(self) -> None:
        first = style_lint.compute_metrics(["我走了。我们留下。"])
        third = style_lint.compute_metrics(["他走了。他们留下。"])
        self.assertEqual(first["person"], "first")
        self.assertEqual(third["person"], "third")

    def test_style_drift_detection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            chapters = [
                make_chapter(
                    "ch1",
                    1,
                    {
                        "original": {"s1": ["一二三四。五六七八。"]},
                        "retold": {
                            "s1": [
                                "一二三四五六七八九十。一二三四五六七八九十。",
                                "“好。”",
                            ]
                        },
                    },
                )
            ]
            project = write_project(
                Path(tmp),
                chapters,
                project={
                    "kind": "retelling",
                    "modes": ["original", "retold"],
                    "primaryMode": "original",
                    "sourceDir": "sources",
                    "retoldDir": "retold",
                },
            )
            result = run_tool("style_lint.py", project, "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["baseline"]["mode"], "original")
            self.assertAlmostEqual(
                report["baseline"]["metrics"]["avgSentenceHanzi"], 4.0
            )
            warnings = joined(report["warnings"])
            self.assertIn("平均句长漂移", warnings)
            self.assertIn("对话段落比例", warnings)
            self.assertTrue((project / "build" / "style_report.json").exists())

    def test_style_banned_phrase_strict_and_no_metrics(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            entities = {
                "entities": [
                    make_entity(
                        "a",
                        "甲",
                        summary="这不是失去，而是另一种开始。",
                    )
                ],
                "relations": [],
            }
            project = write_project(Path(tmp), None, entities=entities)
            result = run_tool(
                "style_lint.py", project, "--json", "--no-metrics"
            )
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertIsNone(report["baseline"])
            self.assertEqual(report["modes"], {})
            self.assertIn("对称金句", joined(report["warnings"]))

            strict = run_tool(
                "style_lint.py", project, "--strict", "--no-metrics"
            )
            self.assertEqual(strict.returncode, 1)
            self.assertTrue(
                (project / "build" / "style_report.json").exists()
            )

    def test_style_source_fallback_without_build(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = write_project(
                Path(tmp),
                None,
                project={
                    "kind": "import",
                    "modes": ["original"],
                    "primaryMode": "original",
                    "sourceDir": "sources",
                    "chapters": [
                        {"id": "ch1", "order": 1, "files": ["01.md"]}
                    ],
                },
                files={
                    "sources/01.md": "# 第一章\n\n一二三四。五六七八。\n"
                },
            )
            result = run_tool("style_lint.py", project, "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertEqual(report["baseline"]["mode"], "original")
            self.assertEqual(report["baseline"]["metrics"]["hanzi"], 8)

    def test_style_json_purity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = write_project(Path(tmp), None)
            result = run_tool("style_lint.py", project, "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            payload = json.loads(result.stdout)
            self.assertIn("warnings", payload)


# --------------------------------------------------------------------- audit


class AuditEvidenceTests(unittest.TestCase):
    def test_missing_evidence_warning_and_strict(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            entities = {
                "entities": [make_entity("a", "甲")],
                "relations": [],
            }
            chapters = [
                make_chapter(
                    "ch1", 1, {"original": {"s1": ["甲走进灯塔。"]}}
                )
            ]
            project = write_project(
                Path(tmp),
                chapters,
                entities=entities,
                project={"primaryMode": "original"},
            )
            result = run_tool("audit_content.py", project, "--json")
            self.assertEqual(result.returncode, 0, result.stderr)
            report = json.loads(result.stdout)
            self.assertIn("没有任何证据", joined(report["warnings"]))
            self.assertEqual(report["stats"]["entities"], 1)
            self.assertEqual(report["stats"]["evidence"], 0)

            strict = run_tool("audit_content.py", project, "--strict")
            self.assertEqual(strict.returncode, 1)

    def test_quote_without_section(self) -> None:
        cases = [
            (
                "unique",
                {"s1": ["甲乙丙丁戊己出现在这里。"], "s2": ["别的内容。"]},
                "甲乙丙丁戊己",
                "info",
                "唯一解析",
            ),
            (
                "multiple",
                {"s1": ["重复引文测试一次。"], "s2": ["重复引文测试两次。"]},
                "重复引文测试",
                "errors",
                "匹配多个小节",
            ),
            (
                "none",
                {"s1": ["这里什么也没有。"]},
                "完全找不到的句子",
                "errors",
                "无法在",
            ),
        ]
        for name, sections, quote, bucket, needle in cases:
            with self.subTest(case=name), tempfile.TemporaryDirectory() as tmp:
                entities = {
                    "entities": [
                        make_entity(
                            "a",
                            "甲",
                            evidence=[evidence("ch1", None, quote)],
                        )
                    ],
                    "relations": [],
                }
                chapters = [make_chapter("ch1", 1, {"original": sections})]
                project = write_project(
                    Path(tmp),
                    chapters,
                    entities=entities,
                    project={"primaryMode": "original"},
                )
                result = run_tool("audit_content.py", project, "--json")
                report = json.loads(result.stdout)
                self.assertIn(needle, joined(report[bucket]))
                expected_code = 0 if bucket == "info" else 1
                self.assertEqual(result.returncode, expected_code)

    def test_short_and_duplicate_quotes(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            entities = {
                "entities": [
                    make_entity(
                        "a",
                        "甲",
                        evidence=[
                            evidence("ch1", "s1", "甲乙丙"),
                            evidence("ch1", "s1", "甲乙丙"),
                        ],
                    )
                ],
                "relations": [],
            }
            chapters = [make_chapter("ch1", 1, {"original": {"s1": ["甲乙丙丁。"]}})]
            project = write_project(
                Path(tmp),
                chapters,
                entities=entities,
                project={"primaryMode": "original"},
            )
            result = run_tool("audit_content.py", project, "--json")
            report = json.loads(result.stdout)
            warnings = joined(report["warnings"])
            self.assertIn("不足 6 个汉字", warnings)
            self.assertIn("重复引文", warnings)
            self.assertEqual(result.returncode, 0)

    def test_explicit_section_mismatch_is_error(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            entities = {
                "entities": [
                    make_entity(
                        "a",
                        "甲",
                        evidence=[evidence("ch1", "s9", "甲乙丙丁戊己")],
                    )
                ],
                "relations": [],
            }
            chapters = [
                make_chapter("ch1", 1, {"original": {"s1": ["甲乙丙丁戊己。"]}})
            ]
            project = write_project(
                Path(tmp),
                chapters,
                entities=entities,
                project={"primaryMode": "original"},
            )
            result = run_tool("audit_content.py", project, "--json")
            self.assertEqual(result.returncode, 1)
            report = json.loads(result.stdout)
            self.assertIn("section 不存在", joined(report["errors"]))


class AuditContentTests(unittest.TestCase):
    def test_spoiler_leaks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            entities = {
                "entities": [
                    make_entity(
                        "a",
                        "甲",
                        summary="甲和乙一起出发。",
                        evidence=[
                            evidence("ch1", "s1", "甲和乙一起出发")
                        ],
                    ),
                    make_entity(
                        "b",
                        "乙",
                        spoiler=2,
                        first=2,
                        summary="乙在后面。",
                        evidence=[evidence("ch1", "s1", "乙在后面")],
                    ),
                ],
                "relations": [
                    {
                        "from": "a",
                        "to": "b",
                        "label": "同行",
                        "spoilerFrom": 1,
                    }
                ],
            }
            chapters = [
                make_chapter(
                    "ch1",
                    1,
                    {"original": {"s1": ["甲和乙一起出发。乙在后面。"]}},
                )
            ]
            project = write_project(
                Path(tmp),
                chapters,
                entities=entities,
                project={"primaryMode": "original"},
            )
            result = run_tool("audit_content.py", project, "--json")
            report = json.loads(result.stdout)
            warnings = joined(report["warnings"])
            self.assertIn("可能剧透", warnings)
            self.assertIn("小于端点 firstAppear", warnings)
            self.assertEqual(result.returncode, 0)

    def test_relations_duplicate_self_unknown_and_isolated(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            entities = {
                "entities": [
                    make_entity(
                        "a",
                        "甲",
                        evidence=[evidence("ch1", "s1", "甲乙两人都在场")],
                    ),
                    make_entity(
                        "b",
                        "乙",
                        evidence=[evidence("ch1", "s1", "甲乙两人都在场")],
                    ),
                    make_entity("c", "丙", evidence=[]),
                ],
                "relations": [
                    {"from": "a", "to": "b", "label": "同行", "spoilerFrom": 1},
                    {"from": "a", "to": "b", "label": "同行", "spoilerFrom": 1},
                    {"from": "a", "to": "a", "label": "自环", "spoilerFrom": 1},
                    {"from": "a", "to": "ghost", "label": "未知", "spoilerFrom": 1},
                ],
            }
            chapters = [
                make_chapter(
                    "ch1", 1, {"original": {"s1": ["甲乙两人都在场。"]}}
                )
            ]
            project = write_project(
                Path(tmp),
                chapters,
                entities=entities,
                project={"primaryMode": "original"},
            )
            result = run_tool("audit_content.py", project, "--json")
            self.assertEqual(result.returncode, 1)
            report = json.loads(result.stdout)
            warnings = joined(report["warnings"])
            errors = joined(report["errors"])
            self.assertIn("重复关系", warnings)
            self.assertIn("关系自环", warnings)
            self.assertIn("完全孤立", warnings)
            self.assertIn("端点未知", errors)

    def test_section_misalignment_and_hanzi_ratio(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            chapters = [
                make_chapter(
                    "ch1",
                    1,
                    {
                        "original": {
                            "s1": ["一二三四五六七八九十。"],
                            "s2": ["十一十二二十三十四十五。"],
                        },
                        "retold": {"s1": ["一。"], "s3": ["二。"]},
                    },
                )
            ]
            project = write_project(
                Path(tmp),
                chapters,
                project={
                    "kind": "retelling",
                    "modes": ["original", "retold"],
                    "primaryMode": "original",
                },
            )
            result = run_tool("audit_content.py", project, "--json")
            self.assertEqual(result.returncode, 1)
            report = json.loads(result.stdout)
            errors = joined(report["errors"])
            warnings = joined(report["warnings"])
            self.assertIn("section 序列不一致", errors)
            self.assertIn("缺失 ['s2']", errors)
            self.assertIn("多余 ['s3']", errors)
            self.assertIn("字数比", warnings)

    def test_chapter_metadata_and_empty_chapter(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            chapters = [
                make_chapter("ch1", 1, {"original": {"s1": ["第一章正文。"]}}),
                make_chapter("ch2", 2, {"original": {"s1": ["第二章正文。"]}}),
                {
                    "id": "ch3",
                    "order": 3,
                    "modeNames": ["original"],
                    "defaultMode": "original",
                    "parts": [],
                    "hanzi": 0,
                    "hanziByMode": {"original": 0},
                },
            ]
            project = write_project(
                Path(tmp),
                chapters,
                meta={"ch2": {"hook": "钩子"}},
                project={
                    "primaryMode": "original",
                    "ready": ["ch1", "ch2"],
                },
            )
            result = run_tool("audit_content.py", project, "--json")
            self.assertEqual(result.returncode, 1)
            report = json.loads(result.stdout)
            warnings = joined(report["warnings"])
            errors = joined(report["errors"])
            self.assertIn("ready 章节 ch1 缺 chapter_meta", warnings)
            self.assertIn("章节 ch2 缺 cast", warnings)
            self.assertIn("章节 ch3 正文为空或 0 小节", errors)

    def test_illustration_checks(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            chapters = [
                make_chapter("ch1", 1, {"original": {"s1": ["正文。"]}})
            ]
            images = [
                {
                    "id": "i1",
                    "file": "assets/img/missing.png",
                    "alt": "",
                    "chapter": "ch1",
                    "section": "s1",
                },
                {
                    "id": "i2",
                    "file": "assets/img/a.png",
                    "alt": "图",
                    "chapter": "ch1",
                    "section": "s1",
                },
                {
                    "id": "i3",
                    "file": "assets/img/a.png",
                    "alt": "图",
                    "chapter": "ch1",
                    "section": "s1",
                },
                {
                    "id": "i4",
                    "file": "assets/img/b.png",
                    "alt": "图",
                    "sourceUrl": "https://example.com/b.png",
                    "chapter": "ch1",
                    "section": "s1",
                },
                {
                    "id": "i5",
                    "file": "assets/img/c.png",
                    "alt": "图",
                    "chapter": "ch1",
                },
                {
                    "id": "i6",
                    "file": "assets/img/c.png",
                    "alt": "图",
                    "chapter": "ch9",
                    "section": "s1",
                },
            ]
            project = write_project(
                Path(tmp),
                chapters,
                illustrations=images,
                project={"primaryMode": "original"},
                files={
                    "assets/img/a.png": "a",
                    "assets/img/b.png": "b",
                    "assets/img/c.png": "c",
                },
            )
            result = run_tool("audit_content.py", project, "--json")
            self.assertEqual(result.returncode, 1)
            report = json.loads(result.stdout)
            errors = joined(report["errors"])
            warnings = joined(report["warnings"])
            self.assertIn("文件不存在", errors)
            self.assertIn("缺 alt", errors)
            self.assertIn("缺 credit", errors)
            self.assertIn("缺 license", errors)
            self.assertIn("未分配 section", errors)
            self.assertIn("重复 file", warnings)
            self.assertIn("未被任何章节引用", warnings)

    def test_volumes_and_timeline(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            chapters = [
                make_chapter(
                    "ch1",
                    1,
                    {"original": {"s1": ["证据文本在这里。"]}},
                )
            ]
            chapters[0]["volume"] = "vol2"
            entities = {
                "entities": [
                    make_entity(
                        "a",
                        "甲",
                        evidence=[evidence("ch1", "s1", "证据文本在这里")],
                    )
                ],
                "relations": [],
            }
            timeline = {
                "events": [
                    {
                        "id": "ev1",
                        "title": "事件一",
                        "chapter": "ch1",
                        "order": 1,
                        "spoilerFrom": 5,
                        "entities": ["a"],
                        "causes": ["ev2"],
                        "evidence": [],
                    },
                    {
                        "id": "ev2",
                        "title": "事件二",
                        "chapter": "ch9",
                        "order": 2,
                        "causes": ["ev1"],
                    },
                    {"id": "ev1", "title": "重复", "chapter": "ch1"},
                ]
            }
            project = write_project(
                Path(tmp),
                chapters,
                entities=entities,
                timeline=timeline,
                project={
                    "primaryMode": "original",
                    "volumes": [
                        {"id": "vol1", "title": "第一卷", "chapters": ["ch1"]}
                    ],
                },
            )
            result = run_tool("audit_content.py", project, "--json")
            self.assertEqual(result.returncode, 1)
            report = json.loads(result.stdout)
            errors = joined(report["errors"])
            warnings = joined(report["warnings"])
            self.assertIn("未知 volume id", errors)
            self.assertIn("事件 id 重复", errors)
            self.assertIn("引用未知章节", errors)
            self.assertIn("存在环", errors)
            self.assertIn("大于锚点", warnings)

    def test_candidate_extraction(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            text = "黑鸦来了。黑鸦走了。黑鸦看着海。"
            chapters = [
                make_chapter("ch1", 1, {"original": {"s1": [text]}}),
                make_chapter("ch2", 2, {"original": {"s1": [text]}}),
            ]
            project = write_project(
                Path(tmp),
                chapters,
                project={"primaryMode": "original"},
            )
            result = run_tool("audit_content.py", project, "--json")
            report = json.loads(result.stdout)
            names = {candidate["name"]: candidate for candidate in report["candidates"]}
            self.assertIn("黑鸦", names)
            self.assertEqual(names["黑鸦"]["count"], 6)
            self.assertEqual(names["黑鸦"]["chapters"], ["ch1", "ch2"])
            self.assertEqual(result.returncode, 0)

    def test_annotation_coverage_info(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            chapter = {
                "id": "ch1",
                "order": 1,
                "title": "ch1",
                "subtitle": "",
                "modeNames": ["original"],
                "defaultMode": "original",
                "parts": [
                    {
                        "id": "p1",
                        "title": "",
                        "sections": [
                            {
                                "id": "s1",
                                "title": "",
                                "blocks": [
                                    {
                                        "type": "p",
                                        "text": "甲乙丙丁。",
                                        "html": '<a class="ent" data-ent="a">甲</a>乙丙丁。',
                                    }
                                ],
                            }
                        ],
                    }
                ],
                "hanzi": 5,
                "hanziByMode": {"original": 5},
            }
            entities = {
                "entities": [
                    make_entity(
                        "a",
                        "甲",
                        evidence=[evidence("ch1", "s1", "甲乙丙丁")],
                    )
                ],
                "relations": [],
            }
            project = write_project(
                Path(tmp),
                [chapter],
                entities=entities,
                project={"primaryMode": "original"},
            )
            result = run_tool("audit_content.py", project, "--json")
            report = json.loads(result.stdout)
            info = joined(report["info"])
            self.assertIn("data-ent 1 处", info)
            self.assertIn("实体名出现 1 次", info)
            self.assertEqual(result.returncode, 0)

    def test_missing_chapters_degrades_and_json_purity(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            project = write_project(Path(tmp), None)
            result = run_tool("audit_content.py", project, "--json")
            self.assertEqual(result.returncode, 1)
            report = json.loads(result.stdout)
            self.assertIn("请先运行 parse", joined(report["errors"]))
            self.assertEqual(report["candidates"], [])


if __name__ == "__main__":
    unittest.main()
