# Story Forge 数据规范

所有内容文件都在项目根目录的 `content/` 下。正文只由脚本解析，模型只编写这里的结构化元数据。项目类型决定了正文目录和阅读模式：

| kind | modes | 目录 | 阅读器 |
|---|---|---|---|
| `import` | `["original"]` | `sources/` | 只有原文，不显示切换 |
| `retelling` | `["original","retold"]` | `sources/` + `retold/` | 显示原文/复述切换 |
| `creation` | `["retold"]` | `chapters/` | 只有创作，不显示切换 |

> `project.json` 的 `variants` 可以声明任意变体（翻译、简本、注释本等）。声明后，上表的模式与目录只作为兼容回退；实际可用模式、标签与目录以 `variants` 为准。见第 1.3 节。

## 0. content/style_profile.md（先写）

在写任何正文或元数据之前完成。内容见 `engine/content/style_profile.template.md`：

- 叙述人称、时态、叙述距离
- 句子长度与节奏
- 词汇、术语解释方式
- 对话比例与角色说话习惯
- 章节标题写法
- 明确不写的东西
- 3–5 段原文样本

**硬性规则**：所有实体 tagline / summary、章节 hook、takeaways、recap、worldview 卡片、证据 note，都必须仿照这份风格。不要写金句、不要升华、不要替角色下结论。原文放入项目的正文本身不得由模型改写。

构建后用 `python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" style <project>` 检查。

## 1. project.json

```jsonc
{
  "slug": "my-story",                 // 输出文件名
  "title": "故事标题",
  "subtitle": "副标题 / 阅读站定位",
  "description": "搜索与分享描述",
  "lede": "首页导语，一段就够",
  "eyebrow": "MY STORY · VOL.1",      // 首页小标签，可留空
  "brand": { "mark": "STORY", "name": "ARCHIVE" },
  "footerNote": "页脚第一行",
  "footerDetail": "页脚说明，可留空",

  "kind": "import",                   // import | retelling | creation
  "modes": ["original"],              // ["original"] | ["original","retold"] | ["retold"]
  "defaultMode": "original",          // 首次进入章节显示的模式
  "primaryMode": "original",          // 主正文模式；没有 variantFiles 时回退到它
  "sourceDir": "sources",             // import/retelling: sources；creation: chapters
  "retoldDir": "retold",              // 仅 retelling 使用
  "sourcePolicy": "required",         // required | optional | none
  "basedOn": "",                      // 可选：同人所依据的原作名（用于 source-check 搜索）
  "modeLabels": {                     // 阅读器按钮文字
    "original": "原文",
    "retold": "复述"
  },
  "variants": [                       // 可选：任意变体；省略时按 kind 合成
    { "id": "original", "label": "原文", "dir": "sources", "primary": true },
    { "id": "retold",   "label": "复述", "dir": "retold" },
    { "id": "en",       "label": "English", "dir": "translations/en" }
  ],
  "volumes": [                        // 可选：卷/篇章分组
    {
      "id": "vol1",
      "title": "第一卷 雾港",
      "subtitle": "",
      "order": 1,
      "chapters": ["ch1", "ch2"]      // 或用 from/to（按章节 order）
    }
  ],

  "illustrations": {
    "enabled": true,
    "dir": "assets/img",
    "autoPlace": true,
    "maxPerChapter": 4,
    "defaultMode": "both",
    "sources": ["local", "wikimedia", "openverse"],
    "licenseAllow": ["public-domain", "cc0", "cc-by", "cc-by-sa"]
  },

  "siteDir": "site",
  "dataDir": "site/data",
  "titleSeparator": "：",              // H1 标题与副标题的分隔符
  "accentPalette": ["#e23a4e", "#7fd6d6", "#c9a227", "#d98c5f", "#6fbf8f", "#7a9fe2"],
  "ready": ["ch1", "ch2"],            // 已可阅读的章节 id
  "chapters": [
    {
      "id": "ch1",                    // 稳定 id，用于路由、证据、meta
      "order": 1,                     // 阅读顺序，也是 spoilerFrom 的数值基准
      "title": "第一章 标题",          // 可省略，省略时取 H1
      "subtitle": "副标题",            // 可省略，省略时按 titleSeparator 从 H1 拆
      "files": ["01.md"],             // 相对 sourceDir / 主变体目录
      "retoldFiles": ["01.md"],       // 相对 retoldDir；仅 retelling
      "variantFiles": {               // 任意变体：变体 id -> 文件列表
        "retold": ["01.md"],
        "en": ["01.en.md"]
      },
      "volume": "vol1",               // 可选：所属卷 id
      "mode": "parts",                // parts: H1 章 / H2 部 / H3 节
                                       // files: 每个文件一部，H1 部标题 / H2 节
      "defaultMode": "retold"         // 可选：覆盖项目级 defaultMode
    }
  ]
}
```

