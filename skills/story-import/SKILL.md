---
name: story-import
description: "Import existing text as-is into a rich-structured reading site: verbatim body, author-written metadata only, no retold version and no mode toggle. Trigger when the user says 原文放入, 原文阅读站, 导入原文, 直接展示原文, or asks to publish existing chapters without rewriting them."
---

# Story Import（原文放入）

把用户提供的现成文本**原样**做成富结构阅读站。正文只做格式整理，不改写、不重排、不补写；模型只编写元数据。项目没有复述版，阅读站不显示原文/复述切换。

## 产出物

```
<project>/
├── project.json             # kind: "import", modes: ["original"]
├── sources/                 # 原文 Markdown（H1/H2/H3）
├── assets/img/              # 可选插图
├── content/
│   ├── style_profile.md     # 从原文提取的文风样本（写元数据前完成）
│   ├── entities.json        # 人物/势力/地点/术语/事件 + 关系 + 证据
│   ├── chapter_meta.json    # 章节钩子/登场/带走的事
│   ├── recap.json           # 前情提要（可选）
│   ├── worldview.json       # 世界观概念卡（可选）
│   ├── manual_links.json    # 单字名/歧义名的人工锚句
│   └── illustrations.json   # 插图 manifest（可选）
├── site/                    # 多文件阅读站
├── dist/<slug>.html         # 单文件，双击即开
└── build/parse_report.json  # 解析与校验报告
```

## 核心原则

1. **正文逐字保留**：`sources/*.md` 是唯一正文来源。不要润色、改词、合并段落、补过渡句或"修正"原文。
2. **只写元数据**：可以写档案、关系、证据、钩子、前情提要；这些是模型生成的文字，必须仿照原文风格。
3. **没有复述版**：不要创建 `retold/`，不要在 `project.json` 里写 `retoldFiles`。
4. **切换保持隐藏**：`modes` 只有 `["original"]`；阅读器在只有一种模式时不显示切换按钮。
5. **证据可回溯**：每条档案事实尽量配一条原文短引；引文必须逐字来自 `sources/`。

## 语言风格：元数据仿照原文

正文不需要仿写，但**所有由你生成的文字**——实体 tagline、summary、章节 hook、takeaways、recap、worldview 卡片、证据 note、页脚说明——都要是原文风格的延续。

写之前先从原文摘 3–5 段有代表性的文字（叙述、对话、小节标题各至少一段），写进 `content/style_profile.md`：

```markdown
# 风格样本

## 叙述人称与时态
## 句子长度与节奏
## 词汇
## 对话比例
## 章节与小节标题
## 原文明确避免的东西
## 3 段原文样本
```

规则：

- 能沿用原文的词就沿用：人物称呼、术语、组织名、章节用词。
- 句子长度贴近原文；原文短，不要写长排比。
- 只写原文能支撑的内容；找不到依据就删。
- takeaways 写"发生了什么、谁做了什么、结果是什么"，不写"这告诉我们……"。
- 证据 note 只说明"这条证据证明什么"。
- 禁止金句、升华、抽象大词、替角色下结论、空泛评价。

## 工作流

> 命令中的 `$CLAUDE_PLUGIN_ROOT` 指插件根目录。如果环境没有这个变量，替换成 `~/.claude/skills/story-forge`。

### 0. 确认范围

- 源文本在哪？格式是 txt / epub / pdf / docx / Markdown？
- 包含哪些章节？本次交付哪几章？
- 是否需要单文件分享版？
- 是否需要档案、前情提要、星图等元数据，还是只做纯阅读站？

### 0.5 源文本获取（没有原文时默认搜索）

如果用户只给了作品名、`sources/` 为空，不要先停下来要文件：

1. 运行 `python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" source-check <project> --json`。
2. `next` 为 `search_original` 时，按返回的 `searchPlan.queries` 用 WebSearch 查找，再用 WebFetch 读取候选页；至少检查官方、公有领域、开放许可来源。
3. **每次搜索后必须记录**：

   ```bash
   python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" source-check <project> \
     --record-search --outcome not_found \
     --query "…" --candidate "标题|URL|reference" --notes "…"
   ```

4. 只把有权使用的全文写进 `sources/`；受版权保护的作品只把可靠页面记为 `kind: "reference"`。
5. 在 `content/source_provenance.json` 登记来源、用途与许可。
6. 找不到时先记录 `not_found`，再如实说明已试查询与缺口，请用户提供文件。

**在记录搜索尝试之前，不要直接向用户要文件。** 完整规则见 `skills/story-source/SKILL.md`。

### 1. 创建项目

```bash
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" new <project> --template import \
  --title "故事标题" --subtitle "读者定位" --slug "story-slug"
```

模板会生成 `kind: "import"`、`modes: ["original"]`、`sourceDir: "sources"`。

### 2. 把原文转成 `sources/*.md`

- txt/epub/pdf 先提取文本；epub 可用 `epub` 技能或解压 XHTML。
- 每章一个文件，用两位序号：`01.md`、`02.md`……
- 只做结构整理，不改正文：

```markdown
# 第一章 标题：副标题

（章节导语，如果原文有）

## 第一幕 · 幕名

### 场景标题

原文段落……
```

