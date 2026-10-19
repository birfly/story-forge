#!/usr/bin/env python3
"""Story Forge — source availability and provenance check.

Usage:
    python source_check.py <project-dir> [--json] [--strict] [--write-template]

This tool never searches the network. It tells the model whether the project
has source text, whether its provenance/rights are recorded, and which search
queries to use when the source is missing. Actual discovery is done with the
host's WebSearch / WebFetch tools and then imported with ingest_sources.py.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

HANZI_RE = re.compile(r"[一-鿿]")
CLEARED_LICENSES = {
    "public-domain",
    "public domain",
    "cc0",
    "cc-by",
    "cc-by-sa",
    "licensed",
    "user-provided",
}
REFERENCE_KINDS = {"reference", "summary", "wiki", "canon"}


def utf8_stdio() -> None:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass


def read_json(path: Path) -> Any:
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def infer_kind(config: dict[str, Any]) -> str:
    kind = str(config.get("kind") or "").lower()
    if kind in ("import", "retelling", "creation"):
        return kind
    if config.get("sourceDir") == "chapters" and "retoldDir" not in config:
        return "creation"
    if any(
        isinstance(spec, dict) and spec.get("retoldFiles")
        for spec in config.get("chapters") or []
    ):
        return "retelling"
    return "import"


def primary_source_dir(config: dict[str, Any]) -> str:
    variants = config.get("variants")
    if isinstance(variants, list):
        for variant in variants:
            if isinstance(variant, dict) and variant.get("primary"):
                return str(variant.get("dir") or config.get("sourceDir", "sources"))
    if infer_kind(config) == "creation":
        return str(config.get("sourceDir", "chapters"))
    return str(config.get("sourceDir", "sources"))


def source_policy(config: dict[str, Any]) -> str:
    declared = str(config.get("sourcePolicy") or "").lower()
    if declared in ("required", "optional", "none"):
        return declared
    return "optional" if infer_kind(config) == "creation" else "required"


def source_files(project: Path, directory: str) -> list[Path]:
    root = project / directory
    if not root.is_dir():
        return []
    return sorted(
        path
        for path in root.glob("*.md")
        if path.is_file() and path.name.lower() != "readme.md"
    )


def count_hanzi(paths: list[Path]) -> int:
    total = 0
    for path in paths:
        try:
            total += len(HANZI_RE.findall(path.read_text(encoding="utf-8-sig")))
        except (OSError, UnicodeDecodeError):
            continue
    return total


def provenance_path(project: Path) -> Path:
    return project / "content" / "source_provenance.json"


def load_provenance(project: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    data = read_json(provenance_path(project))
    if not isinstance(data, dict):
        return {"policy": "", "entries": []}, []
    entries = [
        item for item in data.get("entries") or [] if isinstance(item, dict)
    ]
    return data, entries


def rights_status(entries: list[dict[str, Any]]) -> str:
    if not entries:
        return "unknown"
    primary = [
        entry
        for entry in entries
        if str(entry.get("kind") or "primary-text").lower()
        not in REFERENCE_KINDS
    ]
    if not primary:
        return "reference-only"
    for entry in primary:
        if str(entry.get("license") or "").lower() in CLEARED_LICENSES:
            return "cleared"
    return "unknown"


def search_queries(title: str) -> list[str]:
    title = title.strip()
    if not title:
        return []
    return [
        title,
        f"{title} 原文",
        f"{title} 小说 全文",
        f"{title} 剧情 文本",
        f"{title} wiki",
    ]


def build_report(project: Path) -> dict[str, Any]:
    config = read_json(project / "project.json")
    if not isinstance(config, dict):
        config = {}
    kind = infer_kind(config)
    policy = source_policy(config)
    directory = primary_source_dir(config)
    files = source_files(project, directory)
    provenance, entries = load_provenance(project)
    rights = rights_status(entries)
    title = str(config.get("title") or "").strip()
    based_on = str(config.get("basedOn") or config.get("canon") or "").strip()
    present = bool(files)
    authored = kind == "creation" and policy != "required"

    if policy == "none" and not present:
        next_action = "not_required"
    elif present and authored:
        next_action = "ready"
    elif present and not entries:
        next_action = "record_provenance"
    elif present and rights == "unknown":
        next_action = "confirm_rights"
    elif present:
        next_action = "ready"
    elif policy == "required":
        next_action = "search_original"
    elif based_on:
        next_action = "search_reference"
    else:
        next_action = "optional"

    query_seed = based_on or title
    queries = (
        search_queries(query_seed)
        if not present and next_action in ("search_original", "search_reference")
        else []
    )

    guidance = {
        "search_original": (
            "没有源文本。先用 WebSearch 按 queries 查找原文或可靠剧情资料；"
            "把可用的全文/资料保存为 sources/*.md，再登记 content/source_provenance.json。"
        ),
        "search_reference": (
            "这是基于已有作品的项目，但当前没有源文本。先按 basedOn 搜索原作/设定资料；"
            "只把可靠资料作为参考，登记为 kind: \"reference\"，不要整段复制受版权保护的正文。"
        ),
        "record_provenance": (
            "已有源文本但没有来源记录。登记标题、作者、URL、访问日期、用途与许可。"
        ),
        "confirm_rights": (
            "来源已登记，但许可状态不明。确认用户有权使用该文本；"
            "受版权保护的作品只作为参考，不整段复制进项目。"
        ),
        "ready": "源文本与来源记录就绪。",
        "not_required": "该项目不要求源文本。",
        "optional": (
            "原创故事可以直接写作。如果它是基于已有作品的同人，"
            "在 project.json 里写 basedOn，以便先搜索原作设定。"
        ),
    }[next_action]

    return {
        "project": str(project),
        "title": title,
        "kind": kind,
        "policy": policy,
        "basedOn": based_on,
        "sourceDir": directory,
        "present": present,
        "fileCount": len(files),
        "files": [path.name for path in files],
        "hanzi": count_hanzi(files),
        "provenance": {
            "path": str(provenance_path(project).relative_to(project)),
            "exists": provenance_path(project).is_file(),
            "policy": provenance.get("policy") if isinstance(provenance, dict) else "",
            "entries": len(entries),
            "rights": rights,
        },
        "next": next_action,
        "queries": queries,
        "guidance": guidance,
    }


def write_template(project: Path) -> list[str]:
    created: list[str] = []
    target = provenance_path(project)
    if not target.exists():
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_text(
            json.dumps(
                {
                    "policy": "required",
                    "entries": [
                        {
                            "id": "source-1",
                            "title": "",
                            "author": "",
                            "url": "",
                            "accessed": "",
                            "kind": "primary-text",
                            "license": "unknown",
                            "notes": "",
                        }
                    ],
                },
                ensure_ascii=False,
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
        created.append(str(target.relative_to(project)))
    config = read_json(project / "project.json")
    if not isinstance(config, dict):
        config = {}
    directory = primary_source_dir(config)
    readme = project / directory / "PROVENANCE.md"
    if not readme.exists():
        readme.parent.mkdir(parents=True, exist_ok=True)
        readme.write_text(
            "# 源文本来源\n\n"
            "把每个源文件对应的标题、作者、URL、访问日期、用途（primary-text / reference）"
            "和许可登记到 `content/source_provenance.json`。\n\n"
            "- 公有领域 / CC 许可 / 用户提供 / 已授权：可以作为主文本。\n"
            "- 仅作参考（wiki、剧情总结、讨论）：`kind: \"reference\"`，不要整段复制。\n"
            "- 找不到可靠来源时，明确说明，不要凭记忆伪造正文。\n",
            encoding="utf-8",
        )
        created.append(str(readme.relative_to(project)))
    return created


def format_human(report: dict[str, Any]) -> str:
    lines = [
        f"项目：{report['title'] or report['project']}  [{report['kind']}]",
        f"源目录：{report['sourceDir']} · {report['fileCount']} 个文件 · "
        f"{report['hanzi']} 汉字",
        f"策略：{report['policy']} · 来源登记："
        f"{report['provenance']['entries']} 条 · 权利状态："
        f"{report['provenance']['rights']}",
        f"下一步：{report['next']}",
        f"说明：{report['guidance']}",
    ]
    if report["queries"]:
        lines.append("搜索建议：")
        lines.extend(f"  - {query}" for query in report["queries"])
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    parser = argparse.ArgumentParser(
        description="检查 Story Forge 项目的原文与来源登记状态"
    )
    parser.add_argument("project", help="Story Forge project directory")
    parser.add_argument("--json", action="store_true", help="只输出 JSON")
    parser.add_argument(
        "--strict",
        action="store_true",
        help="源文本缺失或来源未确认时返回退出码 1",
    )
    parser.add_argument(
        "--write-template",
        action="store_true",
        help="创建 content/source_provenance.json 与 sources/PROVENANCE.md",
    )
    args = parser.parse_args(argv)

    project = Path(args.project).resolve()
    if not project.is_dir():
        if args.json:
            print(json.dumps({"error": f"项目目录不存在：{project}"}, ensure_ascii=False))
        else:
            print(f"项目目录不存在：{project}", file=sys.stderr)
        return 1

    if args.write_template:
        created = write_template(project)
        if created and not args.json:
            print("已创建：" + "、".join(created))

    report = build_report(project)
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_human(report))

    if args.strict and report["next"] not in ("ready", "not_required", "optional"):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
