---
name: story-retelling
description: "Turn an existing novel, game story, fanfic, or chapter text into a zero-foundation, rich-structured reading site with original/retold mode switching: recap, worldview cards, character/faction/location/term/event dossiers, relationship graph, evidence links, anti-spoiler, and illustrations. Trigger when the user says 小说复述, 剧情重构, 零基础阅读, 富结构阅读, 人物关系图, 世界观导读, 原文/复述切换, 把小说/剧情做成阅读站, or asks to adapt existing chapters into an interactive reader."
---

# Story Retelling

把一个**已有的故事**（小说、游戏剧情、同人、剧本）重构成「零基础读者也能无障碍进入」的富结构阅读站。

## 产出物

```
<project>/
├── project.json
├── sources/                 # 原文 Markdown（H1/H2/H3）
├── retold/                  # 复述 Markdown，文件名与结构同 sources/
├── assets/img/              # 本地插图
├── content/
│   ├── style_profile.md     # 原文语言风格样本与规则（先写这个）
│   ├── entities.json        # 人物/势力/地点/术语/事件 + 关系 + 证据
│   ├── chapter_meta.json    # 章节钩子/登场/带走的事
│   ├── recap.json           # 前情提要（时间线 + 你现在在哪里）
│   ├── worldview.json       # 世界观概念卡
│   ├── manual_links.json    # 单字名/歧义名的人工锚句
│   └── illustrations.json   # 插图登记与授权信息
├── site/                    # 多文件阅读站（构建产物）
├── dist/<slug>.html         # 单文件，双击即开
└── build/parse_report.json  # 解析与校验报告
```

## 核心原则

1. **正文不重打**：9 万字、30 万字都交给 `parse_chapters.py` 解析；模型只写结构化元数据。
2. **证据可回溯**：每条档案事实尽量配一条原文短引；构建时逐字校验。
3. **零基础优先**：前情提要、世界观卡、人物一句话、每章钩子与章末回顾，四层缺一不可。
4. **防剧透**：`spoilerFrom` 用章节 `order`；档案与星图只显示当前章节及之前的信息。
5. **少而准的标注**：每章每实体只标首次出现；单字名走人工锚句；标题、剧透提示、来源注不标。
6. **双文本同构**：原文和复述分别放在 `sources/` 与 `retold/`，文件名和 H1/H2/H3 结构一一对应；两版分别解析、分别校验保真。
7. **插图本地化**：图片只从 `assets/img/` 提供；网页来源只接受开放许可，并保留 credit 与 license。

## 双模式：原文与复述

复述项目的 `project.json` 声明两套目录和两种模式：

```jsonc
{
  "kind": "retelling",
  "modes": ["original", "retold"],
  "defaultMode": "retold",      // 首次进入章节显示哪一版
  "primaryMode": "original",    // 没有 retoldFiles 时的主正文模式
  "sourceDir": "sources",
  "retoldDir": "retold",
  "modeLabels": { "original": "原文", "retold": "复述" }
}
```

章节条目同时给出两边的文件：

```jsonc
{
  "id": "ch1",
  "order": 1,
  "files": ["01.md"],        // sources/01.md
  "retoldFiles": ["01.md"],  // retold/01.md
  "mode": "parts"
}
```

规则：

- `retoldFiles` 相对 `retoldDir`；文件名与结构应与 `files` 一一对应。
- 有 `retoldFiles` 的章节解析为双模式；没有的章节只有 `primaryMode`，阅读器不显示切换按钮。
- 只有部分章节完成复述时，先给这些章节写 `retoldFiles`；其余章节按单模式解析（原文仍可阅读），不会阻塞构建。
- 阅读器在章节有多个模式时显示“原文 / 复述”切换。切换时保留当前 section id：两版标题结构一致，就停在同一小节；结构不一致时无法按 section id 对齐，切换后不会自动滚动到对应小节。
- 解析结果中，双模式章节使用 `variants.original` 与 `variants.retold`；单模式章节使用顶层 `parts`。不要手工编辑 `site/data/*.js`。
- 保真检查按模式分别进行：`build/parse_report.json` 的 `fidelityByMode` 会给出 `ch1:original`、`ch1:retold` 两项。
- 证据的 `section` 使用两边共用的 section id。建议证据引原文：解析器会在该 section 的任一模式中校验引文。若两版结构不同，证据定位会不稳定。
- 复述版是重构文本，不是原文的逐字复制；但它的章节/部/节骨架必须与原文一致，否则切换、证据和目录都会错位。

