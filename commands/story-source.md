---
description: 检查项目是否有原文；没有时默认搜索原文、登记来源，再交给导入或复述流程
argument-hint: <project-path> [work-title]
---

使用 `story-source` 技能完成这个任务。

## 必须先读

1. `skills/story-source/SKILL.md` — 搜索、抓取、版权与来源登记规则
2. `engine/content/SCHEMA.md` — `source_provenance.json` 与项目字段
3. 项目当前的 `project.json`、`sources/`、`content/source_provenance.json`

## 执行顺序

1. 检查：

   ```bash
   python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" source-check <project> --json
   ```

2. `next` 为 `search_original` / `search_reference` 时：
   - 用 `source-check` 给出的 `queries` 做 WebSearch；
   - 用 WebFetch 读取候选页；
   - 优先官方、公有领域、开放许可、用户可授权来源；
   - 受版权保护的全文不写入 `sources/`，只把 reliable 资料记为 `reference`。
3. 找到可用全文或用户提供文件后：
   - 用 `story.py ingest` 整理到 `sources/`，或手工整理 H1/H2/H3；
   - 在 `content/source_provenance.json` 登记 title / author / url / accessed / kind / license。
4. 找不到时：列出已试查询与候选，说明缺什么，请用户提供文件或确认使用权；不要凭记忆补正文。
5. 再回到 `/story-import`、`/story-retell` 或 `/story-create` 的对应流程。

## 硬性规则

- 先搜索，再索取文件；找不到就如实报告。
- 不把盗版全文、未授权转载、参考摘要当正文写入 `sources/`。
- 所有来源必须登记；`kind: "reference"` 的内容不能当原文。
- 阅读站构建产物保持离线，不在运行时抓取。
- 正文保真：只整理结构，不改写。

参数：$ARGUMENTS
