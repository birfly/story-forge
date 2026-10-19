---
name: story-creation
description: "Create a new fanfic or story (新建同人) with a rich-structured reader: story bible, characters, factions, locations, terms, events, relationship graph, chapter drafts, recap, illustrations, and a visual-novel-grade reading site. Trigger when the user says 新建同人, 同人创作, 小说创建, 写小说, 故事工坊, 世界观设定, 人物关系网, 章节写作, 做一个互动阅读站, or asks to build a new story from a premise."
---

# 新建同人（Creation）

从一句设定开始，建一个**可读、可查、可扩展**的新同人故事：先有故事圣经（人物/势力/地点/术语/事件/关系），再写章节，最后生成与复述项目相同的富结构阅读站。

项目类型是 `creation`，模式为 `["retold"]`，界面把这个唯一模式标为“创作”。**没有原文模式**，也没有原文/复述切换：`chapters/` 就是正文本身。不要创建 `sources/`、`retold/` 或 `retoldFiles`。

## 产出物

```
<project>/
├── project.json
├── chapters/                # 章节 Markdown（H1/H2/H3）
├── assets/img/              # 本地插图
├── content/
│   ├── style_profile.md     # 文风约定（先写这个）
│   ├── entities.json        # 人物/势力/地点/术语/事件 + 关系
│   ├── chapter_meta.json    # 每章计划：POV/钩子/登场/带走的事
│   ├── recap.json           # 故事前史 + 当前局势（也是大纲）
│   ├── worldview.json       # 世界规则概念卡
│   ├── manual_links.json    # 单字名/歧义名人工锚句
│   └── illustrations.json   # 场景插图登记与授权信息
├── site/                    # 阅读站
├── dist/<slug>.html         # 单文件
└── build/parse_report.json
```

## 核心原则

1. **故事圣经先于正文**：人物、关系、世界规则没定清楚，不要开写第一章。
2. **每章都要推进关系网**：一章至少改变一条关系，或揭示一个实体。
3. **文风先定后写**：先写 `style_profile.md`，再写正文；正文和元数据都用同一种文风。
4. **证据与防剧透**：实体 `summary` 只写 `spoilerFrom` 之前的内容；关系带 `spoilerFrom`。
5. **可扩展**：先做 3 章最小闭环，再扩卷；不要一次性写 30 章设定。
6. **插图本地化**：场景插图只从 `assets/img/` 提供；网页来源只接受开放许可，并保留 credit 与 license。

## 语言风格

### 如果用户给了样文

先按复述技能的「语言风格：必须仿照原文」提取样本：人称、时态、句长、词汇、对话比例、标题习惯、明确避免的东西。之后所有正文、章节钩子、人物档案、前情提要都按这份样文写。

### 如果用户没给样文

在 `content/style_profile.md` 里先定一份**具体**的文风约定，不能写“文笔优美”“有张力”这种空话。至少写清：

```markdown
# 文风约定

## 叙述人称
（第一人称/第三人称限知/全知；是否称呼“你”）

## 时态与距离
（过去时/现在时；叙述者是冷静旁观还是贴近角色）

## 句子
（以短句为主/中长句；平均字数；是否使用破折号、分号、排比）

## 词汇
（口语/书面/技术；是否使用方言、古语、行业词；是否解释术语）

## 对话
（对话占比；是否用引号；是否带“他说”；角色是否有固定口头习惯）

## 描写
（具体动作/感官细节/心理独白；比喻密度；是否使用抽象名词）

## 章节标题
（陈述句/疑问句/名词短语；是否加副标题）

## 明确不写
（例如：不写金句、不写总结性升华、不替角色下结论、不写“不是 A 而是 B”）
```

### 禁止清单

除非用户的样文本身就这样写，否则不要使用：

- 对称金句：“不是 A，而是 B”“与其说 A，不如说 B”“真正的 X 是 Y”
- 升华句：“这意味着”“这正是……的地方”“……才真正开始”
- 抽象名词堆砌：“宿命”“救赎”“困境”“成长的完成”
- 替角色下结论：“她终于明白”“他终于学会”
- 空泛评价：“令人动容”“意味深长”“充满张力”
- 每章结尾都用一句“点题”

### 自检

随机抽 5 句正文或元数据，对照 `style_profile.md`：

