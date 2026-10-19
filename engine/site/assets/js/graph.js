/* ============================================================
   Force-directed atlas graph — dependency-free SVG simulation
   ============================================================ */

window.STORY = window.STORY || {};

(function () {
  "use strict";

  const NS = "http://www.w3.org/2000/svg";

  const TYPE_RADIUS = {
    character: 19,
    faction: 15,
    location: 13,
    term: 11,
    event: 10,
  };

  const TYPE_CLUSTER = {
    character: { radius: 0.22, offset: 0 },
    faction: { radius: 0.36, offset: 0.6 },
    location: { radius: 0.44, offset: 2.1 },
    term: { radius: 0.34, offset: 3.4 },
    event: { radius: 0.42, offset: 4.7 },
  };

  function clamp(value, min, max) {
    return Math.max(min, Math.min(max, value));
  }

  function nodeShape(type, radius) {
    if (type === "faction") {
      return { tag: "rect", attrs: { x: -radius, y: -radius, width: radius * 2, height: radius * 2, rx: 4 } };
    }
    if (type === "location") {
      return { tag: "path", attrs: { d: `M0,${-radius} L${radius},0 L0,${radius} L${-radius},0 Z` } };
    }
    if (type === "term") {
      const points = [];
      for (let i = 0; i < 6; i += 1) {
        const angle = (Math.PI / 3) * i - Math.PI / 6;
        points.push(`${(Math.cos(angle) * radius).toFixed(2)},${(Math.sin(angle) * radius).toFixed(2)}`);
      }
      return { tag: "path", attrs: { d: `M${points.join(" L")} Z` } };
    }
    return { tag: "circle", attrs: { r: radius } };
  }

  class ForceGraph {
    constructor(svg, options) {
      this.svg = svg;
      this.options = options || {};
      this.onSelect = this.options.onSelect || (() => {});
      this.onHover = this.options.onHover || (() => {});
      this.nodes = [];
      this.links = [];
      this.nodeById = new Map();
      this.adjacency = new Map();
      this.positions = new Map();
      this.view = { x: 0, y: 0, k: 1 };
      this.dragging = null;
      this.panning = null;
      this.hovered = null;
      this.width = 0;
      this.height = 0;

      this.viewport = document.createElementNS(NS, "g");
      this.viewport.setAttribute("class", "viewport");
      this.linkLayer = document.createElementNS(NS, "g");
      this.linkLayer.setAttribute("class", "links");
      this.nodeLayer = document.createElementNS(NS, "g");
      this.nodeLayer.setAttribute("class", "nodes");
      this.viewport.appendChild(this.linkLayer);
      this.viewport.appendChild(this.nodeLayer);
      svg.appendChild(this.viewport);

      this.bindEvents();
      this.resizeHandler = () => this.resize();
      window.addEventListener("resize", this.resizeHandler);
      this.resize();
    }

    bindEvents() {
      this.svg.addEventListener("pointerdown", (event) => this.onPointerDown(event));
      this.svg.addEventListener("pointermove", (event) => this.onPointerMove(event));
      this.svg.addEventListener("pointerup", (event) => this.onPointerUp(event));
      this.svg.addEventListener("pointercancel", () => this.endInteraction());
      this.svg.addEventListener("wheel", (event) => this.onWheel(event), { passive: false });
    }

    resize() {
      const rect = this.svg.getBoundingClientRect();
      this.width = Math.max(320, rect.width || 800);
      this.height = Math.max(320, rect.height || 600);
      this.svg.setAttribute("viewBox", `0 0 ${this.width} ${this.height}`);
      this.center();
      this.render();
    }

    center() {
      this.view.x = this.width / 2;
      this.view.y = this.height / 2;
      this.applyView();
    }

    applyView() {
      this.viewport.setAttribute(
        "transform",
        `translate(${this.view.x},${this.view.y}) scale(${this.view.k})`
      );
      this.svg.classList.toggle("zoom-out", this.view.k < 0.72);
    }

    toWorld(clientX, clientY) {
      const rect = this.svg.getBoundingClientRect();
      return {
        x: (clientX - rect.left - this.view.x) / this.view.k,
        y: (clientY - rect.top - this.view.y) / this.view.k,
      };
    }

    setData(nodes, links) {
      const previous = new Map(this.nodes.map((node) => [node.id, { x: node.x, y: node.y }]));
      this.nodes = nodes.map((node) => {
        const old = previous.get(node.id) || this.positions.get(node.id);
        const cluster = TYPE_CLUSTER[node.type] || TYPE_CLUSTER.term;
        const index = nodes.indexOf(node);
        const angle = cluster.offset + index * 0.62;
        const spread = Math.min(this.width, this.height) * cluster.radius;
        return {
          ...node,
          x: old ? old.x : Math.cos(angle) * spread + (Math.random() - 0.5) * 40,
          y: old ? old.y : Math.sin(angle) * spread + (Math.random() - 0.5) * 40,
          vx: 0,
          vy: 0,
          fx: null,
          fy: null,
          radius: TYPE_RADIUS[node.type] || 11,
        };
      });
      this.nodeById = new Map(this.nodes.map((node) => [node.id, node]));
      this.links = links
        .filter((link) => this.nodeById.has(link.from) && this.nodeById.has(link.to))
        .map((link) => ({ ...link }));
      this.buildAdjacency();
      this.buildSvg();
      this.simulate(180);
      this.render();
    }

    buildAdjacency() {
      this.adjacency = new Map();
      for (const node of this.nodes) this.adjacency.set(node.id, new Set());
      for (const link of this.links) {
        this.adjacency.get(link.from).add(link.to);
        this.adjacency.get(link.to).add(link.from);
      }
    }

    buildSvg() {
      this.linkLayer.textContent = "";
      this.nodeLayer.textContent = "";

      this.linkElements = new Map();
      for (const link of this.links) {
        const line = document.createElementNS(NS, "line");
        line.setAttribute("class", `edge kind-${link.kind || "unknown"}`);
        line.dataset.from = link.from;
        line.dataset.to = link.to;
        line.dataset.label = link.label || "";
        this.linkLayer.appendChild(line);
        this.linkElements.set(`${link.from}::${link.to}::${link.label}`, line);
      }

      this.nodeElements = new Map();
      for (const node of this.nodes) {
        const group = document.createElementNS(NS, "g");
        group.setAttribute("class", "node");
        group.dataset.id = node.id;
        group.setAttribute("tabindex", "0");
        group.setAttribute("role", "button");
        group.setAttribute(
          "aria-label",
          `${node.name}，${window.STORY.util.typeLabel(node.type)}`
        );
        group.style.setProperty("--node-color", node.color || "var(--line-strong)");

        const shape = nodeShape(node.type, node.radius);
        const shapeElement = document.createElementNS(NS, shape.tag);
        shapeElement.setAttribute("class", "node-shape");
        for (const [key, value] of Object.entries(shape.attrs)) {
          shapeElement.setAttribute(key, value);
        }
        group.appendChild(shapeElement);

        const icon = document.createElementNS(NS, "text");
        icon.setAttribute("class", "node-icon");
        icon.textContent = node.icon || node.name.slice(0, 1);
        group.appendChild(icon);

        const label = document.createElementNS(NS, "text");
        label.setAttribute("class", "node-label");
        label.setAttribute("y", node.radius + 13);
        label.textContent = node.name;
        group.appendChild(label);

        group.addEventListener("pointerdown", (event) => {
          event.stopPropagation();
          this.startNodeDrag(node, event);
        });
        group.addEventListener("pointerenter", () => this.hoverNode(node));
        group.addEventListener("pointerleave", () => this.clearHover());
        group.addEventListener("click", (event) => {
          event.stopPropagation();
          if (!this.dragMoved) this.onSelect(node);
        });
        group.addEventListener("keydown", (event) => {
          if (event.key === "Enter" || event.key === " ") {
            event.preventDefault();
            this.onSelect(node);
          }
        });

        this.nodeLayer.appendChild(group);
        this.nodeElements.set(node.id, group);
      }
    }

    simulate(iterations) {
      const nodes = this.nodes;
      const links = this.links;
      if (!nodes.length) return;
      const repulsion = 5200;
      const springLength = 118;
      const springStrength = 0.014;
      const centerStrength = 0.0016;

      for (let tick = 0; tick < iterations; tick += 1) {
        for (const node of nodes) {
          if (node.fx !== null && node.fx !== undefined) {
            node.x = node.fx;
            node.y = node.fy;
            node.vx = 0;
            node.vy = 0;
            continue;
          }
          node.vx *= 0.86;
          node.vy *= 0.86;
        }

        for (let i = 0; i < nodes.length; i += 1) {
          for (let j = i + 1; j < nodes.length; j += 1) {
            const a = nodes[i];
            const b = nodes[j];
            let dx = a.x - b.x;
            let dy = a.y - b.y;
            let dist2 = dx * dx + dy * dy;
            if (dist2 < 1) {
              dx = (Math.random() - 0.5) * 2;
              dy = (Math.random() - 0.5) * 2;
              dist2 = 1;
            }
            const dist = Math.sqrt(dist2);
            const force = repulsion / dist2;
            const fx = (dx / dist) * force;
            const fy = (dy / dist) * force;
            a.vx += fx;
            a.vy += fy;
            b.vx -= fx;
            b.vy -= fy;
          }
        }

        for (const link of links) {
          const a = this.nodeById.get(link.from);
          const b = this.nodeById.get(link.to);
          if (!a || !b) continue;
          const dx = b.x - a.x;
          const dy = b.y - a.y;
          const dist = Math.sqrt(dx * dx + dy * dy) || 1;
          const force = (dist - springLength) * springStrength;
          const fx = (dx / dist) * force;
          const fy = (dy / dist) * force;
          a.vx += fx;
          a.vy += fy;
          b.vx -= fx;
          b.vy -= fy;
        }

        for (const node of nodes) {
          if (node.fx !== null && node.fx !== undefined) {
            node.x = node.fx;
            node.y = node.fy;
            continue;
          }
          node.vx -= node.x * centerStrength;
          node.vy -= node.y * centerStrength;
          const speed = Math.sqrt(node.vx * node.vx + node.vy * node.vy);
          const limit = 9;
          if (speed > limit) {
            node.vx = (node.vx / speed) * limit;
            node.vy = (node.vy / speed) * limit;
          }
          node.x += node.vx;
          node.y += node.vy;
          const bound = Math.max(this.width, this.height) * 0.72;
          node.x = clamp(node.x, -bound, bound);
          node.y = clamp(node.y, -bound, bound);
        }
      }

      for (const node of nodes) {
        this.positions.set(node.id, { x: node.x, y: node.y });
      }
    }

    render() {
      if (!this.nodeElements) return;
      for (const node of this.nodes) {
        const element = this.nodeElements.get(node.id);
        if (!element) continue;
        element.setAttribute("transform", `translate(${node.x.toFixed(2)},${node.y.toFixed(2)})`);
      }
      for (const link of this.links) {
        const line = this.linkElements.get(`${link.from}::${link.to}::${link.label}`);
        const a = this.nodeById.get(link.from);
        const b = this.nodeById.get(link.to);
        if (!line || !a || !b) continue;
        line.setAttribute("x1", a.x.toFixed(2));
        line.setAttribute("y1", a.y.toFixed(2));
        line.setAttribute("x2", b.x.toFixed(2));
        line.setAttribute("y2", b.y.toFixed(2));
      }
    }

    onPointerDown(event) {
      if (event.button !== 0) return;
      this.panning = {
        startX: event.clientX,
        startY: event.clientY,
        originX: this.view.x,
        originY: this.view.y,
      };
      this.svg.classList.add("dragging");
      this.svg.setPointerCapture(event.pointerId);
    }

    startNodeDrag(node, event) {
      this.dragging = node;
      this.dragStart = { x: event.clientX, y: event.clientY };
      this.dragMoved = false;
      this.svg.setPointerCapture(event.pointerId);
      node.fx = node.x;
      node.fy = node.y;
    }

    onPointerMove(event) {
      if (this.dragging) {
        const world = this.toWorld(event.clientX, event.clientY);
        const dx = event.clientX - this.dragStart.x;
        const dy = event.clientY - this.dragStart.y;
        if (Math.abs(dx) + Math.abs(dy) > 3) this.dragMoved = true;
        this.dragging.x = world.x;
        this.dragging.y = world.y;
        this.dragging.fx = world.x;
        this.dragging.fy = world.y;
        this.dragging.vx = 0;
        this.dragging.vy = 0;
        this.simulate(8);
        this.render();
        return;
      }
      if (this.panning) {
        const dx = event.clientX - this.panning.startX;
        const dy = event.clientY - this.panning.startY;
        this.view.x = this.panning.originX + dx;
        this.view.y = this.panning.originY + dy;
        this.applyView();
      }
    }

    onPointerUp() {
      this.endInteraction();
    }

    endInteraction() {
      if (this.dragging) {
        this.dragging.fx = null;
        this.dragging.fy = null;
        this.simulate(20);
        this.render();
      }
      this.dragging = null;
      this.panning = null;
      this.svg.classList.remove("dragging");
    }

    onWheel(event) {
      event.preventDefault();
      const rect = this.svg.getBoundingClientRect();
      const px = event.clientX - rect.left;
      const py = event.clientY - rect.top;
      const wx = (px - this.view.x) / this.view.k;
      const wy = (py - this.view.y) / this.view.k;
      const factor = event.deltaY < 0 ? 1.12 : 1 / 1.12;
      this.view.k = clamp(this.view.k * factor, 0.35, 2.6);
      this.view.x = px - wx * this.view.k;
      this.view.y = py - wy * this.view.k;
      this.applyView();
    }

    hoverNode(node) {
      if (this.hovered === node.id) return;
      this.hovered = node.id;
      const neighbors = this.adjacency.get(node.id) || new Set();
      for (const [id, element] of this.nodeElements) {
        const active = id === node.id || neighbors.has(id);
        element.classList.toggle("active", active);
        element.classList.toggle("dim", !active);
      }
      for (const line of this.linkElements.values()) {
        const active = line.dataset.from === node.id || line.dataset.to === node.id;
        line.classList.toggle("active", active);
        line.classList.toggle("dim", !active);
      }
      this.onHover(node);
    }

    clearHover() {
      this.hovered = null;
      for (const element of this.nodeElements.values()) {
        element.classList.remove("active", "dim");
      }
      for (const line of this.linkElements.values()) {
        line.classList.remove("active", "dim");
      }
      this.onHover(null);
    }

    focusNode(id) {
      const node = this.nodeById.get(id);
      if (!node) return;
      this.view.k = Math.max(this.view.k, 0.9);
      this.view.x = this.width / 2 - node.x * this.view.k;
      this.view.y = this.height / 2 - node.y * this.view.k;
      this.applyView();
      this.hoverNode(node);
      this.onSelect(node);
    }

    highlight(query) {
      const text = (query || "").trim().toLowerCase();
      if (!text) {
        this.clearHover();
        for (const element of this.nodeElements.values()) element.classList.remove("match", "dim");
        return;
      }
      let first = null;
      for (const [id, element] of this.nodeElements) {
        const node = this.nodeById.get(id);
        const matched =
          node.name.toLowerCase().includes(text) ||
          (node.tagline || "").toLowerCase().includes(text);
        element.classList.toggle("match", matched);
        element.classList.toggle("dim", !matched);
        if (matched && !first) first = node;
      }
      for (const line of this.linkElements.values()) line.classList.add("dim");
      if (first) this.onHover(first);
    }

    highlightPath(ids) {
      const path = new Set((ids || []).map(String));
      this.clearHover();
      for (const [id, element] of this.nodeElements) {
        element.classList.toggle("path", path.has(String(id)));
        element.classList.toggle("dim", path.size > 0 && !path.has(String(id)));
      }
      for (const line of this.linkElements.values()) {
        const active =
          path.size > 0 &&
          path.has(String(line.dataset.from)) &&
          path.has(String(line.dataset.to));
        line.classList.toggle("path", active);
        line.classList.toggle("dim", path.size > 0 && !active);
      }
    }

    resetView() {
      this.view.k = 1;
      this.center();
      this.clearHover();
      this.simulate(80);
      this.render();
    }

    zoom(factor) {
      const centerX = this.width / 2;
      const centerY = this.height / 2;
      const wx = (centerX - this.view.x) / this.view.k;
      const wy = (centerY - this.view.y) / this.view.k;
      this.view.k = clamp(this.view.k * factor, 0.35, 2.6);
      this.view.x = centerX - wx * this.view.k;
      this.view.y = centerY - wy * this.view.k;
      this.applyView();
    }

    destroy() {
      window.removeEventListener("resize", this.resizeHandler);
      this.svg.textContent = "";
      this.nodes = [];
      this.links = [];
      this.nodeById = new Map();
      this.adjacency = new Map();
      this.nodeElements = new Map();
      this.linkElements = new Map();
    }
  }

  window.STORY.ForceGraph = ForceGraph;
})();
