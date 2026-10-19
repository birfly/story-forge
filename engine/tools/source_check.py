#!/usr/bin/env python3
"""Story Forge — source availability, search plan, provenance and attempts.

Usage:
    python source_check.py <project-dir> [--json] [--strict] [--write-template]
    python source_check.py <project-dir> --record-search --outcome not_found \
        --query "作品名 原文" --candidate "某 Wiki|https://…|reference" --notes "…"

This tool never performs network searches. It tells the model whether source
text exists, which resources and queries to check, and records what was tried.
Actual discovery is done with the host's WebSearch / WebFetch tools and then
imported with ingest_sources.py.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime
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
SEARCH_OUTCOMES = {
    "found_text",
    "found_reference_only",
    "not_found",
    "user_declined",
    "blocked",
}
STRICT_OK = {"ready", "not_required", "optional", "reference_ready"}
SEARCH_PLAN_PATH = Path(__file__).resolve().parent.parent / "source_sources.json"

DEFAULT_SEARCH_PLAN: dict[str, Any] = {
    "priority": [
        {"id": "official", "label": "官方 / 出版社 / 作者官网"},
        {
            "id": "public-domain",
            "label": "公有领域",
            "examples": [
                "Project Gutenberg",
                "Wikisource",
                "Aozora Bunko",
                "Chinese Text Project",
                "Internet Archive",
            ],
        },
        {"id": "open-license", "label": "开放许可", "examples": ["CC0", "CC BY", "CC BY-SA"]},
        {"id": "user-provided", "label": "用户提供 / 已授权"},
        {
            "id": "reference",
            "label": "参考来源",
            "examples": ["官方 wiki", "百科", "剧情总结", "攻略"],
            "note": "只能作为 reference，不能当正文",
        },
    ],
    "queryTemplates": [
        "{title}",
        "{title} 原文",
        "{title} 小说 全文",
        "{title} 剧情 文本",
        "{title} wiki",
        "{title} site:zh.wikisource.org",
        "{title} site:gutenberg.org",
        "{title} site:aozora.gr.jp",
        "{title} 作者 {author}",
    ],
    "avoid": ["盗版聚合站", "未授权全文转载", "网盘转载", "来源不明的全文"],
}


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


def load_provenance(
    project: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
    data = read_json(provenance_path(project))
    if not isinstance(data, dict):
        return {"policy": "", "entries": [], "searchAttempts": []}, [], []
    entries = [
        item for item in data.get("entries") or [] if isinstance(item, dict)
    ]
    attempts = [
        item for item in data.get("searchAttempts") or [] if isinstance(item, dict)
    ]
    return data, entries, attempts


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


def load_search_plan() -> dict[str, Any]:
    data = read_json(SEARCH_PLAN_PATH)
    if not isinstance(data, dict):
        return DEFAULT_SEARCH_PLAN
    plan = dict(DEFAULT_SEARCH_PLAN)
    plan.update(data)
    return plan


def expand_queries(
    plan: dict[str, Any],
    title: str,
    author: str,
    based_on: str,
) -> list[str]:
    seed = based_on or title
    if not seed:
        return []
    values = {"title": seed, "author": author, "basedOn": based_on}
    queries: list[str] = []
    for template in plan.get("queryTemplates") or []:
        template = str(template)
        if "{author}" in template and not author:
            continue
        try:
            query = template.format(**values).strip()
        except (KeyError, ValueError):
            continue
        if query and query not in queries:
            queries.append(query)
    return queries


def search_plan(
    title: str, author: str, based_on: str
) -> dict[str, Any]:
    plan = load_search_plan()
    return {
        "priority": plan.get("priority") or DEFAULT_SEARCH_PLAN["priority"],
        "queries": expand_queries(plan, title, author, based_on),
        "avoid": plan.get("avoid") or DEFAULT_SEARCH_PLAN["avoid"],
    }


def decide_next(
    *,
    policy: str,
    present: bool,
    authored: bool,
    entries: list[dict[str, Any]],
    rights: str,
    based_on: str,
    attempts: list[dict[str, Any]],
) -> str:
    last_outcome = str(attempts[-1].get("outcome") or "") if attempts else ""
    if policy == "none" and not present:
        return "not_required"
    if present and authored:
        return "ready"
    if present and not entries:
        return "record_provenance"
    if present and rights == "unknown":
        return "confirm_rights"
    if present:
        return "ready"
    if policy == "required":
        if not attempts:
            return "search_original"
        if last_outcome == "found_text":
            return "import_source"
        if last_outcome in ("found_reference_only", "not_found", "user_declined", "blocked"):
            return "request_source"
        return "search_original"
    if based_on:
        if not attempts:
            return "search_reference"
        if last_outcome in ("found_reference_only", "found_text"):
            return "reference_ready"
        if last_outcome in ("not_found", "user_declined", "blocked"):
            return "optional"
        return "search_reference"
    return "optional"


def build_report(project: Path) -> dict[str, Any]:
    config = read_json(project / "project.json")
    if not isinstance(config, dict):
        config = {}
    kind = infer_kind(config)
    policy = source_policy(config)
    directory = primary_source_dir(config)
    files = source_files(project, directory)
    provenance, entries, attempts = load_provenance(project)
    rights = rights_status(entries)
    title = str(config.get("title") or "").strip()
    author = str(config.get("author") or "").strip()
    based_on = str(config.get("basedOn") or config.get("canon") or "").strip()
    present = bool(files)
    authored = kind == "creation" and policy != "required"
    next_action = decide_next(
        policy=policy,
        present=present,
        authored=authored,
        entries=entries,
        rights=rights,
        based_on=based_on,
        attempts=attempts,
    )
    plan = search_plan(title, author, based_on)

    guidance = {
        "search_original": (
            "没有源文本，也没有搜索记录。必须先用 WebSearch / WebFetch 按 searchPlan 搜索；"
            "至少检查官方、公有领域和开放许可来源，然后用 --record-search 记录 outcome。"
            "在记录搜索尝试之前，不要直接向用户要文件。"
        ),
        "search_reference": (
            "这是基于已有作品的项目，但还没有原作资料。先按 basedOn 搜索原作/设定；"
            "只把可靠资料记为 kind: \"reference\"，不要整段复制受版权保护的正文。"
            "搜索后用 --record-search 记录 outcome。"
        ),
        "import_source": (
            "搜索记录显示已找到可用全文。用 story.py ingest 导入，"
            "并在 content/source_provenance.json 登记 primary-text、URL 与许可。"
        ),
        "request_source": (
            "已记录搜索尝试，但没有找到可用全文。把候选、缺口和已试查询告诉用户，"
            "请其提供文件或确认使用权；不要凭记忆补正文。"
        ),
        "record_provenance": (
            "已有源文本但没有来源记录。登记标题、作者、URL、访问日期、用途与许可。"
        ),
        "confirm_rights": (
            "来源已登记，但许可状态不明。确认用户有权使用该文本；"
            "受版权保护的作品只作为参考，不整段复制进项目。"
        ),
        "reference_ready": (
            "参考资料已找到并记录，可以开始写作。参考不能替代原文，"
            "也不要整段复制受版权保护的正文。"
        ),
        "ready": "源文本与来源记录就绪。",
        "not_required": "该项目不要求源文本。",
        "optional": (
            "原创故事可以直接写作。如果它是基于已有作品的同人，"
            "在 project.json 里写 basedOn，以便先搜索原作设定。"
        ),
    }[next_action]

    last_outcome = str(attempts[-1].get("outcome") or "") if attempts else ""
    return {
        "project": str(project),
        "title": title,
        "author": author,
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
            "searchAttempts": len(attempts),
            "lastSearchOutcome": last_outcome,
        },
        "next": next_action,
        "queries": plan["queries"],
        "searchPlan": plan,
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
                    "entries": [],
                    "searchAttempts": [],
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
            "- 找不到可靠来源时，明确说明，不要凭记忆伪造正文。\n\n"
            "搜索尝试也用 `story.py source-check --record-search` 记录到同一个文件。\n",
            encoding="utf-8",
        )
        created.append(str(readme.relative_to(project)))
    return created


def record_search(
    project: Path,
    outcome: str,
    queries: list[str],
    candidates: list[str],
    notes: str,
) -> dict[str, Any]:
    if outcome not in SEARCH_OUTCOMES:
        raise ValueError(f"unknown outcome: {outcome}")
    target = provenance_path(project)
    data = read_json(target)
    if not isinstance(data, dict):
        config = read_json(project / "project.json")
        policy = source_policy(config) if isinstance(config, dict) else "required"
        data = {"policy": policy, "entries": [], "searchAttempts": []}
    attempts = data.get("searchAttempts")
    if not isinstance(attempts, list):
        attempts = []
    record = {
        "at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "outcome": outcome,
        "queries": [query for query in queries if query],
        "candidates": [candidate for candidate in candidates if candidate],
        "notes": notes,
    }
    attempts.append(record)
    data["searchAttempts"] = attempts
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(
        json.dumps(data, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    return record


def format_human(report: dict[str, Any]) -> str:
    lines = [
        f"项目：{report['title'] or report['project']}  [{report['kind']}]",
        f"源目录：{report['sourceDir']} · {report['fileCount']} 个文件 · "
        f"{report['hanzi']} 汉字",
        f"策略：{report['policy']} · 来源登记："
        f"{report['provenance']['entries']} 条 · 权利状态："
        f"{report['provenance']['rights']}",
        f"搜索尝试：{report['provenance']['searchAttempts']} 次"
        + (
            f" · 最近结果：{report['provenance']['lastSearchOutcome']}"
            if report["provenance"]["lastSearchOutcome"]
            else ""
        ),
        f"下一步：{report['next']}",
        f"说明：{report['guidance']}",
    ]
    if report["searchPlan"]["queries"]:
        lines.append("搜索建议：")
        lines.extend(f"  - {query}" for query in report["searchPlan"]["queries"])
    if report["searchPlan"]["priority"]:
        lines.append("优先来源：")
        for item in report["searchPlan"]["priority"]:
            label = item.get("label") or item.get("id")
            examples = item.get("examples") or []
            suffix = f"（{', '.join(examples)}）" if examples else ""
            lines.append(f"  - {label}{suffix}")
    if report["searchPlan"]["avoid"]:
        lines.append("避免：" + "、".join(report["searchPlan"]["avoid"]))
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    parser = argparse.ArgumentParser(
        description="检查 Story Forge 项目的原文、搜索计划与来源登记状态"
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
        help="创建 content/source_provenance.json 与主源目录下的 PROVENANCE.md",
    )
    parser.add_argument(
        "--record-search",
        action="store_true",
        help="把一次搜索尝试写入 content/source_provenance.json",
    )
    parser.add_argument(
        "--outcome",
        choices=sorted(SEARCH_OUTCOMES),
        help="搜索尝试的结果；配合 --record-search",
    )
    parser.add_argument(
        "--query",
        action="append",
        default=[],
        help="本次搜索使用的查询；可重复",
    )
    parser.add_argument(
        "--candidate",
        action="append",
        default=[],
        help="候选来源描述（如 标题|URL|reference）；可重复",
    )
    parser.add_argument("--notes", default="", help="本次搜索的备注")
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

    recorded: dict[str, Any] | None = None
    if args.record_search:
        if not args.outcome:
            message = "--record-search 需要 --outcome"
            if args.json:
                print(json.dumps({"error": message}, ensure_ascii=False))
            else:
                print(message, file=sys.stderr)
            return 2
        if not (args.query or args.candidate or args.notes):
            message = "至少提供 --query、--candidate 或 --notes 之一"
            if args.json:
                print(json.dumps({"error": message}, ensure_ascii=False))
            else:
                print(message, file=sys.stderr)
            return 2
        recorded = record_search(
            project,
            args.outcome,
            args.query,
            args.candidate,
            args.notes,
        )
        if not args.json:
            print(
                "已记录搜索尝试："
                f"{recorded['outcome']} · {recorded['at']}"
            )

    report = build_report(project)
    if recorded is not None:
        report["recordedSearch"] = recorded
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
    else:
        print(format_human(report))

    if args.strict and report["next"] not in STRICT_OK:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