### 1.1 三种模板

`scripts/story.py new --template ...` 写入以下组合：

| template | kind | modes | defaultMode | primaryMode | sourceDir | retoldDir | sourcePolicy | modeLabels |
|---|---|---|---|---|---|---|---|---|
| `import` | `import` | `["original"]` | `original` | `original` | `sources` | — | `required` | 原文 |
| `retelling` | `retelling` | `["original","retold"]` | `retold` | `original` | `sources` | `retold` | `required` | 原文 / 复述 |
| `creation` | `creation` | `["retold"]` | `retold` | `retold` | `chapters` | — | `optional` | 创作（阅读器对 creation 固定显示） |

三种模板都会写入对应的 `variants` 数组。`sourcePolicy` 决定 `source-check` 是否把“缺少原文”视为必须处理：import/retelling 为 `required`，creation 为 `optional`。

### 1.2 规则

- `variants` 声明变体顺序、标签、目录与主变体。未声明时按 kind 合成：import → `original`；retelling → `original` + `retold`；creation → `retold`。
- 主变体（`primary: true`，只能有一个）使用章节的 `files`；其他变体使用 `variantFiles[id]`。`retoldFiles` 是 `variantFiles.retold` 的兼容别名。
- 没有文件的变体不会进入该章节的 `modeNames`；主变体必须有文件。缺省变体只影响该章节，不阻塞构建。
- `retoldFiles` / `variantFiles` 指向的文件名与 `files` 一一对应。变体之间应保持相同的 H1/H2/H3 结构，切换和证据才能按 section id 对齐。
- `defaultMode` 优先取章节级，其次项目级；不在该章可用模式中时，回退到 `retold`，再回退到第一个模式。
- `primaryMode` 是主变体 id；没有 `variantFiles` 的章节只解析主变体。
- 省略 `chapters` 时，自动发现主变体目录下所有 `.md`（排除 `README.md`），按文件名排序，生成 `ch1..chN`；这种自动发现不会生成 `variantFiles`。
- `order` 必须从 1 开始且唯一；所有 `spoilerFrom` 都用它。
- `ready` 非空时只包含这些章节为“可读”；为空时依次回退到“有 chapter_meta 的章节”“全部章节”。`ready` 不包含的章节在目录里显示“待续”。
- `volumes` 可选。每个卷用 `chapters` 明确列出成员，或用 `from`/`to` 按 order 推导；章节也可写 `volume`。同一章只能属于一个卷，未知卷会在解析时给出 warning。
- `sourcePolicy`：`required`（import/retelling）缺少源文本时 `source-check` 返回 `search_original`；`optional`（creation）允许直接写作，`basedOn` 存在时返回 `search_reference`。
- `illustrations` 是项目级插图配置。`place-images` 读取 `maxPerChapter` 作为默认上限；其余字段用于记录项目约定（`enabled` 是否启用、`dir` 图片目录、`autoPlace` 是否期望自动放置、`defaultMode` 默认注入模式、`sources` 允许来源、`licenseAllow` 允许许可证），实际执行以 CLI 参数和工具内置许可规则为准。

## 2. 解析输出：单变体与多变体章节

`parse_chapters.py` 写入 `build/chapters.json` 和 `site/data/chapters.js`。章节对象有两种形状。

### 2.1 单模式章节（import / creation / 没有 retoldFiles 的 retelling 章节）

```jsonc
{
  "id": "ch1",
  "order": 1,
  "title": "第一章 标题",
  "subtitle": "副标题",
  "volume": "vol1",                 // 仅当 project.json 声明了 volumes
  "modeNames": ["original"],        // creation 为 ["retold"]；其他变体同理
  "defaultMode": "original",
  "parts": [ /* 部 → 节 → blocks */ ],
  "sources": [ /* {label,url} */ ],
  "related": [ /* {label,url} */ ],
  "hanzi": 12345,
  "chars": 12400,                   // CJK + Latin letters/digits，供翻译变体统计
  "hanziByMode": { "original": 12345 },
  "charsByMode": { "original": 12400 }
}
```

