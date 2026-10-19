---
description: 把用户提供的原文原样放入富结构阅读站，只补元数据，不改写正文
argument-hint: <source-dir> <project-path>
---

使用 `story-import` 技能完成这个任务。

## 必须先读

1. `engine/content/SCHEMA.md` — 数据规范
2. `skills/story-import/SKILL.md` — 完整工作流
3. 源文本目录中的章节文件

## 执行顺序

1. 确认范围：源目录、格式（txt/epub/pdf/docx/Markdown）、章节范围、是否需要单文件、是否需要档案/前情提要。
2. 如果还没有项目，先 scaffold：
   `python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" new <project> --template import --title "…" --slug "…"`
3. **源文本获取（默认）**：如果用户只给了作品名、`sources/` 为空，先按 `story-source` 技能搜索原文：
   `python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" source-check <project> --json`
   按返回的 `queries` 搜索；只把公有领域 / 开放许可 / 用户提供 / 已授权的全文写进 `sources/`，并在 `content/source_provenance.json` 登记。找不到就如实说明并请用户提供文件。
4. 把源文本转成 `sources/*.md`（H1/H2/H3）。只整理结构，正文逐字保留。
5. 配置 `project.json`：`chapters` 的 `id` / `order` / `files` / `mode`，以及 `ready`。
6. **写 `content/style_profile.md`**：从原文提取人称、句长、词汇、对话比例、标题习惯、明确不写的东西，并摘录 3–5 段样本。
7. 跑 `python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" parse <project>`，检查 `build/parse_report.json` 的 `fidelity` 与 section id。
8. 按顺序写元数据（可选）：`worldview.json` → `entities.json` → `manual_links.json` → `chapter_meta.json` → `recap.json`。证据引文必须逐字来自 `sources/`。
9. 如需插图：本地文件放 `assets/img/` 并在 `content/illustrations.json` 登记，或跑
   `python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" fetch-images <project> --query "…" --chapter ch1`
   然后 `place-images <project> --apply`。
10. 构建与校验：
   `python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" build <project> --single`
   `python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" verify <project>`
   `python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" style <project>`
11. 用浏览器检查阅读、档案、证据回跳、插图与响应式。确认页面**没有**原文/复述切换。

## 硬性规则

- 正文不重打、不润色、不补写；`sources/*.md` 是唯一正文来源。
- 不创建 `retold/`，不写 `retoldFiles`；`kind` 保持 `import`，`modes` 保持 `["original"]`。
- 所有生成文字必须仿照原文风格；禁止金句、升华、替角色下结论。
- 证据引文必须逐字来自原文。
- 单字名不自动标注，走 `manual_links.json`。
- `spoilerFrom` 用章节 `order`，不是章节 id。
- 图片只用本地文件；网页来源仅限 Wikimedia Commons / Openverse 的开放许可图片，并保留 credit 与 license。
- 校验不通过就不要宣布完成。

参数：$ARGUMENTS
