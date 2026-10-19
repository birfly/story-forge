# Story Forge — 功能扩展实施规格（v2）

本文件是 2026-10-19 这轮扩展的内部规格。实现必须保持三条底线：

1. 正文保真：`sources/` / `chapters/` 的正文只由脚本解析，模型不改写。
2. 离线可用：构建产物不得依赖 CDN、外链字体、fetch / module / worker。
3. 向后兼容：现有 `import` / `retelling` / `creation` 项目不修改也能 parse / build / verify。

Python 3.13，仅标准库为必需依赖；`pypdf` 作为 PDF 摄取的可选依赖，缺失时给出明确提示。

---

## 一、原文摄取 `ingest`

新文件：`engine/tools/ingest_sources.py`，测试：`engine/tests/test_ingest.py`。

CLI（由 `scripts/story.py` 转发）：

```bash
python scripts/story.py ingest <project> <source> \
  [--to sources|chapters|DIR] [--dry-run] [--force] \
  [--update-project] [--extract-images] [--json]
```

支持格式：

| 格式 | 实现 |
|---|---|
| `.txt` / `.text` | 编码探测（BOM、utf-8、gb18030、utf-16、big5），章节标题识别，页眉页脚/页码清洗 |
| `.md` | 读取后只规整标题层级与空行，正文不改写 |
| `.epub` | zipfile 读取 container.xml → OPF → spine 顺序；按 nav/NCX 或 XHTML 标题拆章 |
| `.docx` | zipfile 读取 `word/document.xml`；识别 Heading1/2/3（含中文样式名）；无样式时用章节正则 |
| `.html` / `.htm` | html.parser 提取标题与正文，跳过 script/style/nav |
| `.pdf` | 可选 `pypdf`；按页提取后清洗重复页眉页脚；正文过少时报告“无文本层，需要 OCR” |
| 目录 | 按扩展名递归处理（txt/md/epub/docx/html），按文件名排序 |

章节识别：

- 中文：`第X章/回/节/卷/部/篇/集`、`序章`、`楔子`、`序`、`引子`、`番外…`、`尾声`、`终章`、`后记`
- 英文：`Chapter N`、`CHAPTER N`、`Part N`、`Prologue`、`Epilogue`
- 数字标题：单独一行的 `1.` / `01` / `一、`
- 候选行长度 ≤ 60 字符，且不以 `。！？；：，,` 结尾
- 少于 2 个章节标题时：整份文本作为一章，报告 `confidence: "low"`

输出：

- 目标目录默认由 `project.json` 的 kind 决定：import/retelling → `sourceDir`（默认 `sources`），creation → `sourceDir`（默认 `chapters`）；`--to` 覆盖
- 文件名 `01.md`、`02.md`…；`--update-project` 时写入 `project.json` 的 `chapters`（保留已有字段，只补 `id/order/title/files/mode`）
- `build/ingest_report.json`：

```jsonc
{
  "source": "…",
  "format": "txt",
  "sha256": "…",
  "encoding": "utf-8",
  "targetDir": "sources",
  "dryRun": false,
  "chapters": [
    {"index": 1, "title": "第一章 …", "file": "01.md", "hanzi": 1234,
     "paragraphs": 42, "confidence": "high"}
  ],
  "warnings": ["…"],
  "stats": {"inputHanzi": 12345, "outputHanzi": 12340, "droppedRatio": 0.0004}
}
```

规则：

- 默认不覆盖已存在文件；冲突时整体中止并列出冲突文件；`--force` 才覆盖
- `--dry-run` 只输出计划，不写文件
- 正文只做：标题层级归一、段落间空行、页眉页脚/页码移除、行尾空白清理；不得润色、合并、补写
- 若 `outputHanzi / inputHanzi < 0.98`，在 warnings 中说明丢失比例与原因
- EPUB 可选 `--extract-images`：把内嵌图片复制到 `assets/img/epub-<n>.<ext>`，不自动写 illustrations.json，在报告中列出路径

---

## 二、项目状态 `status`

新文件：`engine/tools/project_status.py`，测试：`engine/tests/test_status.py`。

CLI：

```bash
python scripts/story.py status <project> [--json] [--strict]
```

读取：`project.json`、`content/*.json`、源目录文件、`build/parse_report.json`、`build/chapters.json`、`content/illustrations.json`。

输出 `build/status.json`，结构：