- 人称、时态、句长是否一致？
- 有没有出现约定里“明确不写”的东西？
- 这句话像不像这个故事里的人会说的话？
- 有没有比设定多解释一步？

## 工作流

> 命令中的 `$CLAUDE_PLUGIN_ROOT` 指插件根目录。如果环境没有这个变量，替换成 `~/.claude/skills/story-forge`。

### 0. 前提访谈

一次问一个，能从上下文推断就跳过：

1. 题材与基调（科幻/奇幻/悬疑/现实主义；冷/暖/荒诞/克制）
2. 篇幅（短篇 3–5 章 / 中篇 8–15 章 / 长篇分卷）
3. 叙述人称（第一/第三限知/全知）
4. 目标读者（零基础/类型读者/青少年/成人）
5. 核心问题（这个故事反复追问的一件事）
6. 结局感受（不是情节，是读者读完后的情绪）
7. 有没有样文或明确想模仿的作家/作品

### 0.5 原作资料（仅同人，默认搜索）

如果这是基于已有作品的同人：

1. 在 `project.json` 写 `"basedOn": "原作名"`。
2. 运行 `python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" source-check <project> --json`。
3. `next` 为 `search_reference` 时，按 `searchPlan.queries` 搜索原作设定、人物、时间线；只登记为 `kind: "reference"`，不要复制受版权保护的正文。
4. **搜索后用 `source-check --record-search` 记录**；在记录之前不要直接停下来要资料。
5. 原创故事跳过这一步。

完整规则见 `skills/story-source/SKILL.md`。

### 1. 创建项目

```bash
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" new <project> --template creation \
  --title "故事标题" --subtitle "一句话定位" --slug "story-slug"
```

模板会生成 `kind: "creation"`、`modes: ["retold"]`、`defaultMode: "retold"`、`sourceDir: "chapters"`，界面标签为“创作”。不要改成双模式。

### 2. 写 style_profile.md

在写任何正文之前完成。后面每一章、每一条档案都以它为准。

### 3. 建故事圣经

#### 3.1 worldview.json

6–12 张概念卡：世界规则、技术、势力、地理、历史。每张卡：

- 一句话定义；
- 3–5 句解释；
- 关联实体 id。

#### 3.2 entities.json

先建主线实体（20–30 个），再补：

- 人物：主角、对手、盟友、镜像角色、只闻其名者。
- 势力：至少两个目标冲突的组织。
- 地点：故事主要发生的 3–6 个空间。
- 术语：读者必须懂的 5–10 个概念。
- 事件：改变关系的关键节点。

每个实体写：

- `tagline`：一句话；
- `summary`：80–150 字，只写 `spoilerFrom` 之前；
- `aliases`：长度 ≥ 2 的别名；
- `spoilerFrom` / `firstAppear`：章节 order；
- `evidence`：正文写出来后再补，引用必须是写好的正文短句。

关系先连主线：

```jsonc
{ "from": "a", "to": "b", "label": "关系", "kind": "ally", "spoilerFrom": 1 }
```

#### 3.3 recap.json

创作项目的 recap 同时是**故事前史 + 当前局势 + 大纲**：

- `eras`：故事开始前的 3–6 个时代/事件；
- `whereYouAre`：第一章入口时，每个主要人物在哪里、想要什么、被什么挡住。

#### 3.4 chapter_meta.json

先写章节计划，再写正文。每章：

- `codename`
- `hook`（1–2 句，按文风约定写）
- `cast`（本章登场实体）
- `takeaways`（3–5 条，写“发生了什么”，不写升华）
- `newTerms`

章节计划至少回答：POV 是谁、目标是什么、阻碍是什么、转折是什么、结尾钩子是什么。

### 4. 写章节

放进 `chapters/`，结构：

```markdown
# 第一章 标题：副标题

## 第一幕 · 幕名

### 场景标题

正文……
```

写作规则：

- 每章只引入 1–3 个新命名实体。
- 每章至少改变一条关系，或揭示一个实体。
- 伏笔写进事件节点，不要只放在作者脑子里。
- 每章结尾留一个具体的下一步，不写空泛悬念。
- 章节内的称呼、术语、地名，和 `entities.json` 完全一致。

