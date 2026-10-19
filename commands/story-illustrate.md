---
description: 为 Story Forge 项目登记或抓取插图，分配到章节小节并重新构建
argument-hint: <project-path> ["query"] [--chapter ch1] [--source wikimedia|openverse|local]
---

使用 `engine/content/SCHEMA.md` 第 9 节与对应故事技能的插图小节完成这个任务。

## 必须先读

1. `engine/content/SCHEMA.md` — `content/illustrations.json` 字段与校验规则
2. `engine/tools/fetch_illustrations.py`、`engine/tools/place_illustrations.py` — 实际行为
3. 项目当前的 `content/illustrations.json` 与 `project.json`

## 执行顺序

1. 确认项目已 `parse` 过；`place-images` 依赖 `build/chapters.json`。
2. 选择图片来源：
   - **本地文件**：用户提供的图片放进 `assets/img/`，在 `content/illustrations.json` 登记 `id`、`file`、`alt`、`chapter`，可选 `caption`、`keywords`。
   - **开放许可抓取**：
     `python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" fetch-images <project> --query "关键词" --chapter ch1 --limit 2`
     可用 `--source wikimedia|openverse|local`、`--local-dir PATH`、`--mode both|original|retold`、`--dry-run`。
3. 先看候选：加 `--dry-run`，确认来源、尺寸与许可证。
4. 分配小节：
   `python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" place-images <project>`
   确认输出后再写：
   `python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" place-images <project> --apply`
   可用 `--chapter ch1` 限定章节、`--max-per-chapter N` 调整上限。
5. 重新解析并构建：
   `python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" build <project> --single`
6. 校验：
   `python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" verify <project>`
7. 在浏览器检查图注、署名、许可、窄屏布局；确认单文件打开后图片仍在（已内联为 data URI）。

## 硬性规则

- manifest 的 `file` 只接受项目内本地文件；站点拒绝远程热链（`http://` / `https://` 的 `src` 会校验失败）。
- 网页来源必须带 `credit` 与 `license`；`sourceUrl` 用于署名链接。
- 每张图必须有 `alt`；`section` 必须存在，`mode` 必须是该章节可用的模式。
- `mode: "both"` 会注入所有模式；双文本项目建议两版 section id 一致。
- 受版权保护的官方美术 / 同人图：只由用户提供本地文件并自行确认权利，不要用抓取工具下载。
- `fetch-images` 只从 Wikimedia Commons、Openverse 取开放许可图片，或复制 `--local-dir` 中的用户文件。
- 不手工编辑 `site/data/*.js`；流程是 manifest → parse → build。
- 校验不通过就不要宣布完成。

参数：$ARGUMENTS