顶层直接有 `parts`、`sources`、`related`、`hanzi`。

### 2.2 多变体章节（有 variantFiles / retoldFiles）

```jsonc
{
  "id": "ch1",
  "order": 1,
  "title": "第一章 标题",             // 取 defaultMode 的标题
  "subtitle": "副标题",
  "modeNames": ["original", "retold"],
  "defaultMode": "retold",
  "hanzi": 11800,                     // defaultMode 的汉字数
  "chars": 11920,                     // defaultMode 的字符数（CJK + 字母/数字）
  "hanziByMode": { "original": 12345, "retold": 11800 },
  "charsByMode": { "original": 12400, "retold": 11920 },
  "variants": {
    "original": {
      "parts": [ /* ... */ ],
      "sources": [ /* ... */ ],
      "related": [ /* ... */ ],
      "hanzi": 12345,
      "title": "第一章 标题",
      "subtitle": "副标题"
    },
    "retold": {
      "parts": [ /* ... */ ],
      "sources": [],
      "related": [],
      "hanzi": 11800,
      "chars": 11920,
      "title": "第一章 标题",
      "subtitle": "副标题"
    }
  }
}
```

多变体章节**没有顶层 `parts` / `sources` / `related`**；读取正文时必须先选 `variants[mode]`。`hanzi` 保留为 defaultMode 的字数，供首页/目录显示。

### 2.3 图片块

解析器把 `content/illustrations.json` 中的登记项插入目标 section 的 `blocks`：

```jsonc
{
  "type": "image",
  "src": "assets/img/lighthouse.jpg",
  "alt": "夜里的灯塔",
  "caption": "灯塔在雾中亮起",
  "credit": "摄影者 / 机构",
  "license": "CC BY-SA 4.0",
  "sourceUrl": "https://commons.wikimedia.org/...",
  "width": 1600,
  "height": 900,
  "imageId": "img-lighthouse"
}
```

- 多变体章节的图片可能同时出现在 `variants.original` 与 `variants.retold`（或其他变体）的对应 section 中。
- `src` 始终是项目相对路径；构建时复制到 `site/assets/`，单文件构建内联为 data URI。

### 2.4 build/parse_report.json

```jsonc
{
  "chapters": 6,
  "fidelity": true,
  "fidelityByMode": {
    "ch1:original": true,
    "ch1:retold": true
  },
  "errors": [],
  "warnings": [],
  "hanzi": 93520,
  "hanziByMode": { "original": 93520, "retold": 91000 },
  "charsByMode": { "original": 93800, "retold": 91240 },
  "illustrations": 12
}
```

- `fidelity` 是所有模式全部章节的总结果。
- `fidelityByMode` 的 key 是 `<chapterId>:<mode>`；双文本项目必须逐项为 `true`。
- `warnings` 包含插图模式/小节缺失等非阻塞问题。

## 3. content/entities.json

```jsonc
{
  "entities": [
    {
      "id": "lucia",                  // 唯一，字母数字下划线
      "type": "character",            // character | faction | location | term | event
      "name": "露西亚",
      "aliases": ["露西亚"],          // 只放长度 >= 2 的别名；单字名走 manual_links
      "tagline": "一句话认识",
      "summary": "80–150 字档案，只写当前 ready 章节能支撑的信息",
      "spoilerFrom": 1,               // 从第几章（order）起可展示；0 = 前情提要可见
      "firstAppear": 1,               // 首次出现章节 order；0 = 前情提要
      "icon": "露",                   // 1 个字
      "color": "#e23a4e",
      "evidence": [
        {
          "chapter": "ch1",           // 章节 id
          "section": "sch1-1-1",      // 可省略：解析器按 quote 在章内唯一定位
          "quote": "原文中的精确短句",  // 必须是该节正文的精确子串
          "note": "这条证据说明什么"
        }
      ]
    }
  ],
  "relations": [
    {
      "from": "lucia",
      "to": "commander",
      "label": "指挥 / 同行",
      "kind": "ally",                 // ally | hostile | family | mentor | contract | unknown
      "spoilerFrom": 1
    }
  ]
}
```

规则：

