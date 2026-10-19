/* ============================================================
   Timeline view — structured events, spoiler-gated
   ============================================================ */

window.STORY = window.STORY || {};

(function () {
  "use strict";

  const { esc } = window.STORY.util;

  let events = [];
  let progress = 1;

  function chapterOrders() {
    return window.STORY.data.chapters
      .map((chapter) => Number(chapter.order))
      .filter(Number.isFinite);
  }

  function latestOrder() {
    const orders = chapterOrders();
    if (!orders.length) return 1;
    const position = window.STORY.store.getPosition();
    const saved = position ? Number(position.order) : NaN;
    if (Number.isFinite(saved) && saved > 0) {
      return Math.min(saved, Math.max(...orders));
    }
    return Math.max(...orders);
  }

  function eventOrder(event, index) {
    const explicit = Number(event.order);
    if (Number.isFinite(explicit)) return explicit;
    const chapter = window.STORY.data.chapterById.get(String(event.chapter || ""));
    if (chapter) return Number(chapter.order || 0) * 1000 + index;
    return 100000 + index;
  }

  function visible(event) {
    if (!window.STORY.store.state.spoiler) return true;
    const from = Number(event.spoilerFrom);
    if (Number.isFinite(from)) return from <= progress;
    const chapter = window.STORY.data.chapterById.get(String(event.chapter || ""));
    return !chapter || Number(chapter.order || 0) <= progress;
  }

  function entityChips(event) {
    const chips = (event.entities || [])
      .map((id) => window.STORY.data.entityById.get(id))
      .filter(Boolean)
      .filter((entity) => window.STORY.store.isVisible(entity, progress));
    if (!chips.length) return "";
    return `<div class="event-cast">${chips
      .map(
        (entity) => `
          <button class="cast-chip" type="button" data-ent="${esc(entity.id)}">
            <span class="dot" style="--entity-color:${esc(
              entity.color || "var(--accent)"
            )}">${esc(entity.icon || entity.name.slice(0, 1))}</span>
            <span>${esc(entity.name)}</span>
          </button>`
      )
      .join("")}</div>`;
  }

  function eventTitle(id) {
    const found = events.find((event) => String(event.id) === String(id));
    return found ? found.title || found.id : id;
  }

  function linkButtons(event, key, label) {
    const ids = event[key] || [];
    if (!ids.length) return "";
    return `
      <div class="event-links">
        <span>${label}</span>
        ${ids
          .map(
            (id) =>
              `<button type="button" data-event="${esc(id)}">${esc(
                eventTitle(id)
              )}</button>`
          )
          .join("")}
      </div>`;
  }

  function evidenceButton(event) {
    if (!event.evidence || !event.evidence.length) return "";
    return `<button class="event-evidence" type="button" data-evidence="1">原文证据 · ${
      event.evidence.length
    }</button>`;
  }

  function renderList() {
    const host = document.getElementById("timeline-list");
    if (!host) return;
    if (!events.length) {
      host.innerHTML = `<div class="timeline-empty">还没有登记事件线。在 <code>content/timeline.json</code> 里添加事件后重新构建。</div>`;
      return;
    }
    const shown = events
      .map((event, index) => ({
        event,
        index,
        order: eventOrder(event, index),
      }))
      .filter((item) => visible(item.event))
      .sort((a, b) => a.order - b.order);
    if (!shown.length) {
      host.innerHTML = `<div class="timeline-empty">当前进度下没有可显示的事件。把进度滑杆向右拖，或关闭防剧透。</div>`;
      return;
    }
    host.innerHTML = shown
      .map(
        ({ event }, index) => `
        <article class="timeline-event" id="event-${esc(event.id)}">
          <div class="event-axis">
            <span class="event-dot"></span>
            <span class="event-index">${String(index + 1).padStart(2, "0")}</span>
          </div>
          <div class="event-body">
            <div class="event-head">
              <h3>${esc(event.title || event.id)}</h3>
              ${
                event.storyTime
                  ? `<span class="event-time">${esc(event.storyTime)}</span>`
                  : ""
              }
            </div>
            ${event.summary ? `<p>${esc(event.summary)}</p>` : ""}
            ${entityChips(event)}
            ${linkButtons(event, "causes", "前因")}
            ${linkButtons(event, "consequences", "后果")}
            ${evidenceButton(event)}
          </div>
        </article>`
      )
      .join("");
    bindList();
  }

  function bindList() {
    const host = document.getElementById("timeline-list");
    if (!host) return;
    host.querySelectorAll("[data-ent]").forEach((button) => {
      button.addEventListener("click", () =>
        window.STORY.dossier.open(button.dataset.ent)
      );
    });
    host.querySelectorAll("[data-event]").forEach((button) => {
      button.addEventListener("click", () => {
        const target = document.getElementById(`event-${button.dataset.event}`);
        if (target) target.scrollIntoView({ behavior: "smooth", block: "center" });
      });
    });
    host.querySelectorAll("[data-evidence]").forEach((button) => {
      button.addEventListener("click", () => {
        const card = button.closest(".timeline-event");
        const event = events.find(
          (item) => `event-${item.id}` === (card ? card.id : "")
        );
        const evidence = event && (event.evidence || [])[0];
        if (evidence) window.STORY.dossier.jump(evidence);
      });
    });
  }

  function render() {
    const data = window.STORY.data.timeline || { events: [] };
    events = Array.isArray(data.events) ? data.events : [];
    progress = latestOrder();
    window.STORY.store.state.route = "timeline";
    const orders = chapterOrders();
    const minOrder = orders.length ? Math.min(...orders) : 1;
    const maxOrder = orders.length ? Math.max(...orders) : 1;

    document.getElementById("view").innerHTML = `
      <section class="timeline-page">
        <header class="page-hero">
          <div class="hero-kicker">
            <span class="line"></span>
            <span class="eyebrow">${esc(data.kicker || "TIMELINE")}</span>
          </div>
          <h1>${esc(data.title || "事件线")}</h1>
          ${data.lede ? `<p>${esc(data.lede)}</p>` : ""}
        </header>
        <div class="timeline-toolbar">
          <label for="timeline-progress">读到</label>
          <input id="timeline-progress" type="range"
            min="${minOrder}" max="${maxOrder}" step="1" value="${progress}">
          <output id="timeline-progress-out">第 ${progress} 章</output>
          <span class="timeline-count">${events.length} 个事件</span>
        </div>
        <div id="timeline-list" class="timeline-list"></div>
      </section>`;

    renderList();

    const range = document.getElementById("timeline-progress");
    const output = document.getElementById("timeline-progress-out");
    if (range) {
      range.addEventListener("input", () => {
        if (output) output.textContent = `第 ${range.value} 章`;
      });
      range.addEventListener("change", () => {
        progress = Number(range.value);
        window.STORY.store.state.chapterOrder = progress;
        renderList();
      });
    }
  }

  window.STORY.timelinePage = { render };
})();