### 5. 场景插图（可选）

插图登记在 `content/illustrations.json`，本地文件放在 `assets/img/`。字段与校验规则见 `engine/content/SCHEMA.md` 第 9 节。

```bash
# A. 本地图片：放进 assets/img/，手工登记 id、file、alt、chapter

# B. 抓取开放许可图片（Wikimedia Commons / Openverse）
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" fetch-images <project> \
  --query "scene keyword" --chapter ch1 --limit 2

# 分配小节：先 dry-run，再 --apply
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" place-images <project>
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" place-images <project> --apply
```

- 创作项目只有 `retold` 一种模式，图片的 `mode` 保持 `both` 即可；解析器会把它映射到唯一模式。
- `place-images` 按 `keywords` 与小节正文的重叠度选位置；没有关键词时在章内均匀分布。每章默认最多 4 张。
- 网页来源图片必须带 `credit`、`license`、`sourceUrl`；本地图片也必须写 `alt`。
- 受版权保护的官方美术/同人图：只能由用户提供本地文件并自行确认权利；抓取工具只取开放许可图片或 `--local-dir` 中的用户文件。
- 图片不写进 Markdown 正文；解析器按 manifest 注入 image block。

### 6. 解析与构建

```bash
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" parse <project>
```

先检查：

- 每章 fidelity = true；
- `build/chapters.json` 里的 section id；
- 正文里哪些实体第一次出现。

然后补 evidence、更新 `ready`，再：

```bash
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" build <project> --single
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" verify <project>
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" audit <project>
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" style <project>
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" status <project>
```

`status` 的 nextActions 只剩发布类事项，`audit` 无 error，`style` 无未处理的严重警告，才算完成。事件线与术语表有内容时，也按阅读器手工检查。

### 7. 迭代

- 新章：先写 `chapter_meta`，再写正文，再补 evidence。
- 关系变化：改 `relations` 的 `label` / `kind` / `spoilerFrom`。
- 新增重要实体：先加档案，再回正文标注。
- 每卷结束：更新 `recap.eras` 与 `whereYouAre`。

## 最小可行故事

先跑通一个 3 章闭环：

- 5 个实体：主角、对手、盟友、1 个势力、1 个地点；
- 1 个术语（世界的核心规则）；
- 3 条关系；
- 3 章 × 800–1500 字；
- `ready: ["ch1","ch2","ch3"]`；
- build + verify + style lint。

跑通后再扩人物、扩地图、扩势力。

## 质量清单

- [ ] `style_profile.md` 已写，且是具体的（不是“文笔优美”）
- [ ] `project.json` 为 `kind: "creation"`、`modes: ["retold"]`，界面显示“创作”且没有原文/复述切换
- [ ] 每个主要人物有欲望、阻碍、选择
- [ ] 每条关系至少变化一次
- [ ] 每章引入的新实体 ≤ 3
- [ ] 每章结尾有具体下一步
- [ ] `summary` 没有超过 `spoilerFrom` 的信息
- [ ] 证据引文逐字来自正文
- [ ] 正文与档案的称呼、术语、地名一致
- [ ] 插图 id 唯一、文件存在、`alt` 存在、section 存在、网页图片带 credit/license
- [ ] style lint 无未处理警告
- [ ] 375 / 768 / 1440 三档阅读正常

## 常见错误

| 错误 | 后果 | 修正 |
|---|---|---|
| 先写 10 章再建设定 | 前后矛盾、关系网断裂 | 先故事圣经，再正文 |
| 文风约定写空话 | 每章像不同人写的 | 写清人称/句长/词汇/对话/禁止项 |
| 每章加 10 个新名字 | 读者记不住 | 每章 ≤ 3 个新实体 |
| 关系只建不改 | 星图是静态图 | 每章至少改一条关系 |
| 档案写成作者解读 | 和正文打架 | 只写正文能支撑的内容 |
| 结局先写死 | 中段没有张力 | 先定结局感受，不定具体台词 |
| 创建 `sources/` 或 `retold/` | 项目结构混乱 | 创作正文只放 `chapters/` |
| 图片只写远程 URL | 远程热链被拒绝 | 下载到 `assets/img/` 并登记 |
| 图片未指定 section | 校验失败 | 先跑 `place-images --apply` |
