/* ============================================================
   Glossary view — term entities, searchable, spoiler-gated
   ============================================================ */

window.STORY = window.STORY || {};

(function () {
  "use strict";

  const { esc } = window.STORY.util;

  let query = "";
  let sortMode = "appearance";
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

  function terms() {
    return window.STORY.data.entities.filter((entity) => entity.type === "term");
  }

  function termVisible(term) {
    if (!window.STORY.store.state.spoiler) return true;
    const from = Number(term.spoilerFrom);
    if (Number.isFinite(from)) return from <= progress;
    return true;
  }

  function chapterLabel(order) {
    const number = Number(order || 0);
    if (!number) return "前情提要";
    const chapter =
      window.STORY.data.chapterByOrder.get(number) ||
      window.STORY.data.chapters.find(
        (item) => Number(item.order) === number
      );
    if (!chapter) return `第 ${number} 章`;
    return `第 ${window.STORY.store.chapterNumber(chapter)} 章 · ${chapter.title}`;
  }

  function filtered() {
    const q = query.trim().toLowerCase();
    return terms()
      .filter((term) => {
        if (!q) return true;
        if (!termVisible(term)) return false;
        return `${term.name} ${term.tagline || ""} ${term.summary || ""}`
          .toLowerCase()
          .includes(q);
      })
      .sort((a, b) => {
        if (sortMode === "name") {
          return String(a.name).localeCompare(String(b.name), "zh-Hans-CN");
        }
        const first = Number(a.firstAppear || 0);
        const second = Number(b.firstAppear || 0);
        if (first !== second) return first - second;
        return String(a.name).localeCompare(String(b.name), "zh-Hans-CN");
      });
  }

  function termCard(term) {
    const visible = termVisible(term);
    return `
      <article class="glossary-card ${visible ? "" : "locked"}" data-term="${esc(
      term.id
    )}" tabindex="0">
        <div class="g-head">
          <span class="g-icon" style="--entity-color:${esc(
            term.color || "var(--accent)"
          )}">${visible ? esc(term.icon || term.name.slice(0, 1)) : "?"}</span>
          <div>
            <h3>${visible ? esc(term.name) : "？？？"}</h3>
            <span class="g-first">${esc(chapterLabel(term.firstAppear))}</span>
          </div>
        </div>
        <p class="g-tagline">${
          visible
            ? esc(term.tagline || "")
            : "防剧透已开启：读到相应章节后再展开。"
        }</p>
        ${
          visible && term.summary
            ? `<p class="g-summary">${esc(term.summary)}</p>`
            : ""
        }
        ${
          visible && term.aliases && term.aliases.length
            ? `<div class="g-aliases">${term.aliases
                .filter((alias) => alias !== term.name)
                .map((alias) => `<span>${esc(alias)}</span>`)
                .join("")}</div>`
            : ""
        }
      </article>`;
  }

  function renderList() {
    const host = document.getElementById("glossary-list");
    if (!host) return;
    const items = filtered();
    if (!items.length) {
      host.innerHTML = `<div class="glossary-empty">${
        terms().length
          ? "没有匹配的术语。"
          : "这个项目还没有登记术语实体。在 <code>content/entities.json</code> 中添加 <code>type: \"term\"</code> 的实体即可。"
      }</div>`;
      return;
    }
    if (sortMode === "name") {
      host.innerHTML = `<div class="glossary-grid">${items
        .map(termCard)
        .join("")}</div>`;
    } else {
      const groups = [];
      for (const term of items) {
        const key = Number(term.firstAppear || 0);
        let group = groups.find((item) => item.key === key);
        if (!group) {
          group = { key, label: chapterLabel(key), items: [] };
          groups.push(group);
        }
        group.items.push(term);
      }
      host.innerHTML = groups
        .map(
          (group) => `
            <section class="glossary-group">
              <h2>${esc(group.label)}<span>${group.items.length}</span></h2>
              <div class="glossary-grid">${group.items.map(termCard).join("")}</div>
            </section>`
        )
        .join("");
    }
    bindCards();
  }

  function bindCards() {
    const host = document.getElementById("glossary-list");
    if (!host) return;
    host.querySelectorAll("[data-term]").forEach((card) => {
      const open = () => window.STORY.dossier.open(card.dataset.term);
      card.addEventListener("click", open);
      card.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          open();
        }
      });
    });
  }

  function render() {
    progress = latestOrder();
    window.STORY.store.state.route = "glossary";
    const total = terms().length;

    document.getElementById("view").innerHTML = `
      <section class="glossary-page">
        <header class="page-hero">
          <div class="hero-kicker">
            <span class="line"></span>
            <span class="eyebrow">GLOSSARY</span>
          </div>
          <h1>术语表</h1>
          <p>正文里出现过的概念、物件与专名。点击卡片打开档案，查看关系与原文证据。</p>
        </header>
        <div class="glossary-toolbar">
          <div class="glossary-search">
            <input id="glossary-search" type="search" placeholder="搜索术语…"
              value="${esc(query)}" aria-label="搜索术语">
          </div>
          <div class="glossary-sort" role="group" aria-label="排序">
            <button type="button" data-sort="appearance" class="${
              sortMode === "appearance" ? "on" : ""
            }">按出现顺序</button>
            <button type="button" data-sort="name" class="${
              sortMode === "name" ? "on" : ""
            }">按名称</button>
          </div>
          <span class="glossary-count">${total} 条</span>
        </div>
        <div id="glossary-list"></div>
      </section>`;

    renderList();

    const searchInput = document.getElementById("glossary-search");
    if (searchInput) {
      searchInput.addEventListener("input", () => {
        query = searchInput.value;
        renderList();
      });
    }
    document.querySelectorAll("[data-sort]").forEach((button) => {
      button.addEventListener("click", () => {
        sortMode = button.dataset.sort;
        document
          .querySelectorAll("[data-sort]")
          .forEach((item) =>
            item.classList.toggle("on", item.dataset.sort === sortMode)
          );
        renderList();
      });
    });
  }

  window.STORY.glossary = { render };
})();
