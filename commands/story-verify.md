---
description: 校验正文完整性、变体保真、插图、数据一致性、离线性、内容审计与文风
argument-hint: <project-path>
---

在目标项目中执行：

```bash
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" verify <project>
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" audit <project>
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" style <project>
python "$CLAUDE_PLUGIN_ROOT/scripts/story.py" status <project>
```

必须全绿才算完成：

- `fidelity = true`；多变体项目的 `fidelityByMode` 中每章每个可用变体都为 `true`
- 关系端点存在
- 证据 section 存在（或可由 quote 唯一定位）、引文逐字命中
- `data-ent` 全部有实体；所有变体的标注都检查
- 插图：id 唯一、`file` 本地存在、`alt` 存在、`section` 在目标变体存在、网页图片带 `credit` 与 `license`
- 无外链脚本/样式/图片、无 fetch/module/worker
- 时间线事件 id 唯一、引用存在、因果无环；卷册引用有效
- `audit` 无 error；严重 warning 已处理
- `style` 无未处理的严重警告，复述/元数据漂移可解释
- `status` 的 nextActions 只剩构建/发布类事项

再手工检查：

- 复述项目：原文/复述切换出现，切换后停在同一小节
- 原文放入/新建同人：不出现模式切换
- 插图：图注、署名、许可可见；单文件打开后图片仍在
- 事件线：进度滑杆与防剧透生效，证据可回正文
- 术语表：搜索、排序、防剧透、档案跳转可用
- 档案面板：“出现位置”可跳到对应小节
- 星图：“连接”查询能高亮最短路径
- 375 / 768 / 1440 三档宽度无横向溢出

参数：$ARGUMENTS