- **证据引文必须逐字来自正文**，构建时会校验；不要凭记忆改字。省略 `section` 时，解析器会在该章所有变体的所有小节中查找 quote：唯一命中会自动补上 section；多处命中或找不到会报错并列出候选。
- 双文本项目中，同一个 `section` id 可能同时存在于 `original` 与 `retold`；引文只要能在该 section 的任一模式中找到即可，建议引原文。
- 每条实体给 1–3 条证据；重要实体 3 条。
- 实体总量建议 40–100；关系 1–2 倍于实体。
- `summary` 只写到 `spoilerFrom` 为止的事实；后续章节的事放后续版本。
- `aliases` 不要放“里”“迅”这类单字名，也不要放“德斯”这种会从“科德斯”里截出的片段。
- 同名不同身份（例如复制体/本体）必须是两个实体，用关系表达。

## 4. content/chapter_meta.json

```jsonc
{
  "ch1": {
    "codename": "THE LIGHTHOUSE",
    "hook": "本章钩子，1–2 句",
    "epigraph": "可选题记",
    "readingMinutes": 12,
    "cast": ["lucia", "commander"],   // 章节封面的人物条
    "takeaways": ["章末带走的三到五件事"],
    "newTerms": ["term-id"]           // 章末新词卡
  }
}
```

章节元数据按章节 id 共用，不区分模式。

## 5. content/recap.json

```jsonc
{
  "title": "在进入第一章之前",
  "kicker": "STORY SO FAR",
  "lede": "为什么需要这段前情",
  "eras": [
    {
      "id": "era-1",
      "label": "很久以前",
      "title": "时代标题",
      "summary": "2–4 句概述",
      "beats": ["要点一", "要点二"]
    }
  ],
  "whereYouAre": {
    "title": "你现在在哪里",
    "text": "把读者放到第一章入口的状态",
    "checklist": ["人物甲：此刻在做什么", "人物乙：此刻在做什么"]
  }
}
```

复述/原文放入项目：`eras` 覆盖正文之前的章节；新建同人项目：`eras` 可以当作故事前史/大纲。

## 6. content/worldview.json

```jsonc
{
  "cards": [
    {
      "id": "wv-1",
      "entity": "term-id",            // 点击卡片会打开该实体档案
      "title": "概念名",
      "oneLiner": "一句话定义",
      "body": "零基础读者需要知道的解释，3–5 句"
    }
  ]
}
```

建议 6–12 张卡，覆盖读者进入第一章必须懂的概念。

## 7. content/manual_links.json

只用于单字名、易误伤的短名，或需要精确指定位置的情况。

```jsonc
{
  "links": [
    {
      "chapter": "ch1",
      "section": "sch1-1-1",              // 可省略：按 quote 在章内唯一定位
      "quote": "里注意到的则是医生签名",   // 该节正文的精确子串
      "entity": "lee",
      "target": "里",                     // quote 中要包住的那一段
      "note": "可选说明"
    }
  ]
}
```

规则：

- 每个单字名每章标 1–3 处即可，不要全篇标。
- `quote` 必须唯一且逐字来自正文。省略 `section` 时会在章内唯一定位；多处或找不到会报错。
- 自动标注已经保证每章每个实体只标首次；manual 是补充，不要重复。
- 双文本项目中，`section` 使用两版共用的 id；标注会分别应用到存在的模式。

## 8. 正文 Markdown 约定

```markdown
# 第一章 标题：副标题

（章节导语）

## 第一幕 · 幕名

（部导语）

### 场景标题

正文段落……

> 引用段落

- 列表项
```

- H1 = 章；H2 = 部（`mode: "parts"`）或节（`mode: "files"`）；H3 = 节。
- 正文中的 `**加粗**`、`*斜体*`、`` `代码` ``、`[链接](url)` 会被渲染；链接会移到章末“来源与延伸”。
- 以“剧透”开头的段落会渲染成阅读提示；以“依据/关键资料”开头的段落会渲染成来源注。
- 不要手写 HTML。不要直接在 Markdown 里插入图片；图片统一登记在 `content/illustrations.json`，由解析器注入 image block。
- 复述项目的 `sources/` 与 `retold/` 使用相同的 H1/H2/H3 骨架；正文措辞可以不同。
- 原文放入项目的 `sources/` 必须逐字保留用户提供的正文，只整理标题层级和页眉页码。

## 9. content/illustrations.json

插图 manifest 是唯一图片来源。文件结构：

