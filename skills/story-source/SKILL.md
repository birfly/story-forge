---
name: story-source
description: "在开始原文放入或复述之前，检查项目是否有源文本；没有时默认用 WebSearch / WebFetch 搜索原文、官方资料或可靠剧情参考，保存到 sources/ 并登记 content/source_provenance.json。Trigger when the user gives a work title without source files, when sources/ is empty, or when the user says 搜索原文、找原文、没有原文、帮我找小说/剧情文本."
---

# Story Source（原文获取）

当用户要复述或导入一部作品、但没有提供源文件时，先找工作，再问用户要文件。不要凭记忆编造正文。

## 先判断

```bash
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" source-check <project> --json
```

- `next: "search_original"` — import / retelling 项目缺少源文本，**必须先搜索**。
- `next: "search_reference"` — creation 项目声明了 `basedOn`，缺少原作/设定参考，**必须先搜索**。
- `next: "import_source"` — 搜索记录显示已找到全文，去 `ingest`。
- `next: "request_source"` — 已记录搜索尝试但没找到可用全文，向用户要文件。
- `next: "reference_ready"` — 参考已足够，可以开始写作。
- `next: "record_provenance"` / `"confirm_rights"` — 已有文本，但来源或许可没登记。
- `next: "ready"` / `"not_required"` / `"optional"` — 不需要再找。

## 搜索前置门（硬性）

没有源文本时，顺序固定，不能跳过：

1. 运行 `source-check`。
2. `next` 为 `search_original` / `search_reference` 时，先用 WebSearch / WebFetch 搜索；至少检查 `searchPlan.priority` 里的官方、公有领域、开放许可来源。
3. 每次搜索后，必须把结果写进来源文件：

```bash
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" source-check <project> \
  --record-search --outcome not_found \
  --query "作品名 原文" --query "作品名 小说 全文" \
  --candidate "某 Wiki|https://…|reference" \
  --notes "只找到参考页，没有可用全文"
```

`--outcome` 只能是 `found_text` / `found_reference_only` / `not_found` / `user_declined` / `blocked`。

4. 只有记录为 `not_found`、`found_reference_only` 或 `user_declined` 后，才向用户索取文件。
5. 找到可用全文后，先 `ingest` 导入并登记 `primary-text`，再跑 `source-check` 确认 `next` 变为 `ready`。

**没有记录搜索尝试之前，不要直接停下来问用户要文件。**

没有项目时，先 scaffold；连作品名都没有时，只问一个问题：作品名、作者、你要用的是哪一版。

## 搜索顺序

1. **官方 / 公有领域来源**
   - 出版社、作者官网、官方游戏剧情站、官方设定集
   - Project Gutenberg、Wikisource、Aozora Bunko、Chinese Text Project、Internet Archive（确认版权状态）
2. **开放许可 / 用户提供**
   - 用户自己的文件、已授权的翻译、CC 许可文本
3. **参考来源（不能当正文）**
   - 官方 wiki、百科、剧情总结、讨论帖、攻略
   - 只用来核对人物、时间线、事件事实；`kind` 记为 `reference`

不要使用盗版聚合站、网盘转载、未授权全文站。不要为了“凑够正文”复制受版权保护的长段落。

## 搜索查询

`source-check` 会给出 queries，通常包括：

```text
<作品名>
<作品名> 原文
<作品名> 小说 全文
<作品名> 剧情 文本
<作品名> wiki
```

补充查询：`<作品名> 作者 <作者名>`、`<作品名> 章节列表`、`<作品名> 官方设定`、`<作品名> 文本 site:zh.wikisource.org`。

## 抓取与保存

- 用 WebSearch 找候选，用 WebFetch 读取页面；分页章节逐页抓取，记录章节顺序。
- 只把**你有权使用的文本**写入 `sources/*.md`：
  - 公有领域 / CC / 用户提供 / 已授权 → 可以保存全文；
  - 受版权保护但用户提供了文件 → 按用户文件保存；
  - 只有参考页面 → 写入 `content/source_provenance.json`，`kind: "reference"`，不要往 `sources/` 塞全文。
- 保存后优先用摄取工具整理结构：

```bash
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" ingest <project> <source-file-or-dir> \
  --to sources --update-project
```

- 手工整理时也只做 H1/H2/H3 与空行，不改写正文。

## 来源登记（必做）

`content/source_provenance.json`：

```jsonc
{
  "policy": "required",
  "entries": [
    {
      "id": "source-1",
      "title": "作品名",
      "author": "作者",
      "url": "https://…",
      "accessed": "2026-10-19",
      "kind": "primary-text",        // primary-text | reference
      "license": "public-domain",     // public-domain | cc-by | cc-by-sa | user-provided | licensed | unknown
      "notes": "章节 1–12；来源页标注公有领域"
    }
  ]
}
```

没有记录来源的项目，`source-check` 会停在 `record_provenance`，`status` 也会给出下一步。

## 找不到时

先用 `source-check --record-search --outcome not_found`（只找到参考页时用 `found_reference_only`）记录，再明确报告：

- 搜过哪些查询、看过哪些候选；
- 哪些只能当参考、哪些不可用；
- 缺的是全文、章节范围还是某一版翻译；
- 请用户提供文件或确认使用权。

不要用“我记得剧情是……”来补正文；不要把参考摘要当成原文写入 `sources/`。

## 硬性规则

- 先搜索并记录，再向用户要文件；找不到时必须如实说找不到。
- 原文只从可靠来源获取；版权不明时只作参考。
- 所有来源与搜索尝试写入 `content/source_provenance.json`。
- 构建产物仍然离线，不在阅读站运行时发起网络请求。
- 正文保真规则不变：`sources/` 只整理结构，不改写。
