---
description: 解析章节、构建富结构阅读站并生成单文件（含模式与插图）
argument-hint: <project-path>
---

在目标项目中执行：

```bash
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" parse <project>
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" build <project> --single
```

如果 `content/illustrations.json` 中有未分配小节的图片，先运行：

```bash
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" place-images <project> --apply
```

然后检查：

- `build/parse_report.json`：`fidelity: true`、`errors: []`
- 双文本项目：`fidelityByMode` 中每章的 `original` 与 `retold` 都为 `true`
- `build/parse_report.json` 的 `warnings`：重点看插图模式/小节缺失
- `build/chapters.json`：单模式章节有顶层 `parts`；双模式章节有 `variants.original` / `variants.retold`
- `site/index.html` 可打开
- `site/assets/` 中包含项目 `assets/` 的图片
- `dist/<slug>.html` 可双击打开；本地图片已内联为 data URI
- 复述项目显示原文/复述切换；原文放入/新建同人不显示切换

参数：$ARGUMENTS