```jsonc
{
  "images": [
    {
      "id": "img-lighthouse",          // 唯一；缺失时会回退到 file/src，但建议显式写
      "file": "assets/img/lighthouse.jpg", // 项目相对路径，必须本地存在
      "alt": "雾中的灯塔",              // 必填
      "caption": "灯塔在夜里亮起",       // 可选图注
      "credit": "摄影者 / 机构",         // 网页来源必填
      "license": "CC BY-SA 4.0",        // 网页来源必填
      "sourceUrl": "https://commons.wikimedia.org/wiki/File:...", // 来源页；本地文件可空
      "source": "wikimedia",            // local | wikimedia | openverse
      "width": 1600,                    // 可选，用于减少布局偏移
      "height": 900,
      "chapter": "ch1",                 // 必须是存在的章节 id
      "section": "sch1-0-1",            // 必须是目标模式中存在的 section id
      "afterBlock": 0,                  // 插入位置，0 起；省略时插入节末尾
      "mode": "both",                   // both | original | retold
      "status": "placed",               // unplaced | placed
      "placement": "keyword",           // keyword | even，由 place-images 写入
      "keywords": ["灯塔", "雾"]         // 用于按文字重叠度选小节
    }
  ]
}
```

### 9.1 字段与行为

- `id`：唯一。重复 id 会校验失败。
- `file`：项目相对路径，必须是本地文件。`http://` / `https://` 开头会被拒绝（不允许远程热链）。
- `alt`：必须有这个键；网页图片应写有意义的替代文字。
- `chapter`：必须是 `project.json` 中存在的章节 id。
- `section`：必须是目标模式中存在的 section id；未分配时 `place-images --apply` 会补上。双文本项目建议两版使用相同 section id。
- `mode`：`both` / `all` / 空值表示注入所有可用模式；否则必须是该章节可用的 `original` 或 `retold`。目标模式全部不可用会校验失败。
- `afterBlock`：在 section 的 `blocks` 中从 0 开始插入；省略时插入末尾。`place-images` 会给新放置的条目写入 0。
- `status` / `placement`：`place-images` 的工作状态；`status: "placed"` 且已有 `section` 的条目会被跳过。
- `sourceUrl` 非空时，`credit` 与 `license` 都必须非空，否则校验失败。
- 抓取工具的本地来源会写 `license: "user-provided"`、`credit: "本地提供"`、空 `sourceUrl`；网页来源写 API 返回的作者、许可证与来源页。
- `fetch-images` 只接受 Wikimedia Commons、Openverse 的开放许可结果（public domain / CC0 / CC BY / CC BY-SA 等）或 `--local-dir` 中用户提供的文件；下载仅允许 https、必须是图片内容，单文件上限 20 MB，默认最小宽度 800。
- 受版权保护的官方美术、同人图：只能由用户提供本地文件并自行确认权利，抓取工具不负责获取。

### 9.2 多变体中的图片

- `mode: "both"` 会尝试注入 `original` 与 `retold`；某个模式缺少该 `section` 时，只注入存在的模式并产生 warning。
- 只想在复述版显示时用 `mode: "retold"`；只想在原文显示时用 `mode: "original"`。
- 新建同人只有 `retold` 一种模式，保持 `both` 即可。

## 10. 构建、校验与 CLI

```bash
# 新建项目
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" new <project> \
  --template import|retelling|creation --title "…" --slug "…"

# 原文摄取：txt / md / epub / docx / html / pdf（pdf 需要可选 pypdf）
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" ingest <project> <source> \
  [--to sources] [--dry-run] [--force] [--update-project] [--extract-images]

# 解析 / 构建 / 校验 / 单独生成单文件
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" parse  <project> [--check]
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" build  <project> [--single] [--sync-template]
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" verify <project>
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" single <project>

# 项目状态 / 内容审计 / 文风量化
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" status <project> [--json] [--strict]
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" audit  <project> [--json] [--strict]
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" style  <project> [--json] [--strict] [--no-metrics]

# 源文本与来源检查（不联网，只给建议）
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" source-check <project> \
  [--json] [--strict] [--write-template]
```

`build` 会先跑解析与校验，再把项目 `assets/` 复制到 `site/assets/`；`--single` 继续生成 `dist/<slug>.html` 并把本地图片内联为 data URI。

### 10.1 插图 CLI

```bash
# 分配小节；不加 --apply 是 dry-run
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" place-images <project> \
  --apply [--chapter ch1] [--max-per-chapter N]

# 抓取开放许可图片或复制本地文件
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" fetch-images <project> \
  --query "关键词" [--chapter ch1] [--section sch1-0-1] \
  [--source auto|wikimedia|openverse|local] [--local-dir PATH] \
  [--limit N] [--mode both|original|retold] [--dry-run]
```