## 语言风格：必须仿照原文（硬性要求）

这条的优先级高于“写得漂亮”。**所有由你生成的文字**——实体 tagline、summary、章节 hook、takeaways、recap、worldview 卡片、证据 note、页脚说明——都必须是原文风格的延续，而不是另一种“文案腔”。

### 写之前：先做风格样本

从原文中选 3–5 段有代表性的文字（叙述、对话、小节标题各至少一段），写成 `content/style_profile.md`：

```markdown
# 风格样本

## 叙述人称与时态
（第一/第二/第三人称；过去/现在时；是否直接称呼“你”）

## 句子长度与节奏
（以短句为主/中长句；平均多少字；是否常用停顿、破折号、分号）

## 词汇
（口语/书面/技术；是否使用术语；是否解释术语；是否用比喻）

## 对话比例
（对话多还是叙述多；对话是否带引号；是否用“他说”）

## 章节与小节标题
（陈述句/疑问句/名词短语；是否用副标题）

## 原文明确避免的东西
（例如：不写金句、不做总结性升华、不替角色下结论）

## 3 段原文样本
（逐字摘录，作为写作时的对照）
```

### 写的时候：规则

1. **能沿用原文的词就沿用**：人物称呼、术语、组织名、章节用词，不换同义词。
2. **句子长度贴近原文**：原文短，就不要写长排比；原文长，就不要硬切成口号。
3. **人称一致**：原文用“你”，recap 和 hooks 可以用“你”；原文是第三人称，就不要突然对读者说话。
4. **只写原文能支撑的内容**：summary 里的每个判断，都要能在原文找到依据；找不到就删。
5. **takeaways 是复述，不是升华**：写“发生了什么、谁做了什么、结果是什么”，不写“这告诉我们……”。
6. **保留原文的解释方式**：原文用具体动作解释动机，就用动作；原文用因果句，就用因果句；不要换成抽象名词。
7. **证据 note 只说明“这条证据证明什么”**，不写感悟。

### 禁止清单

除非原文本身就这样写，否则不要使用：

- 对称金句：“不是 A，而是 B”“与其说 A，不如说 B”“真正的 X 是 Y”
- 升华句：“这意味着”“这正是……的地方”“……才真正开始”
- 抽象名词堆叠：“困境”“宿命”“救赎”“成长的完成”“关系的重量”
- 替角色下结论：“她终于明白”“他终于学会”
- 空泛评价：“令人动容”“意味深长”“充满张力”
- 每段都收一个“点题句”

### 写完之后：自检

随机抽 5 句你写的元数据，和原文放在一起读：

- 这句话放进原文，会不会显得像另一个人写的？
- 有没有比原文多走一步（多解释、多评价、多升华）？
- 有没有把角色的推测写成叙事事实？
- 句子长度、用词、标点，和原文样本像不像？

任何一项答不上来，就改plain，直到它能自然待在原文旁边。

### 自动检查

插件提供风格检查：

```bash
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" style <project>
```

它会扫描 `content/*.json` 中的金句模式和抽象词，给出警告；`--strict` 会直接失败。警告不是绝对规则，但每一条都值得回看原文再改。

## 工作流

> 命令中的 `$CLAUDE_PLUGIN_ROOT` 指插件根目录。如果环境没有这个变量，替换成 `~/.claude/skills/story-forge`。

### 0. 确认范围

先问清楚（能从上下文推断就跳过）：

