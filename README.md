# Story Forge

[![tests](https://github.com/birfly/story-forge/actions/workflows/tests.yml/badge.svg)](https://github.com/birfly/story-forge/actions/workflows/tests.yml)

把已有文本或新故事做成**富结构阅读站**：正文可读，人物/势力/地点/术语/事件可点开，关系网可视，前情提要可查，证据可回溯，防剧透可开关。复述项目可以在原文与复述之间切换；项目可以带本地插图。

![Story Forge 阅读站首页](docs/screenshot.png)

> **预览版 `1.2.0-preview.1`**
>
> 支持 **Claude Code**（skills / commands / plugin 结构）。开发与验证环境为 Windows + Python 3.13；CI 覆盖 Ubuntu/Windows × Python 3.11/3.13。其他宿主尚未验证。已知限制见文末。

## 快速开始

```bash
# 1. 安装到 Claude Code 的 skills 目录
git clone https://github.com/birfly/story-forge.git ~/.claude/skills/story-forge

# 2. 构建并打开自带示例（无需 API key）
cd ~/.claude/skills/story-forge
python scripts/story.py build examples/mini-story --single
# 双击 examples/mini-story/dist/mini-story.html
```

创建自己的项目：

```bash
python scripts/story.py new ./my-story --template import \
  --title "故事标题" --slug my-story

# 把 Markdown 放进 my-story/sources/，然后：
python scripts/story.py parse ./my-story
python scripts/story.py build ./my-story --single
python scripts/story.py verify ./my-story
```

没有源文件时，先运行 `source-check`，它会给出搜索建议；模型会按 `story-source` 技能搜索原文并登记来源。

## 支持范围

| 项目 | 状态 |
|---|---|
| Claude Code 技能 / 命令 | 支持 |
| Python 3.11–3.13 | 支持；CI 覆盖 3.11 / 3.13 |
| Windows / Ubuntu | CI 覆盖 |
| macOS | 预期可用，尚未在 CI 验证 |
| 其他宿主（Codex 等） | 未验证，不作为首版支持范围 |

安装后可用技能：`story-source`、`story-import`、`story-retelling`、`story-creation`；命令：`/story-source`、`/story-import`、`/story-retell`、`/story-create`、`/story-illustrate`、`/story-build`、`/story-verify`。

## 0. 原文获取（没有原文时默认搜索）

import / retelling 项目缺少源文本时，不要先停下来要文件。先运行：

```bash
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" source-check <project> --json
```

- `next: "search_original"` → 用 WebSearch 按返回的 `queries` 搜索原文，再用 WebFetch 读取候选页。
- 优先官方、公有领域、开放许可、用户提供或已授权的来源；只把有权使用的全文写进 `sources/`。
- 受版权保护的作品只把可靠页面记为 `kind: "reference"`，不要整段复制正文。
- 在 `content/source_provenance.json` 登记标题、作者、URL、访问日期、用途与许可。
- 找不到就如实说明已试查询与缺口，再请用户提供文件。

下载/整理好的文件用 `story.py ingest` 转成章节 Markdown。完整规则见 `skills/story-source/SKILL.md` 与 `/story-source`。

## 三种项目类型

### 1. 原文放入（import）

用户提供现成文本，项目按原样展示。正文逐字进入 `sources/`，模型只编写结构化元数据，不改写、不重排、不补写正文。项目类型 `import`，只有 `original` 一种模式，阅读站不显示原文/复述切换。

```bash
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" new ./my-import --template import \
  --title "故事标题" --subtitle "阅读站定位" --slug "my-import"
```

### 2. 复述（retelling）

在已有文本之外再提供一份复述版。原文放 `sources/`，复述放 `retold/`，两边使用相同的文件名和 H1/H2/H3 结构。项目类型 `retelling`，模式为 `original` 与 `retold`，阅读站显示原文/复述切换。

```bash
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" new ./my-retelling --template retelling \
  --title "故事标题" --subtitle "给第一次读的人" --slug "my-retelling"
```

### 3. 新建同人（creation）

从一句设定开始写新的同人故事。项目类型 `creation`，只有 `retold` 一种模式，界面把这个模式标为“创作”；没有原文模式。正文放 `chapters/`。

```bash
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" new ./my-fanfic --template creation \
  --title "故事标题" --subtitle "一句话定位" --slug "my-fanfic"
```

---

## 原文/复述切换

双文本项目在 `project.json` 中声明两套目录和两种模式：

```jsonc
{
  "kind": "retelling",
  "modes": ["original", "retold"],
  "defaultMode": "retold",
  "primaryMode": "original",
  "sourceDir": "sources",
  "retoldDir": "retold",
  "modeLabels": { "original": "原文", "retold": "复述" }
}
```

章节条目同时给出两边的文件，文件名和结构一一对应：

```jsonc
{
  "id": "ch1",
  "order": 1,
  "files": ["01.md"],        // sources/01.md
  "retoldFiles": ["01.md"],  // retold/01.md
  "mode": "parts"
}
```

- 解析器把每种模式分别解析成 `variants.original` 与 `variants.retold`，并分别做正文保真检查。
- 阅读器按 `modeLabels` 显示“原文 / 复述”切换；切换时保留当前 section id，因此两边结构一致时会停在同一小节。
- `defaultMode` 决定首次进入章节时显示哪一版；`primaryMode` 是没有复述文件时使用的主正文模式（复述项目为 `original`）。
- 单模式章节（没有 `retoldFiles`）按 `primaryMode` 解析，不会显示切换按钮，也不影响构建。
- 证据和 section id 依据同名结构定位；两边保持相同的 H1/H2/H3 骨架，档案、证据和切换位置才不会错位。

完整字段见 `engine/content/SCHEMA.md`。

---

## 插图

插图统一登记在 `content/illustrations.json`，本地文件放在 `assets/img/`。manifest 形状：

```jsonc
{
  "images": [
    {
      "id": "img-lighthouse",
      "file": "assets/img/lighthouse.jpg",  // 项目相对路径，必须是本地文件
      "alt": "雾中的灯塔",                   // 必填
      "caption": "灯塔在夜里亮起",
      "credit": "摄影者 / 机构",             // 网页来源必填
      "license": "CC BY-SA 4.0",            // 网页来源必填
      "sourceUrl": "https://commons.wikimedia.org/wiki/File:...",
      "source": "wikimedia",                // local | wikimedia | openverse
      "chapter": "ch1",
      "section": "sch1-0-1",                // 未分配时用 place-images 补
      "afterBlock": 0,                      // 插入位置，0 起
      "mode": "both",                       // both | original | retold
      "status": "placed",
      "keywords": ["灯塔", "雾"]
    }
  ]
}
```

支持两种入口：

```bash
# 1. 本地图片：先把文件放进 assets/img/，再登记 manifest（字段见 SCHEMA.md 第 9 节）

# 2. 抓取开放许可图片（Wikimedia Commons / Openverse）
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" fetch-images ./my-story \
  --query "lighthouse night" --chapter ch1 --limit 2

# 3. 分配小节（先 dry-run，确认后 --apply）
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" place-images ./my-story --apply

# 4. 重新构建；单文件会把本地图片内联为 data URI
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" build ./my-story --single
```

- `fetch-images` 只从 Wikimedia Commons 和 Openverse 获取开放许可图片，或从 `--local-dir` 复制用户自己提供的本地文件；下载后自动写入 `credit`、`license`、`sourceUrl`。也可以只用 `--dry-run` 先看候选。
- `place-images` 按登记的关键词与小节文字的重叠度选择小节；没有关键词时按数量均匀分布。默认每章最多 4 张，可用 `--max-per-chapter` 或 `project.json` 的 `illustrations.maxPerChapter` 调整。未分配 `section` 的条目在 parse 时也会按关键词自动落到一个小节，`place-images` 用于重新平衡或在多张图之间分配。
- 解析器把登记项注入为 `{type:"image", src, alt, caption, credit, license, sourceUrl, width, height}` 块；`afterBlock` 控制插入位置。
- 构建时把项目 `assets/` 复制到 `site/assets/`；单文件构建把本地图片内联为 data URI，成品离线可用。
- 站点拒绝远程热链。网页来源图片必须带 `credit` 与 `license`；本地文件必须实际存在；插图必须有 `alt`，`section` 必须存在。
- 官方美术、同人图等受版权保护的材料，只能由用户提供本地文件并自行确认权利。抓取工具不会下载这类图片。
- 双文本项目建议让两版共用相同 section id；`mode: "both"` 会注入两种模式，某一模式缺少该 section 时只会注入存在的模式并给出 warning。

---

## 包含什么

```
story-forge/
├── .claude-plugin/plugin.json
├── skills/
│   ├── story-source/SKILL.md       # 原文获取（默认搜索）
│   ├── story-import/SKILL.md       # 原文放入工作流
│   ├── story-retelling/SKILL.md    # 复述工作流
│   └── story-creation/SKILL.md     # 新建同人工作流
├── commands/
│   ├── story-source.md
│   ├── story-import.md
│   ├── story-retell.md
│   ├── story-create.md
│   ├── story-illustrate.md
│   ├── story-build.md
│   └── story-verify.md
├── engine/
│   ├── tools/
│   │   ├── ingest_sources.py      # txt/epub/docx/html/pdf 摄取
│   │   ├── parse_chapters.py      # 解析 + 标注 + 校验 + 生成数据
│   │   ├── build_project.py       # 复制站点模板 + 构建
│   │   ├── build_singlefile.py    # 内联为单 HTML（含图片）
│   │   ├── fetch_illustrations.py # 抓取/复制开放许可图片
│   │   ├── place_illustrations.py # 图片分配小节
│   │   ├── project_status.py      # 项目进度/覆盖/下一步
│   │   ├── audit_content.py       # 内容审计
│   │   ├── style_lint.py          # 文风指标 + 金句检查
│   │   ├── source_check.py        # 源文本/来源/许可检查
│   │   └── verify.py              # 完整性/离线性验收
│   ├── content/
│   │   ├── SCHEMA.md               # 数据规范
│   │   ├── style_profile.template.md
│   │   ├── timeline.json           # 事件线空模板
│   │   ├── source_provenance.json  # 来源登记空模板
│   │   ├── illustrations.json      # 插图 manifest 空模板
│   │   └── *.json                  # 空模板
│   ├── site/                       # 阅读站模板（CSS/JS/HTML）
│   └── project.template.json
├── scripts/story.py                # CLI：new / ingest / parse / build / verify /
│                                   #      single / status / audit / style / source-check /
│                                   #      place-images / fetch-images
└── README.md
```

项目目录：

```
<project>/
├── project.json
├── sources/                # import / retelling 的原文
├── retold/                 # retelling 的复述
├── chapters/               # creation 的正文
├── assets/img/             # 本地插图
├── content/
│   ├── style_profile.md
│   ├── entities.json
│   ├── chapter_meta.json
│   ├── recap.json
│   ├── worldview.json
│   ├── timeline.json
│   ├── manual_links.json
│   ├── source_provenance.json
│   └── illustrations.json
├── site/                   # 多文件阅读站
├── dist/<slug>.html        # 单文件
└── build/                  # parse_report.json / chapters.json
```

---

## 安装

把整个 `story-forge/` 目录放到：

```
~/.claude/skills/story-forge/
```

下次启动 Claude Code 时，它会作为 `story-forge@skills-dir` 自动加载。

> 下面的命令用 `$CLAUDE_PLUGIN_ROOT` 指向插件根目录。如果当前环境没有设置这个变量，把它替换成插件的实际路径，通常是 `~/.claude/skills/story-forge`。

也可以用 Claude Code 的插件脚手架：

```bash
claude plugin init story-forge
# 然后把本目录的 skills/commands/engine/scripts 复制进去
```

安装后可用：

- 技能：`story-source`、`story-import`、`story-retelling`、`story-creation`
- 命令：`/story-source`、`/story-import`、`/story-retell`、`/story-create`、`/story-illustrate`、`/story-build`、`/story-verify`

---

## 快速开始：原文放入

```bash
# 1. 创建项目
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" new ./my-import --template import \
  --title "故事标题" --subtitle "给第一次读的人" --slug "my-import"

# 2. 把原文整理成 sources/*.md；正文保持原样，只整理 H1/H2/H3
#    H1 = 章，H2 = 部，H3 = 节

# 3. 配置 project.json 的 chapters 与 ready

# 4. 如需档案/前情提要等元数据，先写 content/style_profile.md

# 5. 解析
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" parse ./my-import

# 6. 写 content/ 下的元数据（可选；见 SCHEMA.md）

# 7. 构建 + 校验
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" build ./my-import --single
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" verify ./my-import
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" style ./my-import
```

打开 `my-import/site/index.html`，或双击 `my-import/dist/my-import.html`。阅读站不显示原文/复述切换。

---

## 快速开始：复述

```bash
# 1. 创建项目
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" new ./my-retelling --template retelling \
  --title "故事标题" --subtitle "给第一次读的人" --slug "my-retelling"

# 2. 原文放 sources/，复述放 retold/；文件名和 H1/H2/H3 结构一一对应
#    sources/01.md ↔ retold/01.md

# 3. 在 project.json 的 chapters 中同时写 files 与 retoldFiles

# 4. 写 content/style_profile.md（从原文提取风格）

# 5. 解析；两种模式分别做正文保真检查
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" parse ./my-retelling

# 6. 写 content/ 下的元数据（见 SCHEMA.md）

# 7. 构建 + 校验
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" build ./my-retelling --single
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" verify ./my-retelling
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" style ./my-retelling
```

打开阅读站后，用顶部“原文 / 复述”切换两版。默认显示 `defaultMode`（模板为 `retold`）。

---

## 快速开始：新建同人

```bash
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" new ./my-fanfic --template creation \
  --title "故事标题" --subtitle "一句话定位" --slug "my-fanfic"
```

然后：

1. 写 `content/style_profile.md`。
2. 写 `worldview.json`、`entities.json`、`recap.json`、`chapter_meta.json`。
3. 写 `chapters/*.md`。
4. `parse` → 补 evidence、更新 `ready` → `build --single` → `verify` → `audit` → `style`。

`kind` 为 `creation`，只有 `retold` 模式，界面标签为“创作”，没有原文模式。先跑 3 章最小闭环，再扩卷。

---

## 原文摄取（ingest）

不必手工把 txt/epub/pdf 转成 Markdown：

```bash
# 先看计划，不写文件
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" ingest ./my-story ./novel.epub --dry-run

# 写入 sources/，并把章节合并进 project.json
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" ingest ./my-story ./novel.epub \
  --update-project

# 编码/页眉页脚清洗报告
cat ./my-story/build/ingest_report.json
```

- 支持 txt / md / epub / docx / html；pdf 需要可选 `pypdf`，扫描版会明确提示需要 OCR。
- 章节识别覆盖 `第X章/卷/回`、`序章`、`番外`、`Chapter N`、数字标题等。
- 只做结构归一、段落空行、重复页眉页脚/页码清理；正文不改写。
- 报告包含来源 sha256、编码、逐章字数、丢失比例、warning；冲突默认中止，`--force` 才覆盖。

---

## 富结构扩展

### 任意变体（variants）

`project.json` 可以声明任意变体，不再局限于原文/复述：

```jsonc
"variants": [
  { "id": "original", "label": "原文", "dir": "sources", "primary": true },
  { "id": "retold",   "label": "复述", "dir": "retold" },
  { "id": "en",       "label": "English", "dir": "translations/en" }
]
```

章节用 `variantFiles: { "retold": ["01.md"], "en": ["01.en.md"] }` 指定文件。阅读器按 `modeLabels` 显示切换按钮；两版结构一致时切换停在同一小节。

### 卷册

```jsonc
"volumes": [
  { "id": "vol1", "title": "第一卷 雾港", "order": 1, "chapters": ["ch1", "ch2"] }
]
```

目录、首页章节条按卷分组，可折叠；章节封面显示卷名。也可以用 `from`/`to` 按 order 推导。

### 事件线

`content/timeline.json` 提供结构化事件：故事时间、锚点章节、参与实体、前因/后果、证据。阅读器新增 `#/timeline`：

- 按因果顺序排列，支持进度滑杆与防剧透；
- 实体 chip 打开档案，前后因可跳转，证据可回正文；
- 校验事件 id、引用、因果环与证据引文。

### 术语表与实体出现索引

- `#/glossary` 汇总所有 `type: "term"` 实体，支持搜索、按出现顺序/名称排序、防剧透与档案跳转。
- 档案面板新增“出现位置”：解析器自动索引实体在哪些章/节出现（`site/data/mentions.js`），点击直达正文。
- 星图新增“连接”查询：选择两个实体，BFS 找出当前进度下可见关系中的最短路径并高亮。

---

## 状态、审计与文风

```bash
# 章节 × 变体矩阵、元数据覆盖、下一步
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" status ./my-story

# 证据、剧透泄漏、关系、模式对齐、卷/时间线、未链接高频名
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" audit ./my-story --json

# 基线文风指标 + 复述/元数据漂移 + 金句正则
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" style ./my-story --json
```

- `status` 写 `build/status.json`；缺源文本时会给出搜索建议。
- `audit` 写 `build/audit_report.json`；`--strict` 时 warning 也返回 1。
- `style` 写 `build/style_report.json`：平均句长、句长中位数/p90、对话段比例、段落长度、标点分布、人称、长句比例；对复述变体与作者元数据做漂移告警。

---

## 文风规则（硬性）

**所有由模型生成的文字必须仿照原文或既定文风**：实体 tagline、summary、章节 hook、takeaways、recap、worldview 卡片、证据 note、页脚说明。原文放入项目中，正文本身绝不由模型改写。

- 先做 `content/style_profile.md`：人称、时态、句长、词汇、对话比例、标题习惯、明确不写的东西、3–5 段原文样本。
- 不写金句、不写升华、不替角色下结论、不写空泛评价。
- 不把角色的推测写成叙事事实。
- 写完后用 `story.py style` 检查金句模式、抽象大词与文风漂移。

详细规则见 `skills/story-retelling/SKILL.md` 的「语言风格：必须仿照原文」。

---

## 数据模型

| 文件 | 作用 |
|---|---|
| `project.json` | 项目类型、变体/目录、卷册、章节清单、ready、插图与来源策略 |
| `content/style_profile.md` | 文风约定与原文样本 |
| `content/entities.json` | 实体 + 关系 + 证据 |
| `content/chapter_meta.json` | 每章钩子、登场、takeaways、新词 |
| `content/recap.json` | 前情提要 / 故事前史 + 你现在在哪里 |
| `content/worldview.json` | 世界观概念卡 |
| `content/timeline.json` | 结构化事件线：时间、锚点章节、参与实体、前因/后果、证据 |
| `content/manual_links.json` | 单字名/歧义名人工锚句（`section` 可省略） |
| `content/source_provenance.json` | 源文本来源、用途、许可 |
| `content/illustrations.json` | 插图登记、授权信息、章节/小节位置 |

完整字段见 `engine/content/SCHEMA.md`。

---

## 引擎如何工作

```
txt / epub / docx / html / pdf
   │  ingest_sources.py（可选）
   ▼
源 Markdown（sources/ 或 chapters/）+ 任意变体目录
   │  parse_chapters.py
   │  - 解析 H1/H2/H3 → 章/部/节
   │  - files / variantFiles → 单变体或多变体 variants
   │  - 多字别名自动标注（每章每实体首次）
   │  - 单字名走 manual_links.json（section 可省略）
   │  - 逐字比对每种变体的源文与解析结果
   │  - illustrations.json → 注入 image blocks
   │  - timeline.json → 校验并输出事件线
   │  - 生成 mentions.js 实体出现索引
   ▼
site/data/*.js
   │  build_project / build_singlefile
   ▼
多文件站点 + 单文件 HTML
```

关键点：

- **正文不重打**：9 万字、30 万字都由脚本转换，模型只写元数据；原文放入项目连元数据也可以留空。
- **原文/复述同构**：两版分别解析、分别校验保真；section id 同名时，切换和证据回跳保持位置。
- **任意变体**：`variants` 支持翻译、简本、注释本；没有文件的变体自动跳过，不阻塞构建。
- **卷册与事件线**：目录按卷分组；事件线按因果排序，受进度与防剧透控制。
- **实体出现索引**：档案面板列出实体出现的全部章节/小节，点击直达正文。
- **离线**：无 CDN、无外链字体、无 fetch/module/worker；本地图片随项目构建，单文件内联为 data URI，`file://` 双击可用。
- **防剧透**：`spoilerFrom` 用章节 `order`；档案与星图只显示当前章节及之前。
- **证据回跳**：每条证据带章节 id、section id、原文短引；点击回到正文并高亮。
- **星图**：原生 SVG 力导向图，支持类型筛选、章节滑杆、搜索、缩放、列表兜底。
- **插图**：manifest 驱动；本地文件优先，网页图片只接受开放许可并保留署名与许可信息。

---

## 验收

```bash
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" verify <project>
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" audit <project>
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" style <project>
```

`verify` 检查：

- 每种变体的每章正文与对应源文逐字一致（`fidelityByMode`）
- 关系端点存在
- 证据 section 存在（或可由 quote 唯一定位）、引文逐字命中
- `data-ent` 全部有实体
- 插图 id 唯一、`file` 存在、`alt` 存在、`section` 在目标模式中存在
- 网页来源图片带 `credit` 与 `license`
- 站点无网络依赖（外链脚本/样式/图片、fetch、module、worker）

`audit` 额外检查：

- 无证据/短引文/重复引文/歧义引文
- 剧透泄漏、孤立实体、自环/重复关系
- ready 章节缺元数据、空章节
- 变体 section 结构对齐、字数比异常
- 卷/时间线引用与因果环
- 未链接高频名候选

`style` 检查：

- 金句/升华/抽象大词/替角色下结论等正则
- 基线句长、对话比例、标点、人称、长句比例
- 复述变体与作者元数据的漂移

浏览器手工检查：

- 复述项目：原文/复述切换可用，两版在同一小节对齐
- 原文放入/新建同人：不显示模式切换
- 插图：署名、许可、图注可见；窄屏无横向溢出

---

## 已知限制

- 这是预览版，数据规范与 CLI 仍可能调整。
- 支持范围以 Claude Code 为主；其他宿主尚未验证。
- PDF 摄取依赖可选 `pypdf`；扫描版 PDF 没有文本层，需要外部 OCR。
- “没有原文时默认搜索”由宿主模型的 WebSearch / WebFetch 完成，Python 工具本身不联网；受版权保护的全文不会被写入 `sources/`。
- `fidelity` 证明的是“解析没有丢失/虚构正文”，不证明复述准确、关系正确或文风优秀。
- `audit` 与 `style` 是启发式检查，仍需人工复核；未链接高频名只是候选，不是错误。
- 尚未实现全文搜索、书签/笔记和跨会话续读。
- 大型工具文件（parse / ingest / audit / status）超过 800 行，后续会按职责拆分。

## 许可与贡献

- 许可证：[MIT](LICENSE)
- 更新记录：[CHANGELOG.md](CHANGELOG.md)
- 贡献说明：[CONTRIBUTING.md](CONTRIBUTING.md)
- 问题与建议：请开 GitHub Issue，附上复现命令、`build/parse_report.json` 与 `build/status.json`（可脱敏）。
