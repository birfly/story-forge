/* ============================================================
   App — router, home, recap, global controls
   ============================================================ */

window.STORY = window.STORY || {};

(function () {
  "use strict";

  const { esc } = window.STORY.util;
  let revealObserver = null;

  function stats() {
    const chapters = window.STORY.data.chapters;
    const words = chapters.reduce(
      (sum, chapter) => sum + (chapter.hanzi || chapter.chars || 0),
      0
    );
    return {
      words,
      chapters: chapters.length,
      entities: window.STORY.data.entities.length,
      relations: window.STORY.data.relations.length,
    };
  }

  function worldCard(card, index, span) {
    return `
      <article class="world-card ${span} reveal" data-ent="${esc(card.entity)}" tabindex="0">
        <span class="w-idx">${String(index + 1).padStart(2, "0")}</span>
        <h3>${esc(card.title)}</h3>
        <p class="one-liner">${esc(card.oneLiner)}</p>
        <p>${esc(card.body)}</p>
        <span class="w-link">查看档案 ↗</span>
      </article>`;
  }

  function bindWorldCards() {
    document.querySelectorAll(".world-card[data-ent]").forEach((card) => {
      const open = () => window.STORY.dossier.open(card.dataset.ent);
      card.addEventListener("click", open);
      card.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          open();
        }
      });
    });
  }

  function renderHome() {
    window.STORY.store.state.route = "home";
    const summary = stats();
    const cards = window.STORY.data.worldview.cards;
    const spans = ["span-6", "span-3", "span-3", "span-4", "span-4", "span-4"];
    const eras = window.STORY.data.recap.eras || [];
    const ready = window.STORY.store.state.ready;
    const config = window.STORY.store.config || {};
    const orderedChapters = window.STORY.data.chapters
      .slice()
      .sort((a, b) => Number(a.order) - Number(b.order));
    const first = window.STORY.store.firstChapter || orderedChapters[0] || null;
    const firstId = first ? first.id : "";
    const firstNum = first ? window.STORY.store.chapterNumber(first) : "";
    const firstMeta = first ? window.STORY.store.chapterMeta(first.id) : null;
    const last = orderedChapters[orderedChapters.length - 1] || first;
    const lastNum = last ? window.STORY.store.chapterNumber(last) : "";
    const heroTitle = config.title || (first ? first.title : "故事");
    const heroSubtitle = config.subtitle || "富结构故事阅读站";
    const heroLede =
      config.lede ||
      "这不是一篇平铺的小说。人物、势力、地点、术语与证据被织成一张网——点开任何一个名字，都能看见它从哪里来、与谁相连。";

    const chapterCard = (chapter) => {
      const active = String(chapter.id) === String(firstId);
      const pending = !ready.has(String(chapter.id));
      return `
          <button class="chapter-card ${active ? "active" : ""} ${pending ? "disabled" : ""}"
            type="button" data-chapter="${chapter.id}" ${pending ? 'aria-disabled="true"' : ""}>
            <span class="c-num">${window.STORY.store.chapterNumber(chapter)}</span>
            <span class="c-title">${esc(chapter.title)}</span>
            <span class="c-status">${active ? "开始阅读" : pending ? "待续" : "可阅读"}</span>
          </button>`;
    };
    const chapterGroups = [];
    for (const chapter of window.STORY.data.chapters) {
      const volume = window.STORY.store.volumeOf(chapter);
      const key = volume ? String(volume.id) : "";
      let group = chapterGroups.find((item) => item.key === key);
      if (!group) {
        group = { key, volume, chapters: [] };
        chapterGroups.push(group);
      }
      group.chapters.push(chapter);
    }
    const hasVolumes = chapterGroups.some((group) => group.volume);
    const chapterCards = hasVolumes
      ? chapterGroups
          .map((group) => {
            const cards = group.chapters.map(chapterCard).join("");
            if (!group.volume) {
              return `<div class="chapter-strip">${cards}</div>`;
            }
            return `<div class="chapter-volume">
              <div class="chapter-volume-head">
                <span>${esc(group.volume.title)}</span>
                <span>${group.chapters.length} 章</span>
              </div>
              <div class="chapter-strip">${cards}</div>
            </div>`;
          })
          .join("")
      : `<div class="chapter-strip">${window.STORY.data.chapters
          .map(chapterCard)
          .join("")}</div>`;

    document.getElementById("view").innerHTML = `
      <section class="home-hero">
        <div class="hero-copy">
          <div class="hero-kicker">
            <span class="line"></span>
            <span class="eyebrow">${esc(config.eyebrow || `STORY · ${window.STORY.store.chapterRange()}`)}</span>
          </div>
          <h1 class="hero-title">${esc(heroTitle)}<span class="thin">${esc(heroSubtitle)}</span></h1>
          <p class="hero-lede">${esc(heroLede)}</p>
          <div class="hero-actions">
            <a class="btn primary" href="#/read/${firstId}">开始阅读 · 第 ${firstNum} 章</a>
            <a class="btn" href="#/recap">先看前情提要</a>
            <a class="btn ghost" href="#/atlas">打开星图</a>
          </div>
          <div class="hero-stats">
            <div class="hero-stat"><span class="num">${summary.words.toLocaleString(
              "zh-CN"
            )}</span><span class="lbl">正文汉字</span></div>
            <div class="hero-stat"><span class="num">${summary.chapters}</span><span class="lbl">章节</span></div>
            <div class="hero-stat"><span class="num">${summary.entities}</span><span class="lbl">实体</span></div>
            <div class="hero-stat"><span class="num">${summary.relations}</span><span class="lbl">关系</span></div>
          </div>
        </div>
        <div class="hero-visual" aria-hidden="true">
          <div class="hero-chapter-num" data-num="${firstNum}">${firstNum}</div>
          <div class="hero-chapter-meta">
            <div><strong>${esc(first ? first.title : "")}</strong>${esc(
      firstMeta && firstMeta.codename ? firstMeta.codename : ""
    )}</div>
            <div>READING PREVIEW<br>CHAPTER ${firstNum} / ${lastNum}</div>
          </div>
        </div>
      </section>

      <section class="section">
        <div class="section-head">
          <span class="idx">01 / WORLD</span>
          <h2>开读前 3 分钟</h2>
          <span class="rule"></span>
        </div>
        <div class="world-grid">
          ${cards.slice(0, 6).map((card, index) => worldCard(card, index, spans[index] || "span-4")).join("")}
        </div>
      </section>

      <section class="section">
        <div class="section-head">
          <span class="idx">02 / STORY SO FAR</span>
          <h2>前情提要</h2>
          <span class="rule"></span>
          <a class="mono" href="#/recap">完整时间线 →</a>
        </div>
        <div class="timeline">
          ${eras
            .slice(0, 3)
            .map(
              (era) => `
                <div class="era reveal">
                  <div class="era-label">${esc(era.label)}</div>
                  <div class="era-body">
                    <h3>${esc(era.title)}</h3>
                    <p class="era-summary">${esc(era.summary)}</p>
                  </div>
                </div>`
            )
            .join("")}
        </div>
      </section>

      <section class="section">
        <div class="section-head">
          <span class="idx">03 / CHAPTERS</span>
          <h2>第 1—N 章</h2>
          <span class="rule"></span>
        </div>
        ${chapterCards}
      </section>

      <section class="section">
        <div class="section-head">
          <span class="idx">04 / HOW TO READ</span>
          <h2>阅读须知</h2>
          <span class="rule"></span>
        </div>
        <div class="notice-grid">
          <article class="notice reveal">
            <span class="n-icon">01</span>
            <h3>点开每一个名字</h3>
            <p>正文里带虚线的名称都可以点击。右侧会打开档案：一句话认识、详细说明、关系网，以及可跳回原文的证据。</p>
          </article>
          <article class="notice reveal">
            <span class="n-icon">02</span>
            <h3>用星图看整张网</h3>
            <p>星图把人物、势力、地点、术语与事件放在同一张图里。可以按类型筛选，也可以把阅读进度拖到某一章，只看当时已知的信息。</p>
          </article>
          <article class="notice reveal">
            <span class="n-icon">03</span>
            <h3>防剧透默认开启</h3>
            <p>系统只显示当前章节及之前的信息。你可以随时在右上角关闭它，提前查看完整关系网。</p>
          </article>
        </div>
      </section>

      <footer class="section" style="border-top:1px solid var(--line);padding-top:2rem;padding-bottom:3rem">
        <p class="mono">${esc(config.footerNote || "STORY ARCHIVE")}</p>
        ${
          config.footerDetail
            ? `<p class="dim" style="margin-top:0.6rem;max-width:52em;font-family:var(--font-serif);font-size:0.88rem;line-height:1.9">${esc(
                config.footerDetail
              )}</p>`
            : ""
        }
      </footer>`;

    bindWorldCards();
    bindChapterCards();
    observeReveals();
  }

  function bindChapterCards() {
    document.querySelectorAll(".chapter-card[data-chapter]").forEach((card) => {
      card.addEventListener("click", () => {
        const id = card.dataset.chapter;
        if (window.STORY.store.state.ready.has(String(id))) {
          window.location.hash = `#/read/${id}`;
        } else {
          window.STORY.store.toast("这一章还在制作中");
        }
      });
    });
  }

  function renderRecap() {
    window.STORY.store.state.route = "recap";
    const recap = window.STORY.data.recap;
    const cards = window.STORY.data.worldview.cards;
    const first = window.STORY.store.firstChapter;
    const firstNum = first ? window.STORY.store.chapterNumber(first) : "";
    const recapTitle = recap.title || `在进入第 ${firstNum} 章之前`;
    const recapKicker = recap.kicker || "STORY SO FAR";

    document.getElementById("view").innerHTML = `
      <header class="recap-hero">
        <div class="hero-kicker">
          <span class="line"></span>
          <span class="eyebrow">${esc(recapKicker)}</span>
        </div>
        <h1>${esc(recapTitle)}</h1>
        <p>${esc(recap.lede || "")}</p>
      </header>

      <div class="timeline">
        ${(recap.eras || [])
          .map(
            (era) => `
              <article class="era reveal">
                <div class="era-label">${esc(era.label)}</div>
                <div class="era-body">
                  <h3>${esc(era.title)}</h3>
                  <p class="era-summary">${esc(era.summary)}</p>
                  ${
                    era.beats && era.beats.length
                      ? `<ul>${era.beats.map((beat) => `<li>${esc(beat)}</li>`).join("")}</ul>`
                      : ""
                  }
                </div>
              </article>`
          )
          .join("")}
      </div>

      <section class="where-box reveal">
        <h2>${esc(recap.whereYouAre ? recap.whereYouAre.title : "你现在在哪里")}</h2>
        <p>${esc(recap.whereYouAre ? recap.whereYouAre.text : "")}</p>
        <ul class="where-list">
          ${(recap.whereYouAre && recap.whereYouAre.checklist
            ? recap.whereYouAre.checklist
            : []
          )
            .map((item) => {
              const split = item.indexOf("：");
              if (split < 0) return `<li>${esc(item)}</li>`;
              return `<li><span class="who">${esc(item.slice(0, split))}</span><span>${esc(
                item.slice(split + 1)
              )}</span></li>`;
            })
            .join("")}
        </ul>
      </section>

      <section class="section" style="border-top:1px solid var(--line)">
        <div class="section-head">
          <span class="idx">WORLD</span>
          <h2>世界观速览</h2>
          <span class="rule"></span>
        </div>
        <div class="world-grid">
          ${cards.map((card, index) => worldCard(card, index, index < 2 ? "span-6" : "span-4")).join("")}
        </div>
      </section>

      <div class="recap-cta">
        <a class="btn primary" href="#/read/${first ? first.id : ""}">进入第 ${firstNum} 章${
      first ? ` · ${esc(first.title)}` : ""
    }</a>
      </div>`;

    bindWorldCards();
    observeReveals();
  }

  function observeReveals() {
    if (revealObserver) revealObserver.disconnect();
    const elements = document.querySelectorAll(".reveal");
    if (!("IntersectionObserver" in window)) {
      elements.forEach((element) => element.classList.add("in"));
      return;
    }
    revealObserver = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          entry.target.classList.add("in");
          revealObserver.unobserve(entry.target);
        });
      },
      { threshold: 0.08 }
    );
    elements.forEach((element) => revealObserver.observe(element));
  }

  function updateNav(route) {
    const map = {
      home: "home",
      recap: "recap",
      read: "reader",
      atlas: "atlas",
      timeline: "timeline",
      glossary: "glossary",
    };
    document.querySelectorAll("[data-nav]").forEach((link) => {
      link.classList.toggle("active", link.dataset.nav === map[route]);
    });
  }

  function cleanup() {
    if (window.STORY.reader) window.STORY.reader.destroy();
    if (window.STORY.atlas) window.STORY.atlas.destroy();
    if (window.STORY.dossier) window.STORY.dossier.close();
    if (revealObserver) {
      revealObserver.disconnect();
      revealObserver = null;
    }
  }

  function route() {
    const hash = window.location.hash || "#/";
    const path = hash.slice(1).split("?")[0];
    const segments = path.split("/").filter(Boolean);
    const routeName = segments[0] || "home";

    cleanup();
    updateNav(routeName);

    const modeToggle = document.getElementById("mode-toggle");
    if (modeToggle && routeName !== "read") {
      modeToggle.hidden = true;
      modeToggle.innerHTML = "";
    }

    if (routeName === "read") {
      const fallback = window.STORY.store.firstChapter
        ? window.STORY.store.firstChapter.id
        : null;
      window.STORY.reader.render(segments[1] || fallback);
    } else if (routeName === "atlas") {
      window.STORY.atlas.render();
    } else if (routeName === "timeline" && window.STORY.timelinePage) {
      window.STORY.timelinePage.render();
    } else if (routeName === "glossary" && window.STORY.glossary) {
      window.STORY.glossary.render();
    } else if (routeName === "recap") {
      renderRecap();
    } else {
      renderHome();
    }

    window.scrollTo({ top: 0, behavior: "auto" });
  }

  function bindGlobalControls() {
    const config = window.STORY.store.config || {};
    const first = window.STORY.store.firstChapter;
    const themeButton = document.getElementById("theme-toggle");
    const fontButton = document.getElementById("font-toggle");
    const spoilerButton = document.getElementById("spoiler-toggle");
    const modeToggle = document.getElementById("mode-toggle");

    const pageTitle = [config.title, config.subtitle].filter(Boolean).join(" · ");
    if (pageTitle) document.title = pageTitle;
    const description = document.querySelector('meta[name="description"]');
    if (description && config.description) description.content = config.description;
    if (config.brand) {
      const mark = document.querySelector(".brand-mark");
      const name = document.querySelector(".brand-name");
      if (mark && config.brand.mark) mark.textContent = config.brand.mark;
      if (name && config.brand.name) name.textContent = config.brand.name;
    }
    const readNav = document.querySelector('[data-nav="reader"]');
    if (readNav && first) readNav.href = `#/read/${first.id}`;

    const sync = () => {
      document.documentElement.dataset.theme = window.STORY.store.state.theme;
      document.documentElement.style.setProperty(
        "--reader-size",
        `${window.STORY.store.state.font}px`
      );
      if (themeButton) themeButton.textContent = window.STORY.store.state.theme === "dark" ? "◐" : "◑";
      if (spoilerButton) {
        spoilerButton.classList.toggle("on", window.STORY.store.state.spoiler);
        spoilerButton.setAttribute(
          "aria-pressed",
          window.STORY.store.state.spoiler ? "true" : "false"
        );
      }
    };

    window.STORY.store.applyTheme(window.STORY.store.state.theme);
    window.STORY.store.applyFont(window.STORY.store.state.font);

    if (themeButton) {
      themeButton.addEventListener("click", () => {
        window.STORY.store.toggleTheme();
        sync();
      });
    }

    if (fontButton) {
      fontButton.addEventListener("click", () => {
        window.STORY.store.cycleFont();
        sync();
        window.STORY.store.toast(`正文字号 ${window.STORY.store.state.font}px`);
      });
    }

    if (spoilerButton) {
      spoilerButton.addEventListener("click", () => {
        window.STORY.store.setSpoiler(!window.STORY.store.state.spoiler);
        sync();
        window.STORY.store.toast(
          window.STORY.store.state.spoiler ? "防剧透已开启" : "防剧透已关闭"
        );
        if (window.STORY.store.state.route === "atlas") {
          window.STORY.atlas.render();
        }
      });
    }

    if (modeToggle) {
      modeToggle.addEventListener("click", (event) => {
        const button = event.target.closest("[data-mode]");
        if (button && window.STORY.reader) {
          window.STORY.reader.setMode(button.dataset.mode);
        }
      });
    }

    sync();
  }

  function boot() {
    bindGlobalControls();
    window.addEventListener("hashchange", route);
    route();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