- 源文本在哪？包含哪些章节？目标交付哪几章？
- 读者是完全没读过前文，还是读过一部分？
- 是否需要单文件分享版？
- 原文语言与格式（txt / epub / pdf / docx / Markdown）？

### 0.5 源文本获取（没有原文时默认搜索）

如果用户只给了作品名、`sources/` 为空，先找原文，不要直接停下来要文件：

1. 运行 `python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" source-check <project> --json`。
2. `next` 为 `search_original` 时，按 `searchPlan.queries` 用 WebSearch 查找，再用 WebFetch 读取候选页；至少检查官方、公有领域、开放许可来源。
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
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" new <project> --template retelling \
  --title "故事标题" --subtitle "读者定位" --slug "story-slug"
```

> 命令中的 `scripts/story.py` 是插件内路径；实际使用时按插件安装位置解析。

### 2. 整理源文本与复述文本

**原文**：

- 把原文转成 Markdown。txt/pdf/epub 先提取文本；epub 可用 `epub` 技能或解压 XHTML。
- 统一结构：

```markdown
# 第14章 标题：副标题

（章节导语）

## 第1部 · 部标题

（部导语）

### 场景标题

正文……
```

- 每章一个文件，放进 `sources/`，文件名用两位序号：`01.md`, `02.md`……
- 如果一章被拆成上/中/下，用 `mode: "files"`，每个文件一部；H1 写部标题。

**复述**：

- 在 `retold/` 写复述版，文件名与 `sources/` 一一对应：`sources/01.md` ↔ `retold/01.md`。
- 复述可以重写句子、补足背景，但**必须保留相同的 H1/H2/H3 骨架**。章、部、节的标题和数量尽量与原文对齐，保证 section id 一致。
- 复述正文同样要按 `style_profile.md` 的语言规则来写，不要写成另一种文案腔。
- 原文放入（import）项目没有复述版；新建同人（creation）只有创作正文。只有复述项目需要 `sources/` + `retold/` 两套。

### 3. 配置 project.json

- 填 `title`, `subtitle`, `lede`, `footerNote`。
- 填 `kind`, `modes`, `defaultMode`, `primaryMode`, `sourceDir`, `retoldDir`, `modeLabels`。
  复述模板已经写好：`kind: "retelling"`、`modes: ["original","retold"]`、`sourceDir: "sources"`、`retoldDir: "retold"`。
- 填 `chapters`：`id`、`order`、`files`、`retoldFiles`、`mode`。两边文件同名同结构时，`retoldFiles` 直接填与 `files` 相同的文件名。
- `ready` 先只放已完成元数据的章节；其余显示“待续”。

先跑一次：

```bash
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" parse <project>
```

检查 `build/parse_report.json`：

- `fidelity` 必须为 `true`；
- `fidelityByMode` 中每章的 `chN:original` 与 `chN:retold` 都必须为 `true`；
- 查看 `build/chapters.json` 里的 `parts[].sections[].id`，后面写证据要用这些 section id。双模式章节在 `variants.original` / `variants.retold` 下查看。

### 4. 编写元数据（按顺序）

#### 4.0 style_profile.md（先做）

在读正文之前，先按上一节的方法提取风格样本。**没有 style_profile，不要开始写 summary、hook、takeaways。** 后面的每一段元数据都要以它为对照。

#### 4.1 worldview.json

先写 6–12 张概念卡。读者进入第一章前必须懂什么？每张卡：

- 一句话定义；
- 3–5 句解释；
- 关联到一个实体 id（点击卡片打开档案）。

#### 4.2 entities.json

先列实体，再连关系，最后补证据。

- 人物：主角、关键配角、反派、只闻其名但影响局势的人。
- 势力：阵营、组织、家族、军队、教会、公司。
- 地点：故事发生的关键空间。
- 术语：世界观概念、技术、病疫、等级、货币。
- 事件：推动关系变化的关键节点（星图与章末回顾共用）。

字段：

```jsonc
{
  "id": "lucia",
  "type": "character",
  "name": "露西亚",
  "aliases": ["露西亚"],          // 只放长度 >= 2 的别名
  "tagline": "一句话认识",
  "summary": "80–150 字，只写 spoilerFrom 之前的事实",
  "spoilerFrom": 1,               // 章节 order
  "firstAppear": 1,               // 0 = 前情提要
  "icon": "露",
  "color": "#e23a4e",
  "evidence": [
    { "chapter": "ch1", "section": "sch1-1-1", "quote": "原文精确短句", "note": "说明" }
  ]
}
```

关系：

```jsonc
{ "from": "lucia", "to": "commander", "label": "指挥 / 同行", "kind": "ally", "spoilerFrom": 1 }
```

`kind`: `ally | hostile | family | mentor | contract | unknown`。

**实体规模**：40–100 个；关系 1–2 倍。不要把所有路人写进来；只收「理解主线必需 + 影响关系网」的。

#### 4.3 manual_links.json

单字名（如「里」「迅」）和容易误伤的短名，永远不要放进 `aliases`。用精确锚句：

```jsonc
{
  "links": [
    {
      "chapter": "ch1",
      "section": "sch1-1-1",
      "quote": "里注意到的则是医生签名",
      "entity": "lee",
      "target": "里"
    }
  ]
}
```

每章每个单字名标 1–3 处即可。

#### 4.4 chapter_meta.json

每章：

- `codename`（英文代号，可选）
- `hook`（1–2 句章钩子）
- `epigraph`（可选）
- `readingMinutes`
- `cast`（本章登场实体 id，6–15 个）
- `takeaways`（3–5 条，读者读完应带走的事）
- `newTerms`（本章新词实体 id）

#### 4.5 recap.json

- `title`: “在进入第 X 章之前”
- `kicker`: “STORY SO FAR”
- `lede`: 为什么需要这段前情
- `eras`: 前史时间线，每条 `label / title / summary / beats`
- `whereYouAre`: 把读者放到第一章入口的状态，`checklist` 用“人物：此刻在做什么”

复述项目里，`eras` 要覆盖正文之前的剧情；如果正文从第 14 章开始，就写 1–13 章的浓缩时间线。

### 5. 插图（可选）

插图登记在 `content/illustrations.json`，本地文件放在 `assets/img/`。字段与校验规则见 `engine/content/SCHEMA.md` 第 9 节。

两种入口：

```bash
# A. 本地图片：把文件放进 assets/img/，手工登记 manifest
#    必填：id、file、alt、chapter；建议填 caption、keywords

