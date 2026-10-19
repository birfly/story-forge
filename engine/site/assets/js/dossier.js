/* ============================================================
   Dossier panel — entity card, relations, evidence jumps
   ============================================================ */

window.STORY = window.STORY || {};

(function () {
  "use strict";

  const { esc, typeLabel, kindLabel, kindColor } = window.STORY.util;

  let currentId = null;

  const panel = () => document.getElementById("dossier");
  const inner = () => document.getElementById("dossier-inner");
  const backdrop = () => document.getElementById("dossier-backdrop");

  function sectionTitle(chapterId, sectionId) {
    const entry = window.STORY.data.sectionById.get(`${chapterId}:${sectionId}`);
    return entry ? entry.section.title : "";
  }

  function renderHead(entity, visible) {
    const color = entity.color || "var(--accent)";
    const first = Number(entity.firstAppear);
    const firstLabel = first > 0 ? `首次出现 第 ${first} 章` : "前情提要";
    const kicker = visible
      ? `${typeLabel(entity.type)} · ${firstLabel}`
      : `${typeLabel(entity.type)} · 防剧透`;
    return `
      <div class="dossier-head">
        <div class="dossier-icon" style="--entity-color:${esc(color)}">${
          visible ? esc(entity.icon || entity.name.slice(0, 1)) : "?"
        }</div>
        <div>
          <div class="dossier-kicker">${esc(kicker)}</div>
          <h2 class="dossier-name">${visible ? esc(entity.name) : "？？？"}</h2>
          <p class="dossier-tagline">${
            visible
              ? esc(entity.tagline || "")
              : "防剧透已开启：这个条目在你读到相应章节之前不会展开。"
          }</p>
        </div>
      </div>`;
  }

  function renderRelations(entity) {
    const relations = window.STORY.store.relationsOf(entity.id);
    if (!relations.length) {
      return `<div class="dossier-section-title">关系</div><p class="dim">暂无可显示的关系。</p>`;
    }
    const items = relations
      .map((relation) => {
        const other = window.STORY.store.otherOf(relation, entity.id);
        if (!other) return "";
        const color = kindColor(relation.kind);
        return `
          <button class="rel-item" type="button" data-rel="${esc(other.id)}">
            <span class="rel-kind" style="--kind-color:${color}"></span>
            <span class="rel-name">${esc(other.name)}</span>
            <span class="rel-label">${esc(relation.label || kindLabel(relation.kind))}</span>
          </button>`;
      })
      .join("");
    return `
      <div class="dossier-section-title">关系 · ${relations.length}</div>
      <div class="rel-list">${items}</div>`;
  }

  function renderEvidence(entity) {
    const evidence = entity.evidence || [];
    if (!evidence.length) return "";
    const items = evidence
      .map((ev, index) => {
        const title = sectionTitle(ev.chapter, ev.section);
        const chapter = window.STORY.data.chapterById.get(String(ev.chapter));
        const chapterNo = chapter
          ? window.STORY.store.chapterNumber(chapter)
          : ev.chapter;
        return `
          <button class="evidence-item" type="button" data-ev="${index}">
            <span class="evidence-quote">“${esc(ev.quote)}”</span>
            <span class="evidence-meta">第 ${chapterNo} 章 · ${esc(title)}${
              ev.note ? ` · ${esc(ev.note)}` : ""
            }</span>
          </button>`;
      })
      .join("");
    return `
      <div class="dossier-section-title">原文证据 · ${evidence.length}</div>
      <div class="evidence-list">${items}</div>`;
  }

  function renderActions(entity) {
    return `
      <div class="dossier-actions">
        <button class="btn primary" type="button" data-action="atlas">在星图中查看</button>
        <button class="btn ghost" type="button" data-action="read">跳转到正文</button>
      </div>`;
  }

  function renderMentions(entity) {
    const mentions = window.STORY.store.mentionsOf(entity.id);
    if (!mentions.length) return "";
    const items = mentions
      .map((item, index) => {
        const chapter = window.STORY.data.chapterById.get(String(item.chapter));
        const entry = window.STORY.data.sectionById.get(
          `${item.chapter}:${item.section}`
        );
        const title = entry ? entry.section.title : item.section;
        const chapterNo = chapter
          ? window.STORY.store.chapterNumber(chapter)
          : item.chapter;
        return `
          <button class="mention-item" type="button" data-mention="${index}">
            <span class="mention-chapter">第 ${chapterNo} 章</span>
            <span class="mention-section">${esc(title)}</span>
            <span class="mention-count">${item.count} 次</span>
          </button>`;
      })
      .join("");
    return `
      <div class="dossier-section-title">出现位置 · ${mentions.length}</div>
      <div class="mention-list">${items}</div>`;
  }

  function open(entityId) {
    const entity = window.STORY.data.entityById.get(entityId);
    if (!entity) return;
    currentId = entityId;
    const visible = window.STORY.store.isVisible(entity);

    inner().innerHTML = `
      <button class="dossier-close" type="button" aria-label="关闭档案">×</button>
      ${renderHead(entity, visible)}
      ${
        visible
          ? `<p class="dossier-summary">${esc(entity.summary || "")}</p>
             ${renderRelations(entity)}
             ${renderEvidence(entity)}
             ${renderMentions(entity)}
             ${renderActions(entity)}`
          : `<p class="dossier-summary dim">把阅读进度或防剧透开关调整到第 ${
              entity.spoilerFrom
            } 章之后，即可查看完整档案。</p>`
      }`;

    inner().scrollTop = 0;
    panel().classList.add("open");
    panel().setAttribute("aria-hidden", "false");
    if (window.innerWidth <= 860) backdrop().hidden = false;

    const closeButton = inner().querySelector(".dossier-close");
    if (closeButton) closeButton.focus({ preventScroll: true });

    bind(entity, visible);
  }

  function bind(entity, visible) {
    const closeButton = inner().querySelector(".dossier-close");
    if (closeButton) closeButton.addEventListener("click", close);

    inner().querySelectorAll("[data-rel]").forEach((button) => {
      button.addEventListener("click", () => open(button.dataset.rel));
    });

    inner().querySelectorAll("[data-ev]").forEach((button) => {
      button.addEventListener("click", () => {
        const ev = (entity.evidence || [])[Number(button.dataset.ev)];
        if (ev) jump(ev);
      });
    });

    inner().querySelectorAll("[data-mention]").forEach((button) => {
      button.addEventListener("click", () => {
        const mention = window.STORY.store.mentionsOf(entity.id)[
          Number(button.dataset.mention)
        ];
        if (!mention) return;
        close();
        window.STORY.reader.scrollToSection(mention.chapter, mention.section);
      });
    });

    const atlasButton = inner().querySelector('[data-action="atlas"]');
    if (atlasButton) {
      atlasButton.addEventListener("click", () => {
        close();
        window.location.hash = `#/atlas?focus=${encodeURIComponent(entity.id)}`;
      });
    }

    const readButton = inner().querySelector('[data-action="read"]');
    if (readButton) {
      readButton.addEventListener("click", () => {
        const ev = (entity.evidence || [])[0];
        if (ev) {
          jump(ev);
        } else {
          close();
          const fallback =
            window.STORY.store.firstChapter && window.STORY.store.firstChapter.id;
          window.location.hash = `#/read/${entity.firstAppear || fallback || ""}`;
        }
      });
    }
  }

  function jump(ev) {
    close();
    window.STORY._pendingEvidence = ev;
    const target = `#/read/${ev.chapter}`;
    if (window.location.hash === target) {
      window.STORY.reader.scrollToEvidence(ev);
    } else {
      window.location.hash = target;
    }
  }

  function scrollToEvidence(ev) {
    const section = document.getElementById(ev.section);
    if (!section) return;
    window.setTimeout(() => {
      section.scrollIntoView({ behavior: "smooth", block: "start" });
      window.setTimeout(() => markQuote(section, ev.quote), 350);
    }, 120);
  }

  function markQuote(root, quote) {
    root.querySelectorAll(".evidence-mark").forEach((mark) => {
      const parent = mark.parentNode;
      while (mark.firstChild) parent.insertBefore(mark.firstChild, mark);
      parent.removeChild(mark);
      parent.normalize();
    });

    const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
    let node;
    while ((node = walker.nextNode())) {
      const index = node.nodeValue.indexOf(quote);
      if (index < 0) continue;
      try {
        const range = document.createRange();
        range.setStart(node, index);
        range.setEnd(node, index + quote.length);
        const mark = document.createElement("mark");
        mark.className = "evidence-mark";
        range.surroundContents(mark);
        window.setTimeout(() => {
          mark.classList.add("fade");
        }, 4200);
        return;
      } catch (error) {
        break;
      }
    }
    sectionFlash(root);
  }

  function sectionFlash(root) {
    root.classList.add("flash");
    window.setTimeout(() => root.classList.remove("flash"), 1800);
  }

  function close() {
    currentId = null;
    panel().classList.remove("open");
    panel().setAttribute("aria-hidden", "true");
    backdrop().hidden = true;
  }

  function current() {
    return currentId ? window.STORY.data.entityById.get(currentId) : null;
  }

  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape") close();
  });

  document.addEventListener("click", (event) => {
    if (event.target === backdrop()) close();
  });

  window.STORY.dossier = {
    open,
    close,
    current,
    scrollToEvidence,
    jump,
  };
})();