- H1 = 章，H2 = 部，H3 = 节。
- 去掉页眉、页码、重复的章节导航；不要合并或拆分原文句子。
- 一章被拆成上/中/下时，用 `mode: "files"`，每个文件一部，H1 写部标题。
- 原文中的 `**加粗**`、`*斜体*`、列表、引用可以保留；不要手写 HTML。

### 3. 配置 `project.json`

- 填 `title`、`subtitle`、`lede`、`footerNote`。
- 填 `chapters`：`id`、`order`、`files`、`mode`。
- `ready` 先只放已完成元数据的章节；其余显示"待续"。没有元数据时，`ready` 留空会自动使用有 meta 的章节，若也没有 meta 则包含全部章节。

### 4. 写 `content/style_profile.md`

先从原文提取风格样本。即使只做纯阅读站，也建议保留这份文件，便于后续补元数据。

### 5. 解析并检查保真

```bash
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" parse <project>
```

检查 `build/parse_report.json`：

- `fidelity` 必须为 `true`；
- `fidelityByMode["ch1:original"]` 必须为 `true`；
- 查看 `build/chapters.json` 里的 `parts[].sections[].id`，后面写证据要用这些 section id。

fidelity 比较的是 `sources/` 与解析结果。若失败，先修 Markdown 结构，不要改解析器。

### 6. 编写元数据（可选，按顺序）

#### 6.1 worldview.json

6–12 张概念卡，覆盖读者进入第一章前必须懂的概念。每张卡有一句话定义、3–5 句解释、关联实体 id。

#### 6.2 entities.json

先列实体，再连关系，最后补证据：

- 人物、势力、地点、术语、事件。
- `aliases` 只放长度 ≥ 2 的别名；单字名走 `manual_links.json`。
- `summary` 只写 `spoilerFrom` 之前的事实，80–150 字。
- `evidence` 的 `chapter` 用章节 id，`section` 用解析报告里的 section id，`quote` 必须逐字来自原文。

#### 6.3 manual_links.json

只用于单字名、易误伤的短名，或需要精确指定位置的情况。每章每个单字名标 1–3 处。

#### 6.4 chapter_meta.json

每章写 `codename`、`hook`、`epigraph`、`readingMinutes`、`cast`、`takeaways`、`newTerms`。

#### 6.5 recap.json

`eras` 覆盖正文之前的剧情；`whereYouAre` 把读者放到第一章入口的状态。原文已经是完整故事时，这两部分可以留空或省略。

### 7. 可选：插图

- 本地图片放进 `assets/img/`，在 `content/illustrations.json` 登记（字段见 SCHEMA.md 第 9 节）。
- 也可以抓取开放许可图片：

```bash
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" fetch-images <project> \
  --query "关键词" --chapter ch1 --limit 2
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" place-images <project> --apply
```

- 网页来源图片必须带 `credit` 与 `license`；受版权保护的官方美术/同人图只能由用户提供本地文件并自行确认权利。
- 单模式项目不必设置 `mode`；保持默认 `both` 即可，解析器会把它映射到唯一模式。

### 8. 构建与验收

```bash
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" build <project> --single
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" verify <project>
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" audit <project>
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" style <project>
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" status <project>
```

必须全绿：

- 每章 `fidelity = true`；
- 关系端点存在；
- 证据 section 存在（或可由 quote 唯一定位）、引文逐字命中；
- `data-ent` 全部有实体；
- 插图 id 唯一、文件存在、`alt` 存在、section 存在、网页图片带 credit/license；
- 站点无外链脚本/样式/图片、无 fetch/module/worker；
- 时间线/卷册引用有效，因果无环；
- `audit` 无 error，`style` 无未处理的严重警告。

浏览器检查：

- 阅读站不显示原文/复述切换；
- 首页 → 阅读 → 档案 → 证据回跳；
- 档案“出现位置”可跳到对应小节；
- 事件线（如有）进度滑杆与防剧透生效；术语表（如有）搜索/排序可用；
- 主题 / 字号 / 防剧透 / 刷新后位置恢复；
- 375 / 768 / 1440 三档宽度无横向溢出。

## 最小可行示例

只做一章纯阅读站：

1. `sources/01.md` 一章，正文逐字；
2. `project.json` 填 `chapters` 与 `ready: ["ch1"]`；
3. `parse`，确认 `fidelity: true`；
4. `build --single` + `verify`。

要档案时再补：8–12 个实体、10–15 条关系、4 张世界观卡、一条 chapter_meta。

## 常见错误

| 错误 | 后果 | 修正 |
|---|---|---|
| 润色或补写原文 | 不再是"原文放入"，fidelity 也会失败 | 只整理结构，正文逐字保留 |
| 创建 `retold/` 或写 `retoldFiles` | 项目变成双模式，切换按钮出现 | 删除复述目录与字段 |
| 手工重打正文 | 丢字、改写、不可维护 | 用脚本解析 |
| 改解析器来"修"保真失败 | 隐藏了真实差异 | 修 `sources/*.md` 结构 |
| `aliases` 放单字名 | "这里/心里"全被标注 | 移到 `manual_links` |
| 证据引文凭记忆写 | 校验失败 / 事实失真 | 从原文复制精确短句 |
| `spoilerFrom` 用章节 id | 防剧透比较错误 | 用章节 `order` |
| 网页图片只抄 URL | 远程热链被拒绝，站点不通过校验 | 下载到 `assets/img/` 并登记 |