# B. 抓取开放许可图片（Wikimedia Commons / Openverse）
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" fetch-images <project> \
  --query "关键词" --chapter ch1 --limit 2

# 分配小节：先 dry-run 看结果，再 --apply
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" place-images <project>
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" place-images <project> --apply
```

- `place-images` 按 `keywords` 与小节正文的重叠度选小节；没有关键词时在章内均匀分布。每章上限默认 4，可用 `--max-per-chapter` 或 `project.json` 的 `illustrations.maxPerChapter` 调整。
- `defaultMode` 为 `both` 时图片注入原文和复述两种模式；建议两版 section id 一致。只想放一版时用 `--mode original` 或 `--mode retold`。
- 网页来源图片必须保留 `credit`、`license`、`sourceUrl`；本地文件也必须写 `alt`。
- 受版权保护的官方美术/同人图：只能由用户提供本地文件并自行确认权利；`fetch-images` 只取 Wikimedia Commons / Openverse 的开放许可图片或 `--local-dir` 中的用户文件。
- 图片不会写进 Markdown 正文；解析器根据 manifest 注入 `{type:"image", ...}` 块。

### 6. 选择 ready 章节并构建

- 编辑 `project.json` 的 `ready`，只放元数据完整的章节。
- 运行：

```bash
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" build <project> --single
```

- 构建会先跑解析与校验，再生成 `site/` 与 `dist/<slug>.html`。

### 7. 验收

```bash
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" verify <project>
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" audit <project>
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" style <project>
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" status <project>
```

必须全绿：

- `fidelity = true`，且 `fidelityByMode` 中每章的每个可用变体都为 `true`（各自与源文逐字一致）
- 关系端点存在
- 证据 section 存在（或可由 quote 唯一定位）、引文逐字命中（在该 section 的任一模式中）
- `data-ent` 全部有实体；所有变体中的标注都检查
- 插图：id 唯一、`file` 本地存在、`alt` 存在、`section` 在目标变体存在、网页图片带 `credit` 与 `license`
- 站点无外链脚本/样式/图片、无 fetch/module/worker
- 变体 section 结构对齐；时间线/卷册引用有效，因果无环
- `audit` 无 error，`style` 无未处理的严重警告

然后在浏览器检查：

- 首页 → 前情提要 → 第一章 → 点击实体 → 档案 → 证据回跳
- 原文/复述切换：按钮出现；切换后停在同一小节；两版标题、目录、字数显示正确
- 主题 / 字号 / 防剧透 / 刷新后位置恢复
- 星图：类型筛选、章节滑杆、搜索、连接查询、点击节点
- 事件线：进度滑杆、前后因跳转、证据回正文
- 术语表：搜索、排序、防剧透、档案跳转
- 档案“出现位置”可跳到对应小节
- 插图：图注、署名、许可可见；单文件打开后图片仍在
- 375 / 768 / 1440 三档宽度无横向溢出

### 8. 迭代

- 新增章节：补 `chapters`、跑 parse、补 meta/entities、更新 `ready`。
- 发现事实错误：先改证据引文与 summary，再跑 verify。
- 发现剧透：调低 `spoilerFrom` 或把内容拆成 `lore` 分段（后续版本）。

## 内容保真清单

写档案时逐条自问：

- [ ] 这句话在原文里有直接依据吗？没有就删。
- [ ] 这是角色「认为」的还是叙事「确认」的？不要把角色推断写成事实。
- [ ] 这是当前章节已知，还是后面才揭晓？后者不能进 `summary`。
- [ ] 有没有把「可能」「疑似」写成「就是」？
- [ ] 有没有把某个势力的行为扩大成整个阵营？
- [ ] 死亡、复活、复制、意识回传等概念，是否严格区分了「数据/形象/本人」？

## 常见错误

| 错误 | 后果 | 修正 |
|---|---|---|
| 手工重打正文 | 丢字、改写、不可维护 | 用脚本解析 |
| `aliases` 放单字名 | 「这里/心里」全被标注 | 移到 `manual_links` |
| 证据引文凭记忆写 | 校验失败 / 事实失真 | 从原文复制精确短句 |
| `spoilerFrom` 用章节 id | 防剧透比较错误 | 用 `order` |
| 两版文件不同名或结构不同 | 切换错位、证据找不到 | `retold/` 与 `sources/` 同名同骨架 |
| 只写 `files` 忘了 `retoldFiles` | 该章没有复述版，切换按钮不出现 | 补 `retoldFiles` 后重新 parse |
| 一次把 90 个实体全写完 | 质量下降、关系混乱 | 先写主线 20–30 个，再补 |
| 星图塞进全部路人 | 毛线球 | 只收主线实体，支持类型筛选 |
| 图片只写远程 URL | 远程热链被拒绝 | 下载到 `assets/img/` 并登记 |
| 图片未指定 section | 校验失败 | 先跑 `place-images --apply` |

## 最小可行示例

只做一章也可以：

1. `sources/01.md` 原文一章；
2. `retold/01.md` 复述版，同名同结构（只做原文复述项目可省略，但那就不是复述项目）；
3. `chapters` 写 `files: ["01.md"]`、`retoldFiles: ["01.md"]`；
4. `entities.json` 8–12 个实体、10–15 条关系；
5. `worldview.json` 4 张卡；
6. `chapter_meta.json` 一条；
7. `recap.json` 一条时间线；
8. `ready: ["ch1"]`；
9. build + verify。

先让一章完整跑通，再复制模式扩展到全书。