`fetch-images` 的补充参数：`--after-block N`、`--min-width N`（默认 800）、`--id NAME`、`--assets DIR`（默认 `assets/img`）。`--dry-run` 只列出候选，不改 manifest。

典型顺序：

```bash
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" parse <project>
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" fetch-images <project> --query "…" --chapter ch1 --limit 2
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" place-images <project> --apply
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" build <project> --single
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" verify <project>
```

### 10.2 校验内容

- 每种变体的每章正文汉字序列与对应源文逐字一致（无丢失、无虚构）。
- 所有关系端点存在；所有证据 section 存在（或可由 quote 唯一定位）；证据引文能在对应小节找到。
- 所有 `data-ent` 都有实体；meta 的 cast/newTerms 都有实体。
- 插图 id 唯一、`file` 本地存在、`alt` 存在、`section` 在目标模式中存在、`mode` 可用；网页图片带 `credit` 与 `license`。
- 卷 id 唯一、章节只属于一个卷；时间线事件 id 唯一、引用存在、无环。
- 站点无外链脚本/样式/图片、无 fetch/module/worker（离线可用）。

## 11. content/timeline.json

结构化事件线，独立于 `recap.json` 的散文式前情。阅读器路由 `#/timeline`。

```jsonc
{
  "title": "事件线",
  "kicker": "TIMELINE",
  "lede": "从交班到风暴里的求救。",
  "events": [
    {
      "id": "ev-handover",           // 唯一
      "title": "交班",
      "summary": "林岚把钥匙、值班表和手电交给沈舟。",  // 仿照原文风格
      "chapter": "ch1",              // 锚点章节；用于防剧透与排序
      "storyTime": "第一天 16:00",   // 可选，故事内时间
      "order": 1,                    // 可选，显示顺序；省略时按章节 order + 索引
      "entities": ["shenzhou", "linlan"],
      "causes": [],                  // 前因事件 id
      "consequences": ["ev-signal"], // 后果事件 id
      "spoilerFrom": 1,              // 第几章起可见；省略时用锚点章节 order
      "evidence": [
        {
          "chapter": "ch1",
          "section": "sch1-0-1",     // 可省略：按 quote 唯一定位
          "quote": "林岚在值班室等他。",
          "note": "交班"
        }
      ]
    }
  ]
}
```

规则：

- `id` 唯一；`entities`、`chapter`、`causes`、`consequences` 必须引用存在的实体/章节/事件。
- 因果图为有向图：cause → event → consequence；出现环会校验失败。
- 事件证据与实体证据使用同一套校验规则（逐字命中、section 存在或可唯一定位）。
- `spoilerFrom` 大于锚点章节 order 会报错；阅读器只显示当前进度及之前的 event。
- 没有 `timeline.json` 时，解析器写入空事件线，页面显示空状态，不影响构建。

## 12. content/source_provenance.json

记录源文本从哪里来、用途和许可。`source-check` 与 `status` 会读取它。

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
      "kind": "primary-text",      // primary-text | reference
      "license": "public-domain",  // public-domain | cc0 | cc-by | cc-by-sa | user-provided | licensed | unknown
      "notes": "章节 1–12；来源页标注公有领域"
    }
  ]
}
```

规则：

- `kind: "reference"` 只用于 wiki、剧情总结、攻略等参考资料，不能作为 `sources/` 正文。
- 只有 public-domain / CC / user-provided / licensed 的 `primary-text` 才被视为可用的主文本。
- import / retelling 的 `sourcePolicy` 通常是 `required`；creation 为 `optional`，可用 `basedOn` 指定原作。

## 13. 状态、审计与文风报告

构建目录下的报告都是生成物，不要手工编辑：

| 文件 | 生成命令 | 用途 |
|---|---|---|
| `build/parse_report.json` | `parse` / `build` | 保真、错误、warning、字数、插图数 |
| `build/status.json` | `status` | 章节 × 变体矩阵、元数据覆盖、下一步 |
| `build/audit_report.json` | `audit` | 证据、剧透泄漏、关系、对齐、卷/时间线、未链接名候选 |
| `build/style_report.json` | `style` | 基线文风指标、变体漂移、元数据漂移 |
| `build/ingest_report.json` | `ingest` | 摄取格式、编码、章节、丢失比例、来源哈希 |

`parse` 还会生成 `site/data/mentions.js`（`window.STORY_MENTIONS`）：实体 → 出现的小节列表，用于档案面板的“出现位置”。它只统计长度 ≥ 2 的名称/别名，并受防剧透过滤。
