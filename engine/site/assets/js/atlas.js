/* ============================================================
   Atlas view — filters, chapter progress, graph/list modes
   ============================================================ */

window.STORY = window.STORY || {};

(function () {
  "use strict";

  const { esc, typeLabel } = window.STORY.util;

  let graph = null;
  let chapterOrder = 1;
  let typeFilters = new Set(window.STORY.data.typeOrder);
  let viewMode = "graph";
  let search = "";
  let hoveredNode = null;
  let lastMouse = { x: 0, y: 0 };

  function entityVisible(entity) {
    return window.STORY.store.isVisible(entity, chapterOrder);
  }

  function visibleData() {
    const nodes = window.STORY.data.entities.filter(
      (entity) => typeFilters.has(entity.type) && entityVisible(entity)
    );
    const ids = new Set(nodes.map((node) => node.id));
    const links = window.STORY.data.relations.filter(
      (relation) =>
        ids.has(relation.from) &&
        ids.has(relation.to) &&
        (!window.STORY.store.state.spoiler || Number(relation.spoilerFrom) <= chapterOrder)
    );
    return { nodes, links };
  }

  function renderToolbar() {
    const orders = window.STORY.data.chapters
      .map((chapter) => Number(chapter.order))
      .filter(Number.isFinite);
    const minOrder = orders.length ? Math.min(...orders) : 1;
    const maxOrder = orders.length ? Math.max(...orders) : 1;
    const chips = window.STORY.data.typeOrder
      .map((type) => {
        const color = window.STORY.data.typeColors[type];
        const on = typeFilters.has(type);
        return `<button class="filter-chip ${on ? "on" : "off"}" type="button" data-type="${type}">
            <span class="swatch" style="--chip-color:${color}"></span>${esc(typeLabel(type))}
          </button>`;
      })
      .join("");

    return `
      <div class="atlas-toolbar">
        <div class="atlas-title"><strong>星图</strong><span>RELATION NETWORK</span></div>
        <div class="atlas-search">
          <input id="atlas-search" type="search" placeholder="搜索人物 / 地点 / 术语…" value="${esc(
            search
          )}" aria-label="搜索实体">
        </div>
        <div class="filter-chips" role="group" aria-label="实体类型筛选">${chips}</div>
        <div class="chapter-range">
          <label for="atlas-chapter">读到</label>
          <input id="atlas-chapter" type="range" min="${minOrder}" max="${maxOrder}" step="1" value="${chapterOrder}">
          <output id="atlas-chapter-out">第 ${chapterOrder} 章</output>
        </div>
        <div class="view-toggle" role="group" aria-label="视图">
          <button type="button" data-view="graph" class="${viewMode === "graph" ? "on" : ""}">图谱</button>
          <button type="button" data-view="list" class="${viewMode === "list" ? "on" : ""}">列表</button>
        </div>
        <div class="atlas-path">
          <button id="atlas-path-toggle" class="view-toggle-btn" type="button" aria-expanded="false">连接</button>
          <div id="atlas-path-panel" class="atlas-path-panel" hidden>
            <input id="atlas-path-from" list="atlas-entity-list" placeholder="起点" aria-label="路径起点">
            <input id="atlas-path-to" list="atlas-entity-list" placeholder="终点" aria-label="路径终点">
            <datalist id="atlas-entity-list">
              ${window.STORY.data.entities
                .map(
                  (entity) =>
                    `<option value="${esc(entity.name)}">${esc(entity.id)}</option>`
                )
                .join("")}
            </datalist>
            <button id="atlas-path-run" class="btn ghost" type="button">查找</button>
            <span id="atlas-path-result" class="atlas-path-result" role="status"></span>
          </div>
        </div>
      </div>`;
  }

  function renderLegend() {
    return `
      <div class="atlas-legend" aria-label="图例">
        <span class="legend-item"><span class="legend-line ally"></span>盟友</span>
        <span class="legend-item"><span class="legend-line hostile"></span>敌对</span>
        <span class="legend-item"><span class="legend-line family"></span>亲属</span>
        <span class="legend-item"><span class="legend-line contract"></span>契约 / 未知</span>
      </div>`;
  }

  function render() {
    destroy();
    chapterOrder = window.STORY.store.state.chapterOrder || 1;
    window.STORY.store.state.route = "atlas";

    const view = document.getElementById("view");
    view.innerHTML = `
      <div class="atlas-view">
        ${renderToolbar()}
        <div class="atlas-stage ${viewMode === "list" ? "off" : ""}" id="atlas-stage">
          <svg class="atlas-svg" id="atlas-svg" role="img" aria-label="人物、势力、地点、术语与事件的关系网络"></svg>
          <div class="zoom-controls">
            <button type="button" data-zoom="in" aria-label="放大">+</button>
            <button type="button" data-zoom="out" aria-label="缩小">−</button>
            <button type="button" data-zoom="reset" aria-label="重置视图">⌂</button>
          </div>
          ${renderLegend()}
          <div class="atlas-hint">拖拽节点 · 滚轮缩放<br>点击节点打开档案</div>
        </div>
        <div class="atlas-list ${viewMode === "list" ? "on" : ""}" id="atlas-list"></div>
      </div>`;

    bindToolbar();

    const svg = document.getElementById("atlas-svg");
    if (svg) {
      graph = new window.STORY.ForceGraph(svg, {
        onSelect: (node) => window.STORY.dossier.open(node.id),
        onHover: (node) => {
          hoveredNode = node;
          if (!node) hideTooltip();
          else showTooltip(node);
        },
      });
      svg.addEventListener("pointermove", (event) => {
        lastMouse = { x: event.clientX, y: event.clientY };
        if (hoveredNode) showTooltip(hoveredNode);
      });
      applyFilters();
    }

    renderList();
    bindZoom();
    focusFromHash();
  }

  function resolveEntity(value) {
    const text = String(value || "").trim().toLowerCase();
    if (!text) return null;
    const nodes = visibleData().nodes;
    return (
      nodes.find((node) => String(node.id).toLowerCase() === text) ||
      nodes.find((node) => String(node.name).toLowerCase() === text) ||
      nodes.find((node) =>
        (node.aliases || []).some(
          (alias) => String(alias).toLowerCase() === text
        )
      ) ||
      nodes.find((node) =>
        `${node.name} ${node.id}`.toLowerCase().includes(text)
      ) ||
      null
    );
  }

  function findPath(fromId, toId, links) {
    const adjacency = new Map();
    for (const link of links) {
      if (!adjacency.has(link.from)) adjacency.set(link.from, []);
      if (!adjacency.has(link.to)) adjacency.set(link.to, []);
      adjacency.get(link.from).push(link.to);
      adjacency.get(link.to).push(link.from);
    }
    const queue = [fromId];
    const previous = new Map([[fromId, null]]);
    while (queue.length) {
      const current = queue.shift();
      if (current === toId) break;
      for (const next of adjacency.get(current) || []) {
        if (previous.has(next)) continue;
        previous.set(next, current);
        queue.push(next);
      }
    }
    if (!previous.has(toId)) return null;
    const path = [];
    let node = toId;
    while (node) {
      path.unshift(node);
      node = previous.get(node);
    }
    return path;
  }

  function runPathQuery() {
    const fromInput = document.getElementById("atlas-path-from");
    const toInput = document.getElementById("atlas-path-to");
    const result = document.getElementById("atlas-path-result");
    if (!fromInput || !toInput || !result) return;
    const from = resolveEntity(fromInput.value);
    const to = resolveEntity(toInput.value);
    if (!from || !to) {
      result.textContent = "请选择两个当前可见的实体";
      if (graph) graph.highlightPath([]);
      return;
    }
    if (from.id === to.id) {
      result.textContent = "起点和终点相同";
      return;
    }
    const path = findPath(from.id, to.id, visibleData().links);
    if (!path) {
      result.textContent = "当前进度下没有连接路径";
      if (graph) graph.highlightPath([]);
      return;
    }
    const names = path.map((id) => {
      const entity = window.STORY.data.entityById.get(id);
      return entity ? entity.name : id;
    });
    result.textContent = names.join(" → ");
    if (graph) graph.highlightPath(path);
  }

  function bindToolbar() {
    const searchInput = document.getElementById("atlas-search");
    if (searchInput) {
      searchInput.addEventListener("input", () => {
        search = searchInput.value;
        if (graph) graph.highlight(search);
        renderList();
      });
      searchInput.addEventListener("keydown", (event) => {
        if (event.key !== "Enter") return;
        const query = search.trim().toLowerCase();
        if (!query) return;
        const match = visibleData().nodes.find((node) =>
          `${node.name} ${node.tagline}`.toLowerCase().includes(query)
        );
        if (match && graph) graph.focusNode(match.id);
      });
    }

    document.querySelectorAll(".filter-chip[data-type]").forEach((button) => {
      button.addEventListener("click", () => {
        const type = button.dataset.type;
        if (typeFilters.has(type)) typeFilters.delete(type);
        else typeFilters.add(type);
        button.classList.toggle("on", typeFilters.has(type));
        button.classList.toggle("off", !typeFilters.has(type));
        applyFilters();
        renderList();
      });
    });

    const range = document.getElementById("atlas-chapter");
    const output = document.getElementById("atlas-chapter-out");
    if (range) {
      range.addEventListener("input", () => {
        if (output) output.textContent = `第 ${range.value} 章`;
      });
      range.addEventListener("change", () => {
        chapterOrder = Number(range.value);
        window.STORY.store.state.chapterOrder = chapterOrder;
        const chapter = window.STORY.data.chapterByOrder.get(chapterOrder);
        if (chapter) window.STORY.store.state.chapterId = String(chapter.id);
        applyFilters();
        renderList();
      });
    }

    document.querySelectorAll(".view-toggle [data-view]").forEach((button) => {
      button.addEventListener("click", () => {
        viewMode = button.dataset.view;
        document
          .querySelectorAll(".view-toggle [data-view]")
          .forEach((item) => item.classList.toggle("on", item.dataset.view === viewMode));
        document.getElementById("atlas-stage").classList.toggle("off", viewMode === "list");
        document.getElementById("atlas-list").classList.toggle("on", viewMode === "list");
        renderList();
      });
    });

    const pathToggle = document.getElementById("atlas-path-toggle");
    const pathPanel = document.getElementById("atlas-path-panel");
    if (pathToggle && pathPanel) {
      pathToggle.addEventListener("click", () => {
        pathPanel.hidden = !pathPanel.hidden;
        pathToggle.setAttribute(
          "aria-expanded",
          pathPanel.hidden ? "false" : "true"
        );
      });
    }
    const pathRun = document.getElementById("atlas-path-run");
    if (pathRun) pathRun.addEventListener("click", runPathQuery);
    ["atlas-path-from", "atlas-path-to"].forEach((id) => {
      const input = document.getElementById(id);
      if (input) {
        input.addEventListener("keydown", (event) => {
          if (event.key === "Enter") runPathQuery();
        });
      }
    });
  }

  function bindZoom() {
    document.querySelectorAll("[data-zoom]").forEach((button) => {
      button.addEventListener("click", () => {
        if (!graph) return;
        if (button.dataset.zoom === "in") graph.zoom(1.2);
        if (button.dataset.zoom === "out") graph.zoom(1 / 1.2);
        if (button.dataset.zoom === "reset") graph.resetView();
      });
    });
  }

  function applyFilters() {
    if (!graph) return;
    const { nodes, links } = visibleData();
    graph.setData(nodes, links);
    if (!nodes.length) {
      window.STORY.store.toast("当前筛选下没有节点");
    } else if (search) {
      graph.highlight(search);
    }
  }

  function renderList() {
    const list = document.getElementById("atlas-list");
    if (!list) return;
    const query = search.trim().toLowerCase();
    const nodes = visibleData().nodes.filter((entity) => {
      if (!query) return true;
      return `${entity.name} ${entity.tagline || ""}`.toLowerCase().includes(query);
    });

    if (!nodes.length) {
      list.innerHTML = `<div class="atlas-empty">当前筛选下没有节点。</div>`;
      return;
    }

    list.innerHTML = window.STORY.data.typeOrder
      .map((type) => {
        const items = nodes.filter((node) => node.type === type);
        if (!items.length) return "";
        return `
          <section class="list-group">
            <h2>${esc(typeLabel(type))} · ${items.length}</h2>
            ${items
              .map(
                (entity) => `
                  <button class="list-entity" type="button" data-ent="${esc(entity.id)}">
                    <span class="icon" style="--entity-color:${esc(
                      entity.color || "var(--accent)"
                    )}">${esc(entity.icon || entity.name.slice(0, 1))}</span>
                    <span>
                      <span class="name">${esc(entity.name)}</span>
                      <span class="tagline">${esc(entity.tagline || "")}</span>
                    </span>
                    <span class="rel-count">${window.STORY.store.entityRelationsCount(
                      entity.id
                    )} 关系</span>
                  </button>`
              )
              .join("")}
          </section>`;
      })
      .join("");

    list.querySelectorAll("[data-ent]").forEach((button) => {
      button.addEventListener("click", () => window.STORY.dossier.open(button.dataset.ent));
    });
  }

  function showTooltip(node) {
    const tooltip = document.getElementById("tooltip");
    if (!tooltip) return;
    const visible = window.STORY.store.isVisible(node, chapterOrder);
    tooltip.innerHTML = visible
      ? `<span class="tt-name">${esc(node.name)} · ${esc(typeLabel(node.type))}</span>
         <span class="tt-tag">${esc(node.tagline || "")}</span>`
      : `<span class="tt-name">？？？</span><span class="tt-tag">防剧透已开启</span>`;
    tooltip.hidden = false;
    const x = Math.min(window.innerWidth - 150, Math.max(150, lastMouse.x));
    const y = Math.max(80, lastMouse.y - 14);
    tooltip.style.left = `${x}px`;
    tooltip.style.top = `${y}px`;
  }

  function hideTooltip() {
    const tooltip = document.getElementById("tooltip");
    if (tooltip) tooltip.hidden = true;
  }

  function focusFromHash() {
    const query = window.location.hash.split("?")[1] || "";
    const focus = new URLSearchParams(query).get("focus");
    if (!focus || !graph) return;
    window.setTimeout(() => graph.focusNode(focus), 320);
  }

  function destroy() {
    if (graph) {
      graph.destroy();
      graph = null;
    }
    hoveredNode = null;
    hideTooltip();
  }

  window.STORY.atlas = { render, destroy };
})();