```jsonc
{
  "project": {
    "path": "…", "title": "…", "kind": "…",
    "modes": ["original", "retold"],
    "chapterCount": 6, "readyCount": 4, "hanzi": 93520
  },
  "chapters": [
    {
      "id": "ch1", "order": 1, "title": "…", "volume": "vol1",
      "parsed": true, "ready": true, "meta": true,
      "sections": 12, "cast": 5,
      "variants": {
        "original": {"files": ["01.md"], "present": true, "hanzi": 12345,
                     "fidelity": true, "stale": false},
        "retold":   {"files": ["01.md"], "present": true, "hanzi": 11800,
                     "fidelity": true, "stale": true}
      },
      "illustrations": 2
    }
  ],
  "content": {
    "entities": 61, "byType": {"character": 20},
    "relations": 57, "entitiesWithoutEvidence": 3,
    "recapEras": 4, "worldviewCards": 8,
    "timelineEvents": 12
  },
  "illustrations": {"total": 12, "placed": 10, "unplaced": 2,
                    "missingAlt": 0, "missingCredit": 0},
  "build": {"parseReportAt": "…", "errors": [], "warnings": []},
  "nextActions": ["…"]
}
```

- `stale`：源文件 mtime 晚于对应 build 产物（或内容哈希与 build 记录不一致）时为 true；没有 build 数据时为 null
- `nextActions` 由确定性规则生成：缺 parse、fidelity 失败、有 warnings、未分配插图、实体无证据、mode 对齐失败、章节未写 meta、有 unready 章节等
- 人类可读输出：项目摘要 + 章节矩阵 + 内容覆盖 + 下一步
- 退出码：有 parse errors / 核心文件缺失 → 1；`--strict` 时 warnings 也 → 1；否则 0

---

## 三、文风量化

修改：`engine/tools/style_lint.py`，测试：`engine/tests/test_style_audit.py`。

保留现有 banned/soft 正则检查与退出码语义。新增 `--json`、`--strict`、`--no-metrics`。

指标（按模式统计）：

- `hanzi`、`paragraphs`、`sentences`
- `avgSentenceHanzi`、`medianSentenceHanzi`、`p90SentenceHanzi`
- `dialogueParagraphRatio`：段落含 `「」`、`“”`、`『』` 或行首 `——` 的比例
- `avgParagraphHanzi`
- `punctuation`: `，。！？；：…` 各占比
- `person`: `first` / `third` / `mixed`（按 我/我们 vs 他/她/他们 的出现次数）
- `longSentenceRatio`：> 60 汉字的句子占比

基线：主模式（primary）的源文指标。对比：

- 复述章节：`avgSentenceHanzi` 相对基线偏差 > 35% → warning；`dialogueParagraphRatio` 相对偏差 > 50% 且绝对值差 > 0.1 → warning；与原文逐字相同的小节占比 > 0.8 → warning（疑似未复述）
- 元数据（entities 的 tagline/summary/note、chapter_meta 的 hook/takeaways、recap、worldview、timeline summary）：聚合后 `avgSentenceHanzi` 偏差 > 50% → warning；`longSentenceRatio` > 0.3 → warning
- 现有 banned 正则命中 → 保持原有 error/warning 语义

输出 `build/style_report.json`：

```jsonc
{
  "baseline": {"mode": "original", "metrics": {…}},
  "modes": {"original": {…}, "retold": {…}},
  "chapters": [{"chapter": "ch1", "mode": "retold",
                "avgSentenceHanzi": 21.3, "dialogueParagraphRatio": 0.31,
                "drift": {"avgSentenceHanzi": 0.12}}],
  "metadata": {…},
  "errors": [], "warnings": []
}
```

人类可读输出必须包含基线指标、每章漂移、问题列表。`--strict` 时 warnings → 退出码 1。

---

## 四、内容审计 `audit`

新文件：`engine/tools/audit_content.py`，测试：`engine/tests/test_style_audit.py`。

CLI：

```bash
python scripts/story.py audit <project> [--json] [--strict]
```

读取 `build/chapters.json`（不存在时提示先 parse）、`content/*.json`、`project.json`。输出 `build/audit_report.json`：

```jsonc
{
  "errors": [], "warnings": [], "info": [],
  "candidates": [{"name": "…", "count": 12, "chapters": ["ch1","ch2"]}],
  "stats": {"entities": 61, "evidence": 120, "coverage": 0.92}
}
```

检查项：

1. 实体证据
   - 无证据实体 → warning
   - 引文 < 6 个汉字 → warning
   - 同一实体重复引文 → warning
   - 缺 `section` 的引文：按章节内唯一子串定位；唯一 → info（可自动解析）；多处 → error；找不到 → error
   - `section` 存在但引文不匹配 → error
