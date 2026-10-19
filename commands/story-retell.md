---
description: 把已有小说 / 游戏剧情 / 同人文本重构为带原文/复述切换的富结构阅读站
argument-hint: <source-dir> [chapter-range]
---

使用 `story-retelling` 技能完成这个任务。

## 必须先读

1. `engine/content/SCHEMA.md` — 数据规范
2. `skills/story-retelling/SKILL.md` — 完整工作流
3. 源文本目录中的章节文件

## 执行顺序

1. 确认范围：源目录、章节范围、读者是否读过前文、是否需要单文件。
2. 如果还没有项目，先 scaffold：
   `python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" new <project> --template retelling --title "…" --slug "…"`
3. **源文本获取（默认）**：如果用户只给了作品名、`sources/` 为空，先按 `story-source` 技能搜索原文：
   `python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" source-check <project> --json`
   按返回的 `queries` 搜索；只把公有领域 / 开放许可 / 用户提供 / 已授权的全文写进 `sources/`，并在 `content/source_provenance.json` 登记。找不到就如实说明并请用户提供文件。
4. 把原文整理成 `sources/*.md`（H1/H2/H3）；把复述版写进 `retold/*.md`。两边文件名与 H1/H2/H3 结构一一对应（`sources/01.md` ↔ `retold/01.md`）。
5. 配置 `project.json`：`kind: "retelling"`、`modes: ["original","retold"]`、`sourceDir: "sources"`、`retoldDir: "retold"`；章节条目同时写 `files` 与 `retoldFiles`。
6. **先写 `content/style_profile.md`**：从原文提取人称、句长、词汇、对话比例、标题习惯、明确不写的东西，并摘录 3–5 段样本。
7. 跑 `python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" parse <project>`，检查 `build/parse_report.json` 的 `fidelityByMode`（每章 `original` 与 `retold` 都要为 true）与 section id。
8. 按顺序写元数据：`worldview.json` → `entities.json` → `manual_links.json` → `chapter_meta.json` → `recap.json`。证据引文必须逐字来自对应模式正文；section 使用两版共用的 id。
9. 如需插图：本地文件放 `assets/img/` 并登记 `content/illustrations.json`，或跑
   `python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" fetch-images <project> --query "…" --chapter ch1`；再跑 `python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" place-images <project> --apply`。
10. 更新 `project.json` 的 `ready`，跑：
   `python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" build <project> --single`
   `python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" verify <project>`
   `python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" style <project>`
11. 用浏览器检查首页、前情提要、阅读、原文/复述切换、档案、星图、防剧透、插图、响应式。切换后应停在同一小节。

## 硬性规则

- 正文不重打：原文与复述都交给解析器；模型只写复述文本与结构化元数据。
- 两版必须同构：`retold/` 与 `sources/` 同名、同 H1/H2/H3 骨架；否则切换错位、证据找不到。
- 所有生成文字必须仿照原文风格；禁止金句、升华、替角色下结论。
- 证据引文必须逐字来自正文；`section` 必须是两版共用的 id。
- 单字名不自动标注，走 `manual_links.json`。
- `spoilerFrom` 用章节 `order`，不是章节 id。
- 图片只用本地文件；网页来源仅限 Wikimedia Commons / Openverse 的开放许可图片，并保留 credit 与 license。
- 校验不通过就不要宣布完成。

参数：$ARGUMENTS
