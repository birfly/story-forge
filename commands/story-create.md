---
description: 从一句设定新建同人故事，并生成创建模式的富结构阅读站
argument-hint: <project-path> [premise]
---

使用 `story-creation` 技能完成这个任务。

## 必须先读

1. `engine/content/SCHEMA.md` — 数据规范
2. `skills/story-creation/SKILL.md` — 完整工作流

## 执行顺序

1. 前提访谈：题材、篇幅、人称、目标读者、核心问题、结局感受、是否有样文。一次问一个。
2. 如果还没有项目，先 scaffold：
   `python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" new <project> --template creation --title "…" --slug "…"`
   模板生成 `kind: "creation"`、`modes: ["retold"]`，界面标签为“创作”；没有原文模式。
3. **原作资料（默认，仅同人）**：如果这是基于已有作品的同人，在 `project.json` 写 `basedOn: "原作名"`，然后按 `story-source` 技能搜索原作设定、人物与时间线：
   `python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" source-check <project> --json`
   按 `searchPlan.queries` 搜索，并用
   `source-check <project> --record-search --outcome <结果> --query "…" --notes "…"`
   记录；在记录之前不要直接停下来要资料。参考资料登记为 `kind: "reference"`，不要整段复制受版权保护的正文。原创故事跳过这一步。
4. **先写 `content/style_profile.md`**：
   - 有样文：按样文提取人称、句长、词汇、对话比例、标题习惯、禁止项。
   - 无样文：写一份具体的文风约定，不能写“文笔优美”这种空话。
5. 建故事圣经：`worldview.json` → `entities.json` → `recap.json`（前史 + 当前局势 + 大纲）→ `chapter_meta.json`（章节计划）。
6. 写章节到 `chapters/*.md`（H1/H2/H3），每章只引入 1–3 个新实体，至少改变一条关系。
7. 如需插图：本地文件放 `assets/img/` 并登记 `content/illustrations.json`，或跑
   `python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" fetch-images <project> --query "…" --chapter ch1`；再跑 `python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" place-images <project> --apply`。创作项目只有 `retold` 模式，图片 `mode` 保持 `both` 即可。
8. 跑：
   `python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" parse <project>`
   补 evidence、更新 `ready`，再：
   `python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" build <project> --single`
   `python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" verify <project>`
   `python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" style <project>`
9. 最小闭环：3 章、5 个实体、3 条关系。跑通后再扩。

## 硬性规则

- 创建项目不写 `sources/`、`retold/`、`retoldFiles`；正文只在 `chapters/`。
- 故事圣经先于正文。
- 文风约定先于第一章；正文和元数据都用同一种文风。
- 不写金句、不升华、不替角色下结论。
- `summary` 不得超过 `spoilerFrom`。
- 证据引文必须逐字来自正文。
- 图片只用本地文件；网页来源仅限 Wikimedia Commons / Openverse 的开放许可图片，并保留 credit 与 license。
- 校验不通过就不要宣布完成。

参数：$ARGUMENTS