2. 剧透泄漏
   - 实体 summary/tagline 中出现另一个实体（名字或别名），且后者 `firstAppear` 或 `spoilerFrom` 大于当前实体的 `spoilerFrom` → warning
   - 关系 `spoilerFrom` 小于任一端点 `firstAppear` → warning
3. 关系
   - 未知端点 → error
   - 自环 → warning
   - 重复关系（同 from/to/label）→ warning
   - 完全孤立实体（无关系、无证据、无提及）→ warning
4. 章节元数据
   - ready 章节缺 `chapter_meta` → warning
   - 章节缺 cast → warning
   - 章节正文为空 / 0 小节 → error
5. 模式对齐
   - 非主模式与主模式的 section id 序列不一致 → error，列出缺失/多余
   - 章节字数比（非主/主）< 0.5 或 > 1.5 → warning
6. 插图
   - 未分配 section、文件不存在、缺 alt、网页来源缺 credit/license → error
   - 未被任何章节引用、重复 file、文件 > 2 MB → warning
7. 卷册 / 时间线
   - 未知 volume id、章节重复归属 → error
   - 时间线事件 id 重复、引用未知实体/章节、causes/consequences 成环 → error
   - 事件 `spoilerFrom` 大于锚点章节 order → warning
8. 未链接高频名（保守启发式）
   - 对每章正文提取 2–4 字连续汉字串，过滤常见虚词/代词/动词和已知实体名/别名
   - 跨 ≥ 2 章、总频次 ≥ 6、不是任何实体别名的子串 → 放入 `candidates`，只作提示
9. 标注覆盖
   - 统计每章 `data-ent` 数与该章出现的实体名次数；仅 info，不报错

`--strict` 时 warnings → 退出码 1；errors 始终退出码 1。

---

## 五、富结构扩展（parser + site）

修改：`engine/tools/parse_chapters.py`、`engine/site/index.html`、`engine/site/assets/js/*`、`engine/site/assets/css/*`、`engine/content/SCHEMA.md`、`engine/project.template.json`、`scripts/story.py`。

### 5.1 任意变体（variants）

`project.json` 新增：

```jsonc
"variants": [
  {"id": "original", "label": "原文", "dir": "sources", "primary": true},
  {"id": "retold",   "label": "复述", "dir": "retold"},
  {"id": "en",       "label": "English", "dir": "translations/en"}
]
```

- 未提供 `variants` 时按现有 kind / sourceDir / retoldDir / modeLabels 合成，保证旧项目行为不变
- 章节文件：`files` 是主变体；`variantFiles: {"retold": ["01.md"], "en": ["01.en.md"]}`；`retoldFiles` 继续作为 `variantFiles.retold` 的别名
- `modes` 输出为实际可用变体 id 的顺序（主变体在前，其余按 variants 顺序）
- `modeLabels` 输出所有变体标签
- 解析、标注、证据、插图、verify 全部按变体泛化，不再硬编码 `original` / `retold`
- 阅读器切换按钮使用 `modeLabels`；creation 的主变体标签为“创作”
- 兼容：现有 import / retelling / creation 项目测试必须继续通过

### 5.2 卷册

`project.json`：

```jsonc
"volumes": [
  {"id": "vol1", "title": "第一卷 雾港", "subtitle": "", "order": 1,
   "chapters": ["ch1", "ch2"]}
]
```

- 章节可写 `"volume": "vol1"`；也支持 volume 的 `from`/`to`（按 chapter order）推导
- parser 输出 `config.volumes`（含解析后的 chapter ids）与每章的 `volume`
- 阅读器目录按卷分组，可折叠；首页章节条按卷分组；章节封面显示卷名
- 校验：volume id 唯一、章节只能属于一个卷、引用的章节存在

### 5.3 事件线

新内容文件 `content/timeline.json`：

```jsonc
{
  "title": "事件线",
  "kicker": "TIMELINE",
  "lede": "…",
  "events": [
    {
      "id": "ev1",
      "title": "…",
      "summary": "…",
      "chapter": "ch1",
      "storyTime": "第一天 16:00",
      "order": 1,
      "entities": ["shenzhou", "linlan"],
      "causes": ["ev0"],
      "consequences": ["ev2"],
      "spoilerFrom": 1,
      "evidence": [{"chapter": "ch1", "section": "s1", "quote": "…"}]
    }
  ]
}
```

