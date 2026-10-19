#!/usr/bin/env python3
"""Story Forge CLI — scaffold, build, verify and package story projects.

Examples:
    python scripts/story.py new ./my-story --template retelling --title "…"
    python scripts/story.py parse ./my-story
    python scripts/story.py build ./my-story --single
    python scripts/story.py verify ./my-story
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path

PLUGIN = Path(__file__).resolve().parent.parent
ENGINE = PLUGIN / "engine"
TOOLS = ENGINE / "tools"


def copy_template_content(target: Path) -> None:
    target.mkdir(parents=True, exist_ok=True)
    for source in (ENGINE / "content").glob("*.json"):
        destination = target / source.name
        if not destination.exists():
            shutil.copy2(source, destination)
    style_template = ENGINE / "content" / "style_profile.template.md"
    style_destination = target / "style_profile.md"
    if style_template.exists() and not style_destination.exists():
        shutil.copy2(style_template, style_destination)


TEMPLATE_MODES = {
    "import": {
        "kind": "import",
        "modes": ["original"],
        "defaultMode": "original",
        "primaryMode": "original",
        "sourceDir": "sources",
        "modeLabels": {"original": "原文"},
        "sourcePolicy": "required",
        "variants": [
            {"id": "original", "label": "原文", "dir": "sources", "primary": True}
        ],
    },
    "retelling": {
        "kind": "retelling",
        "modes": ["original", "retold"],
        "defaultMode": "retold",
        "primaryMode": "original",
        "sourceDir": "sources",
        "retoldDir": "retold",
        "modeLabels": {"original": "原文", "retold": "复述"},
        "sourcePolicy": "required",
        "variants": [
            {"id": "original", "label": "原文", "dir": "sources", "primary": True},
            {"id": "retold", "label": "复述", "dir": "retold"},
        ],
    },
    "creation": {
        "kind": "creation",
        "modes": ["retold"],
        "defaultMode": "retold",
        "primaryMode": "retold",
        "sourceDir": "chapters",
        "modeLabels": {"retold": "创作"},
        "sourcePolicy": "optional",
        "variants": [
            {"id": "retold", "label": "创作", "dir": "chapters", "primary": True}
        ],
    },
}


def write_readme(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if not path.exists():
        path.write_text(text, encoding="utf-8")


def cmd_new(args: argparse.Namespace) -> None:
    project = Path(args.path).resolve()
    if project.exists() and any(project.iterdir()):
        raise SystemExit(f"target is not empty: {project}")
    project.mkdir(parents=True, exist_ok=True)
    shutil.copytree(ENGINE / "site", project / "site")
    copy_template_content(project / "content")
    (project / "build").mkdir(exist_ok=True)
    (project / "dist").mkdir(exist_ok=True)
    (project / "assets" / "img").mkdir(parents=True, exist_ok=True)

    mode_config = TEMPLATE_MODES[args.template]
    source_dir = mode_config["sourceDir"]
    (project / source_dir).mkdir(exist_ok=True)
    if args.template == "retelling":
        (project / "retold").mkdir(exist_ok=True)
        write_readme(
            project / "retold" / "README.md",
            "# 复述文本目录\n\n"
            "把复述版章节放在这里，文件名和结构与 `sources/` 一一对应。\n"
            "两个版本使用相同的 H1/H2/H3 结构时，切换阅读模式会停在同一个小节。\n",
        )
    if args.template == "creation":
        write_readme(
            project / source_dir / "README.md",
            "# 章节目录\n\n"
            "把新写的同人章节放在这里。推荐结构：\n\n"
            "```\n# 第一章 标题\n\n## 第一幕 · 幕名\n\n### 场景标题\n\n正文……\n```\n\n"
            "解析器会按 H1/H2/H3 建立章节、部、节。\n",
        )
    else:
        write_readme(
            project / source_dir / "README.md",
            "# 源文本目录\n\n"
            "把已有小说 / 游戏剧情的章节文本放在这里（Markdown）。\n"
            "如果原文是 txt/epub/pdf，先转换成 Markdown，再按 H1/H2/H3 整理。\n",
        )

    config = json.loads((ENGINE / "project.template.json").read_text(encoding="utf-8"))
    config.update(
        {
            "slug": args.slug or project.name,
            "title": args.title or "未命名故事",
            "subtitle": args.subtitle or "富结构故事阅读站",
        }
    )
    config.update(mode_config)
    config.setdefault("volumes", [])
    config["illustrations"] = {
        "enabled": True,
        "dir": "assets/img",
        "autoPlace": True,
        "maxPerChapter": 4,
        "defaultMode": "both",
        "sources": ["local", "wikimedia", "openverse"],
        "licenseAllow": ["public-domain", "cc0", "cc-by", "cc-by-sa"],
    }
    (project / "project.json").write_text(
        json.dumps(config, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    provenance = project / "content" / "source_provenance.json"
    if provenance.exists():
        payload = json.loads(provenance.read_text(encoding="utf-8"))
        payload["policy"] = mode_config.get("sourcePolicy", "required")
        provenance.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    print(f"created {args.template} project: {project}")
    print(f"kind: {mode_config['kind']} · modes: {', '.join(mode_config['modes'])}")
    if mode_config.get("sourcePolicy") == "required":
        print(
            "no source yet? run: "
            f"python scripts/story.py source-check {project}"
        )
    print(f"next: put chapters in {project / source_dir}")
    if args.template == "retelling":
        print(f"      put the retelling in {project / 'retold'}")
    print(f"      python scripts/story.py parse {project}")


def run_tool(command: list[str]) -> None:
    """Run a tool and propagate its exit code to the CLI caller."""
    result = subprocess.run(command, check=False)
    if result.returncode:
        raise SystemExit(result.returncode)


def cmd_parse(args: argparse.Namespace) -> None:
    run_tool(
        [sys.executable, str(TOOLS / "parse_chapters.py"), str(Path(args.path).resolve())]
        + (["--check"] if args.check else [])
    )


def cmd_build(args: argparse.Namespace) -> None:
    command = [
        sys.executable,
        str(TOOLS / "build_project.py"),
        str(Path(args.path).resolve()),
    ]
    if args.single:
        command.append("--single")
    if args.sync_template:
        command.append("--sync-template")
    run_tool(command)


def cmd_verify(args: argparse.Namespace) -> None:
    run_tool(
        [sys.executable, str(TOOLS / "verify.py"), str(Path(args.path).resolve())]
    )


def cmd_status(args: argparse.Namespace) -> None:
    command = [
        sys.executable,
        str(TOOLS / "project_status.py"),
        str(Path(args.path).resolve()),
    ]
    if args.json:
        command.append("--json")
    if args.strict:
        command.append("--strict")
    run_tool(command)


def cmd_ingest(args: argparse.Namespace) -> None:
    command = [
        sys.executable,
        str(TOOLS / "ingest_sources.py"),
        str(Path(args.path).resolve()),
        str(Path(args.source).resolve()),
    ]
    if args.to:
        command.extend(["--to", args.to])
    for flag, enabled in (
        ("--dry-run", args.dry_run),
        ("--force", args.force),
        ("--update-project", args.update_project),
        ("--extract-images", args.extract_images),
        ("--json", args.json),
    ):
        if enabled:
            command.append(flag)
    run_tool(command)


def cmd_audit(args: argparse.Namespace) -> None:
    command = [
        sys.executable,
        str(TOOLS / "audit_content.py"),
        str(Path(args.path).resolve()),
    ]
    if args.json:
        command.append("--json")
    if args.strict:
        command.append("--strict")
    run_tool(command)


def cmd_style(args: argparse.Namespace) -> None:
    command = [
        sys.executable,
        str(TOOLS / "style_lint.py"),
        str(Path(args.path).resolve()),
    ]
    if args.json:
        command.append("--json")
    if args.strict:
        command.append("--strict")
    if args.no_metrics:
        command.append("--no-metrics")
    run_tool(command)


def cmd_source_check(args: argparse.Namespace) -> None:
    command = [
        sys.executable,
        str(TOOLS / "source_check.py"),
        str(Path(args.path).resolve()),
    ]
    if args.json:
        command.append("--json")
    if args.strict:
        command.append("--strict")
    if args.write_template:
        command.append("--write-template")
    if args.record_search:
        command.append("--record-search")
        if args.outcome:
            command.extend(["--outcome", args.outcome])
        for query in args.query or []:
            command.extend(["--query", query])
        for candidate in args.candidate or []:
            command.extend(["--candidate", candidate])
        if args.notes:
            command.extend(["--notes", args.notes])
    run_tool(command)


def cmd_single(args: argparse.Namespace) -> None:
    run_tool(
        [sys.executable, str(TOOLS / "build_singlefile.py"), str(Path(args.path).resolve())]
    )


def cmd_place_images(args: argparse.Namespace) -> None:
    command = [
        sys.executable,
        str(TOOLS / "place_illustrations.py"),
        str(Path(args.path).resolve()),
    ]
    if args.apply:
        command.append("--apply")
    if args.chapter:
        command.extend(["--chapter", args.chapter])
    if args.max_per_chapter:
        command.extend(["--max-per-chapter", str(args.max_per_chapter)])
    run_tool(command)


def cmd_fetch_images(args: argparse.Namespace) -> None:
    command = [
        sys.executable,
        str(TOOLS / "fetch_illustrations.py"),
        str(Path(args.path).resolve()),
    ]
    for flag, value in (
        ("--query", args.query),
        ("--chapter", args.chapter),
        ("--section", args.section),
        ("--source", args.source),
        ("--local-dir", args.local_dir),
        ("--id", args.image_id),
    ):
        if value:
            command.extend([flag, value])
    command.extend(["--limit", str(args.limit)])
    command.extend(["--min-width", str(args.min_width)])
    command.extend(["--after-block", str(args.after_block)])
    command.extend(["--mode", args.mode])
    if args.dry_run:
        command.append("--dry-run")
    run_tool(command)


def main() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    parser = argparse.ArgumentParser(prog="story.py", description="Story Forge CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    new = sub.add_parser("new", help="scaffold a new project")
    new.add_argument("path")
    new.add_argument(
        "--template",
        choices=["import", "retelling", "creation"],
        default="import",
        help="import: 原文放入; retelling: 复述; creation: 新建同人",
    )
    new.add_argument("--title")
    new.add_argument("--subtitle")
    new.add_argument("--slug")
    new.set_defaults(func=cmd_new)

    parse = sub.add_parser("parse", help="parse chapters and build data")
    parse.add_argument("path")
    parse.add_argument("--check", action="store_true")
    parse.set_defaults(func=cmd_parse)

    build = sub.add_parser("build", help="parse + build the site")
    build.add_argument("path")
    build.add_argument("--single", action="store_true")
    build.add_argument("--sync-template", action="store_true")
    build.set_defaults(func=cmd_build)

    verify = sub.add_parser("verify", help="run fidelity + offline checks")
    verify.add_argument("path")
    verify.set_defaults(func=cmd_verify)

    status = sub.add_parser(
        "status", help="report project progress, coverage and next actions"
    )
    status.add_argument("path")
    status.add_argument("--json", action="store_true")
    status.add_argument("--strict", action="store_true")
    status.set_defaults(func=cmd_status)

    ingest = sub.add_parser(
        "ingest",
        help="convert txt/md/epub/docx/html/pdf into chapter Markdown",
    )
    ingest.add_argument("path")
    ingest.add_argument("source")
    ingest.add_argument("--to", default="")
    ingest.add_argument("--dry-run", action="store_true")
    ingest.add_argument("--force", action="store_true")
    ingest.add_argument("--update-project", action="store_true")
    ingest.add_argument("--extract-images", action="store_true")
    ingest.add_argument("--json", action="store_true")
    ingest.set_defaults(func=cmd_ingest)

    audit = sub.add_parser(
        "audit", help="audit metadata, evidence, alignment and coverage"
    )
    audit.add_argument("path")
    audit.add_argument("--json", action="store_true")
    audit.add_argument("--strict", action="store_true")
    audit.set_defaults(func=cmd_audit)

    style = sub.add_parser(
        "style", help="quantitative style metrics + banned-phrase lint"
    )
    style.add_argument("path")
    style.add_argument("--json", action="store_true")
    style.add_argument("--strict", action="store_true")
    style.add_argument("--no-metrics", action="store_true")
    style.set_defaults(func=cmd_style)

    source = sub.add_parser(
        "source-check",
        help="check source text, provenance and rights; suggest search queries",
    )
    source.add_argument("path")
    source.add_argument("--json", action="store_true")
    source.add_argument("--strict", action="store_true")
    source.add_argument("--write-template", action="store_true")
    source.add_argument("--record-search", action="store_true")
    source.add_argument(
        "--outcome",
        choices=[
            "found_text",
            "found_reference_only",
            "not_found",
            "user_declined",
            "blocked",
        ],
    )
    source.add_argument("--query", action="append", default=[])
    source.add_argument("--candidate", action="append", default=[])
    source.add_argument("--notes", default="")
    source.set_defaults(func=cmd_source_check)

    single = sub.add_parser("single", help="build the standalone HTML")
    single.add_argument("path")
    single.set_defaults(func=cmd_single)

    place = sub.add_parser("place-images", help="assign images to sections")
    place.add_argument("path")
    place.add_argument("--apply", action="store_true")
    place.add_argument("--chapter", default="")
    place.add_argument("--max-per-chapter", type=int, default=0)
    place.set_defaults(func=cmd_place_images)

    fetch = sub.add_parser("fetch-images", help="fetch openly licensed images")
    fetch.add_argument("path")
    fetch.add_argument("--query", default="")
    fetch.add_argument("--chapter", default="")
    fetch.add_argument("--section", default="")
    fetch.add_argument("--source", default="auto", choices=["auto", "wikimedia", "openverse", "local"])
    fetch.add_argument("--local-dir", default="")
    fetch.add_argument("--limit", type=int, default=1)
    fetch.add_argument("--min-width", type=int, default=800)
    fetch.add_argument("--after-block", type=int, default=0)
    fetch.add_argument("--mode", default="both", choices=["both", "original", "retold"])
    fetch.add_argument("--id", dest="image_id", default="")
    fetch.add_argument("--dry-run", action="store_true")
    fetch.set_defaults(func=cmd_fetch_images)

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