- 输出 `site/data/timeline.js`（`window.STORY_TIMELINE`），并在 `index.html` 引入
- 阅读器新增路由 `#/timeline` 与顶部导航“事件线”
- 页面：按 `order` / 章节 order 排序；显示 storyTime、标题、摘要、实体 chip、原因/后果链接、证据跳转
- 防剧透：只显示 `spoilerFrom <= 当前进度` 的事件；提供进度滑杆（默认最新 ready 章）
- 校验：id 唯一、实体/章节存在、causes/consequences 存在且无环、evidence 与实体证据同样校验
- 无 timeline.json 时页面显示空状态，不影响构建

### 5.4 术语表

- 新增路由 `#/glossary` 与顶部导航“术语表”
- 数据来自 `entities.json` 中 `type: "term"` 的实体，无需新数据文件
- 功能：搜索、按拼音/名称排序、按首次出现章节分组、防剧透、点击打开档案
- 空状态：没有 term 实体时提示

### 5.5 星图连接查询

- 在 atlas 工具栏增加“连接”查询：两个实体选择/输入，BFS 查找可见关系中的最短路径
- 高亮路径节点与边，并显示文字路径；无路径时提示
- 沿用当前章节滑杆与防剧透过滤

### 5.6 实体出现索引

- parser 从解析后的正文生成 `site/data/mentions.js`（`window.STORY_MENTIONS`）：

```jsonc
{
  "shenzhou": [
    {"chapter": "ch1", "section": "s1", "count": 3, "chapterOrder": 1}
  ]
}
```

- 只统计长度 ≥ 2 的名称/别名；单字名不自动统计
- 同一实体同一 section 只保留一条，count 累加
- dossier 中新增“出现位置”，按章节过滤防剧透，点击跳到对应小节
- 不替代证据；证据仍是人工精选

### 5.7 证据 / manual link 自动定位 section

- `entities.json` 的 evidence 允许省略 `section`；parser 在章节内按 quote 唯一定位并写回输出数据
- quote 匹配多处 → 报错并列出候选 section；匹配不到 → 报错
- `manual_links.json` 允许省略 `section`：在目标章节内按 quote 唯一定位；多处或找不到 → 报错
- 现有显式 `section` 保持优先

---

## 六、测试与验收

必须新增并通过：

- `test_ingest.py`：txt（UTF-8/GBK）、epub、docx、html 的最小样例；dry-run；冲突保护；报告字段
- `test_status.py`：在临时项目上 parse 后生成 status；缺失 build 时的降级；`--json`
- `test_style_audit.py`：文风指标数值、漂移告警、审计的各类 error/warning、`--strict`
- `test_rich_structure.py`：variants（含翻译变体）、volumes、timeline、mentions、证据自动定位
- `test_source_check.py`：缺原文、已有原文待登记、用户提供/许可、creation、basedOn、模板、strict
- 现有 `test_modes.py` 4 个测试继续通过
- 在 `examples/mini-story` 上执行 `parse → build --single → verify`，必须 PASS；单文件可打开

所有新增 CLI 必须写入 `scripts/story.py` 的帮助文本与 README。

---

## 七、没有原文时默认搜索（source-check）

新文件：`engine/tools/source_check.py`，测试：`engine/tests/test_source_check.py`。

CLI：

```bash
python scripts/story.py source-check <project> [--json] [--strict] [--write-template]
```

行为：

- 该工具**不联网**，只检查源目录、文件数、字数、`content/source_provenance.json` 与许可状态。
- `import` / `retelling` 的 `sourcePolicy` 默认为 `required`：没有源文件时返回 `next: "search_original"`，并给出 queries（标题、原文、小说 全文、剧情 文本、wiki）。
- `creation` 默认为 `optional`；若 `project.json` 有 `basedOn`，没有章节时返回 `next: "search_reference"`，按原作名给 queries。
- 已有源文件但没有 provenance → `record_provenance`；有 provenance 但许可未知 → `confirm_rights`；`kind: "reference"` 不算主文本。
- `--write-template` 创建 `content/source_provenance.json` 与主源目录下的 `PROVENANCE.md`。
- `status` 读取该报告，把“没有源文本”或“补全 provenance”插入 `nextActions`。
- 真正的搜索由模型用 WebSearch / WebFetch 完成；`skills/story-source/SKILL.md` 与 `/story-source` 定义来源优先级、版权边界和登记方式。三个既有 skill/command 在源文本缺失时会先走这一步。

