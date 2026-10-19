/* ============================================================
   Reader view — TOC, chapter cover, prose, progress, position
   ============================================================ */

window.STORY = window.STORY || {};

(function () {
  "use strict";

  const { esc } = window.STORY.util;
  const DEFAULT_PALETTE = ["#e23a4e", "#7fd6d6", "#c9a227", "#d98c5f", "#6fbf8f", "#7a9fe2"];

  function chapterAccent(chapter) {
    const palette =
      (window.STORY.store.config && window.STORY.store.config.accentPalette) ||
      DEFAULT_PALETTE;
    const order = Number(chapter.order || 1);
    return palette[(order - 1) % palette.length] || DEFAULT_PALETTE[0];
  }

  function modeLabel(mode) {
    const config = window.STORY.store.config || {};
    if (config.kind === "creation" && mode === "retold") return "创作";
    const labels = config.modeLabels || {};
    return labels[mode] || mode;
  }

  function variantFor(chapter, mode) {
    const store = window.STORY.store;
    return (
      store.variantOf(chapter, mode) ||
      store.variantOf(chapter, store.resolveMode(chapter)) ||
      chapter
    );
  }

  let observer = null;
  let scrollHandler = null;
  let currentChapterId = null;
  let saveTimer = null;

  function sectionIndexLabel(part, section) {
    const sections = part.sections.filter((item) => item.title !== "开篇");
    const index = sections.findIndex((item) => item.id === section.id);
    return index >= 0 ? String(index + 1).padStart(2, "0") : "";
  }

  function renderToc(currentChapter) {
    const chapters = window.STORY.data.chapters;
    const currentMode = window.STORY.store.resolveMode(currentChapter);
    const currentVariant = variantFor(currentChapter, currentMode);

    const chapterItem = (chapter) => {
      const active = String(chapter.id) === String(currentChapter.id);
      const ready = window.STORY.store.state.ready.has(String(chapter.id));
      const parts =
        active && currentVariant && Array.isArray(currentVariant.parts)
          ? currentVariant.parts
            .filter((part) => part.title !== "开篇")
            .map(
              (part) => `
                  <div class="toc-part">
                    <button class="toc-part-btn" type="button" data-scroll="${esc(
                      part.sections[0] ? part.sections[0].id : ""
                    )}">${esc(part.title)}</button>
                    <div class="toc-sections">
                      ${part.sections
                        .filter((section) => section.title !== "开篇")
                        .map(
                          (section) => `
                            <button class="toc-section" type="button" data-scroll="${esc(
                              section.id
                            )}">${esc(section.title)}</button>`
                        )
                        .join("")}
                    </div>
                  </div>`
            )
            .join("")
          : "";
      return `
          <div class="toc-chapter">
            <button class="toc-chapter-btn ${active ? "active" : ""}" type="button"
              data-chapter="${chapter.id}" ${ready ? "" : "disabled"}>
              <span class="n">${window.STORY.store.chapterNumber(chapter)}</span>
              <span class="t">${esc(chapter.title)}</span>
              ${ready ? "" : '<span class="pending">待续</span>'}
            </button>
            ${parts ? `<div class="toc-parts">${parts}</div>` : ""}
          </div>`;
    };

    const volumes = window.STORY.data.volumes || [];
    if (!volumes.length) return chapters.map(chapterItem).join("");

    const groups = [];
    for (const chapter of chapters) {
      const volume = window.STORY.store.volumeOf(chapter);
      const key = volume ? String(volume.id) : "";
      let group = groups.find((item) => item.key === key);
      if (!group) {
        group = { key, volume, chapters: [] };
        groups.push(group);
      }
      group.chapters.push(chapter);
    }
    return groups
      .map((group) => {
        const body = group.chapters.map(chapterItem).join("");
        if (!group.volume) return body;
        return `
          <div class="toc-volume">
            <button class="toc-volume-btn" type="button"
              data-volume-toggle="${esc(group.volume.id)}" aria-expanded="true">
              <span class="v-label">${esc(group.volume.title)}</span>
              <span class="v-count">${group.chapters.length} 章</span>
            </button>
            <div class="toc-volume-body">${body}</div>
          </div>`;
      })
      .join("");
  }

  function renderCast(meta, chapterOrder) {
    if (!meta || !meta.cast) return "";
    const chips = meta.cast
      .map((id) => window.STORY.data.entityById.get(id))
      .filter((entity) => entity && window.STORY.store.isVisible(entity, chapterOrder))
      .map(
        (entity) => `
          <button class="cast-chip" type="button" data-ent="${esc(entity.id)}">
            <span class="dot" style="--entity-color:${esc(entity.color || "var(--accent)")}">${esc(
          entity.icon || entity.name.slice(0, 1)
        )}</span>
            <span>${esc(entity.name)}</span>
          </button>`
      )
      .join("");
    return chips ? `<div class="cast-strip" aria-label="本章登场">${chips}</div>` : "";
  }

  function renderBlocks(blocks) {
    return blocks
      .map((block) => {
        if (block.type === "note") return `<div class="note">${block.html}</div>`;
        if (block.type === "source") return `<p class="source-note">${block.html}</p>`;
        if (block.type === "quote") return `<blockquote>${block.html}</blockquote>`;
        if (block.type === "ul") {
          return `<ul>${block.items.map((item) => `<li>${item}</li>`).join("")}</ul>`;
        }
        if (block.type === "image") {
          const imageSrc =
            (window.STORY_IMAGES && window.STORY_IMAGES[block.src]) || block.src;
          const attrs = [
            `src="${esc(imageSrc)}"`,
            `alt="${esc(block.alt == null ? "" : block.alt)}"`,
            'loading="lazy"',
          ];
          if (block.width != null && block.width !== "") {
            attrs.push(`width="${esc(block.width)}"`);
          }
          if (block.height != null && block.height !== "") {
            attrs.push(`height="${esc(block.height)}"`);
          }
          const caption = block.caption
            ? `<span class="fig-cap">${esc(block.caption)}</span>`
            : "";
          const creditText = [block.credit, block.license]
            .filter((item) => item)
            .map((item) => esc(item))
            .join(" · ");
          let credit = creditText
            ? `<span class="fig-credit">${creditText}</span>`
            : "";
          if (block.sourceUrl && credit) {
            credit = `<span class="fig-credit"><a href="${esc(
              block.sourceUrl
            )}" target="_blank" rel="noopener noreferrer">${creditText}</a></span>`;
          }
          const figcaption =
            caption || credit ? `<figcaption>${caption}${credit}</figcaption>` : "";
          return `<figure class="prose-figure"><img ${attrs.join(
            " "
          )}>${figcaption}</figure>`;
        }
        return `<p>${block.html}</p>`;
      })
      .join("");
  }

  function renderArticle(chapter, meta, mode) {
    const activeMode = mode || window.STORY.store.resolveMode(chapter);
    const variant = variantFor(chapter, activeMode);
    const partsSource = Array.isArray(variant.parts) ? variant.parts : [];
    const accent = chapterAccent(chapter);
    const hanzi = Number(variant.hanzi || 0);
    const chars = Number(variant.chars || 0) || hanzi;
    const units = hanzi || chars;
    const modeNames = window.STORY.store.modeNamesOf(chapter);
    const volume = window.STORY.store.volumeOf(chapter);
    const readingMinutes =
      modeNames.length > 1
        ? Math.max(1, Math.round(units / (hanzi ? 400 : 1000)))
        : (meta && meta.readingMinutes) ||
          Math.max(1, Math.round(units / (hanzi ? 400 : 1000)));
    const title = variant.title || chapter.title || "";
    const subtitle = variant.subtitle || chapter.subtitle || "";
    const modeCounts =
      modeNames.length > 1
        ? `<span>${modeNames
            .map((name) => {
              const amount =
                Number((chapter.hanziByMode || {})[name] || 0) ||
                Number((chapter.charsByMode || {})[name] || 0);
              return `${esc(modeLabel(name))} ${amount.toLocaleString(
                "zh-CN"
              )} 字`;
            })
            .join(" / ")}</span>`
        : "";
    let partNumber = 0;
    const parts = partsSource
      .map((part, partIndex) => {
        const isIntro = part.title === "开篇";
        if (!isIntro) partNumber += 1;
        const sectionBlocks = (part.sections || [])
          .map((section) => {
            const isSectionIntro = section.title === "开篇";
            const index = sectionIndexLabel(part, section);
            const heading = isSectionIntro
              ? ""
              : `<div class="section-heading">
                   <span class="s-idx">${index ? `${index} / ` : ""}SEC</span>
                   <h3>${esc(section.title)}</h3>
                 </div>`;
            return `<section class="section-block prose" id="${esc(section.id)}">
                ${heading}
                ${renderBlocks(section.blocks)}
              </section>`;
          })
          .join("");
        const head = isIntro
          ? ""
          : `<div class="part-head">
               <span class="p-idx">PART ${String(partNumber).padStart(2, "0")}</span>
               <div>
                 <h2>${esc(part.title)}</h2>
                 ${part.subtitle ? `<p class="part-sub">${esc(part.subtitle)}</p>` : ""}
               </div>
             </div>`;
        return `<div class="part-block ${isIntro ? "part-intro" : ""}">${head}${sectionBlocks}</div>`;
      })
      .join("");

    const takeaways = meta && meta.takeaways
      ? `<div class="chapter-end">
           <h2>带走这几件事</h2>
           <ol class="takeaways">
             ${meta.takeaways.map((item) => `<li>${esc(item)}</li>`).join("")}
           </ol>
           ${
             meta.newTerms && meta.newTerms.length
               ? `<div class="dossier-section-title">本章新词</div>
                  <div class="term-list">
                    ${meta.newTerms
                      .map((id) => window.STORY.data.entityById.get(id))
                      .filter(Boolean)
                      .map(
                        (entity) =>
                          `<button class="term-chip" type="button" data-ent="${esc(
                            entity.id
                          )}">${esc(entity.name)}</button>`
                      )
                      .join("")}
                  </div>`
               : ""
           }
         </div>`
      : "";

    const sources = variant.sources && variant.sources.length
      ? `<details class="sources">
           <summary>来源与延伸 · ${variant.sources.length}</summary>
           <ul>
             ${variant.sources
               .map(
                 (source) =>
                   `<li><a href="${esc(source.url)}" target="_blank" rel="noopener noreferrer">${esc(
                     source.label
                   )}</a></li>`
               )
               .join("")}
           </ul>
         </details>`
      : "";

    const ready = window.STORY.store.state.ready;
    const ordered = window.STORY.data.chapters
      .slice()
      .sort((a, b) => Number(a.order) - Number(b.order));
    const currentIndex = ordered.findIndex((item) => String(item.id) === String(chapter.id));
    const prev = currentIndex > 0 ? ordered[currentIndex - 1] : null;
    const next = currentIndex >= 0 ? ordered[currentIndex + 1] : null;
    const nav = `<div class="reader-footer-nav">
        ${
          prev
            ? `<button class="btn ghost" type="button" data-chapter="${prev.id}">← 第 ${window.STORY.store.chapterNumber(
                prev
              )} 章 · ${esc(prev.title)}</button>`
            : `<span></span>`
        }
        ${
          next && ready.has(String(next.id))
            ? `<button class="btn" type="button" data-chapter="${next.id}">第 ${window.STORY.store.chapterNumber(
                next
              )} 章 · ${esc(next.title)} →</button>`
            : `<button class="btn ghost" type="button" disabled>下一章 · 待续</button>`
        }
      </div>`;

    return `
      <article class="article">
        <div class="article-inner" style="--chapter-accent:${accent};--chapter-soft:${accent}22">
          <header class="chapter-cover">
            <span class="cover-num" aria-hidden="true">${window.STORY.store.chapterNumber(
              chapter
            )}</span>
            <div class="cover-kicker">
              <span class="line"></span>
              <span class="code">CHAPTER ${window.STORY.store.chapterNumber(chapter)} · ${
      esc(meta && meta.codename ? meta.codename : "")
    }</span>
            </div>
            <h1 class="cover-title">${esc(title)}</h1>
            <p class="cover-subtitle">${esc(subtitle)}</p>
            <p class="cover-hook">${
              esc(meta && meta.hook ? meta.hook : subtitle)
            }</p>
            ${
              meta && meta.epigraph
                ? `<p class="cover-epigraph">${esc(meta.epigraph)}</p>`
                : ""
            }
            <div class="cover-meta">
              ${volume ? `<span>${esc(volume.title)}</span>` : ""}
              <span>${esc(modeLabel(activeMode))}</span>
              <span>约 ${readingMinutes} 分钟</span>
              <span>${(hanzi || chars).toLocaleString("zh-CN")} ${
                hanzi ? "字" : "字符"
              }</span>
              ${modeCounts}
              <span>${partsSource.filter((part) => part.title !== "开篇").length} 部</span>
              <span>点击人名 / 术语查看档案</span>
            </div>
            ${renderCast(meta, chapter.order)}
          </header>
          ${parts}
          ${takeaways}
          ${sources}
          ${nav}
        </div>
      </article>`;
  }

  function renderModeToggle(chapter, mode) {
    const toggle = document.getElementById("mode-toggle");
    if (!toggle) return;
    const names = window.STORY.store.modeNamesOf(chapter);
    if (names.length <= 1) {
      toggle.innerHTML = "";
      toggle.hidden = true;
      return;
    }
    toggle.innerHTML = names
      .map((name) => {
        const active = name === mode;
        return `<button class="mode-btn ${active ? "active" : ""}" type="button"
          data-mode="${esc(name)}" aria-pressed="${active ? "true" : "false"}">${esc(
          modeLabel(name)
        )}</button>`;
      })
      .join("");
    toggle.hidden = false;
  }

  function firstVisibleSectionId() {
    const sections = Array.from(document.querySelectorAll(".section-block[id]"));
    if (!sections.length) return null;
    const topbar =
      parseFloat(
        window.getComputedStyle(document.documentElement).getPropertyValue("--topbar-h")
      ) || 0;
    const visible = sections.find(
      (section) => section.getBoundingClientRect().bottom > topbar + 8
    );
    return (visible || sections[0]).id;
  }

  function setMode(mode) {
    const store = window.STORY.store;
    const chapter = window.STORY.data.chapterById.get(
      String(store.state.chapterId || currentChapterId || "")
    );
    if (!chapter || !store.modeNamesOf(chapter).includes(mode)) return;
    const sectionId = store.state.sectionId || firstVisibleSectionId();
    store.setMode(mode);
    render(chapter.id);
    if (!sectionId || !document.getElementById(sectionId)) return;
    window.setTimeout(() => {
      const target = document.getElementById(sectionId);
      if (target) target.scrollIntoView({ behavior: "auto", block: "start" });
    }, 120);
  }

  function resolveEvidence(ev) {
    if (!ev || !ev.section) return ev;
    if (document.getElementById(ev.section)) return ev;
    const chapter = window.STORY.data.chapterById.get(
      String(window.STORY.store.state.chapterId || currentChapterId || "")
    );
    if (!chapter) return ev;
    const base = window.STORY.data.sectionById.get(`${chapter.id}:${ev.section}`);
    const title = base && base.section ? base.section.title : "";
    if (!title) return ev;
    const variant = variantFor(chapter, window.STORY.store.resolveMode(chapter));
    for (const part of variant.parts || []) {
      for (const section of part.sections || []) {
        if (section.title === title) {
          return Object.assign({}, ev, { section: section.id });
        }
      }
    }
    return ev;
  }

  function bindToc() {
    document.querySelectorAll(".toc [data-scroll]").forEach((button) => {
      button.addEventListener("click", () => {
        const target = document.getElementById(button.dataset.scroll);
        if (!target) return;
        document.querySelector(".toc").classList.remove("open");
        target.scrollIntoView({ behavior: "smooth", block: "start" });
      });
    });

    document.querySelectorAll(".toc [data-chapter]").forEach((button) => {
      if (button.disabled) return;
      button.addEventListener("click", () => {
        window.location.hash = `#/read/${button.dataset.chapter}`;
      });
    });

    document.querySelectorAll(".toc [data-volume-toggle]").forEach((button) => {
      button.addEventListener("click", () => {
        const body = button.nextElementSibling;
        if (!body) return;
        const collapsed = body.classList.toggle("collapsed");
        button.setAttribute("aria-expanded", collapsed ? "false" : "true");
      });
    });
  }

  function bindEntityLinks() {
    const tooltip = document.getElementById("tooltip");

    document.querySelectorAll(".article [data-ent]").forEach((link) => {
      link.addEventListener("click", (event) => {
        event.preventDefault();
        window.STORY.dossier.open(link.dataset.ent);
      });

      link.addEventListener("mouseenter", (event) => {
        const entity = window.STORY.data.entityById.get(link.dataset.ent);
        if (!entity || !tooltip) return;
        if (!window.STORY.store.isVisible(entity)) {
          tooltip.innerHTML = `<span class="tt-name">？？？</span><span class="tt-tag">防剧透已开启</span>`;
        } else {
          tooltip.innerHTML = `<span class="tt-name">${esc(entity.name)} · ${esc(
            window.STORY.util.typeLabel(entity.type)
          )}</span><span class="tt-tag">${esc(entity.tagline || "")}</span>`;
        }
        tooltip.hidden = false;
        positionTooltip(event, tooltip);
      });

      link.addEventListener("mousemove", (event) => {
        if (tooltip && !tooltip.hidden) positionTooltip(event, tooltip);
      });

      link.addEventListener("mouseleave", () => {
        if (tooltip) tooltip.hidden = true;
      });
    });

    document.querySelectorAll(".article [data-chapter]").forEach((button) => {
      if (button.disabled) return;
      button.addEventListener("click", () => {
        window.location.hash = `#/read/${button.dataset.chapter}`;
      });
    });
  }

  function positionTooltip(event, tooltip) {
    const gap = 14;
    const x = Math.min(window.innerWidth - 150, Math.max(150, event.clientX));
    const y = Math.max(70, event.clientY - gap);
    tooltip.style.left = `${x}px`;
    tooltip.style.top = `${y}px`;
  }

  function bindProgress(chapter) {
    const progressBar = document.getElementById("progress-bar");
    const update = () => {
      if (progressBar) {
        const max = document.documentElement.scrollHeight - window.innerHeight;
        const ratio = max > 0 ? Math.min(1, Math.max(0, window.scrollY / max)) : 0;
        progressBar.style.width = `${ratio * 100}%`;
      }
    };
    update();
    scrollHandler = update;
    window.addEventListener("scroll", update, { passive: true });
  }

  function bindSectionObserver(chapter) {
    if (observer) observer.disconnect();
    const sections = Array.from(document.querySelectorAll(".section-block[id]"));
    if (!sections.length) return;

    const tocLinks = new Map(
      Array.from(document.querySelectorAll(".toc-section[data-scroll]")).map((button) => [
        button.dataset.scroll,
        button,
      ])
    );

    observer = new IntersectionObserver(
      (entries) => {
        const visible = entries
          .filter((entry) => entry.isIntersecting)
          .sort((a, b) => b.intersectionRatio - a.intersectionRatio)[0];
        if (!visible) return;
        const id = visible.target.id;
        tocLinks.forEach((button, sectionId) => {
          button.classList.toggle("active", sectionId === id);
        });
        window.STORY.store.state.sectionId = id;
        window.clearTimeout(saveTimer);
        saveTimer = window.setTimeout(() => {
          window.STORY.store.savePosition(chapter.id, id, chapter.order);
        }, 450);
      },
      { rootMargin: "-18% 0px -68% 0px", threshold: [0, 0.2, 0.6] }
    );

    sections.forEach((section) => observer.observe(section));
  }

  function restorePosition(chapter) {
    const pendingSection = window.STORY._pendingSection;
    if (
      pendingSection &&
      String(pendingSection.chapter) === String(chapter.id)
    ) {
      window.STORY._pendingSection = null;
      const target = document.getElementById(pendingSection.section);
      if (target) {
        window.setTimeout(() => {
          target.scrollIntoView({ behavior: "auto", block: "start" });
        }, 100);
      }
      return;
    }
    const pending = window.STORY._pendingEvidence;
    if (pending && String(pending.chapter) === String(chapter.id)) {
      window.STORY._pendingEvidence = null;
      window.STORY.dossier.scrollToEvidence(resolveEvidence(pending));
      return;
    }
    const position = window.STORY.store.getPosition();
    if (
      !position ||
      String(position.chapterId) !== String(chapter.id) ||
      !position.sectionId
    ) {
      return;
    }
    const target = document.getElementById(position.sectionId);
    if (!target) return;
    window.setTimeout(() => {
      target.scrollIntoView({ behavior: "auto", block: "start" });
    }, 80);
  }

  function scrollToSection(chapterId, sectionId) {
    if (!chapterId || !sectionId) return;
    if (String(currentChapterId) === String(chapterId)) {
      const target = document.getElementById(sectionId);
      if (target) {
        target.scrollIntoView({ behavior: "smooth", block: "start" });
      }
      return;
    }
    window.STORY._pendingSection = {
      chapter: String(chapterId),
      section: String(sectionId),
    };
    window.location.hash = `#/read/${chapterId}`;
  }

  function render(chapterId) {
    destroy();
    const chapter =
      window.STORY.data.chapterById.get(String(chapterId)) ||
      window.STORY.data.firstChapter;
    if (!chapter) return;
    currentChapterId = chapter.id;
    window.STORY.store.state.chapterId = String(chapter.id);
    window.STORY.store.state.chapterOrder = Number(chapter.order || 1);
    window.STORY.store.state.route = "reader";
    const meta = window.STORY.store.chapterMeta(chapter.id);
    const mode = window.STORY.store.resolveMode(chapter);

    const view = document.getElementById("view");
    view.innerHTML = `
      <button class="toc-mobile-toggle" type="button" aria-expanded="false">目录</button>
      <div class="reader-layout">
        <aside class="toc" aria-label="章节目录">
          <div class="toc-head"><h2>章节目录</h2><span class="mono">${esc(
            window.STORY.store.chapterRange()
          )}</span></div>
          ${renderToc(chapter)}
          <div class="toc-foot">
            点击正文中带虚线的名称，打开人物 / 术语档案。<br>
            星图中可查看完整关系网。
          </div>
        </aside>
        ${renderArticle(chapter, meta, mode)}
      </div>`;

    renderModeToggle(chapter, mode);
    bindToc();
    bindEntityLinks();
    bindProgress(chapter);
    bindSectionObserver(chapter);
    bindMobileToc();
    restorePosition(chapter);
    view.focus({ preventScroll: true });
  }

  function bindMobileToc() {
    const toggle = document.querySelector(".toc-mobile-toggle");
    const toc = document.querySelector(".toc");
    if (!toggle || !toc) return;
    toggle.addEventListener("click", () => {
      const open = toc.classList.toggle("open");
      toggle.setAttribute("aria-expanded", open ? "true" : "false");
    });
    document.addEventListener(
      "click",
      (event) => {
        if (!toc.classList.contains("open")) return;
        if (toc.contains(event.target) || toggle.contains(event.target)) return;
        toc.classList.remove("open");
        toggle.setAttribute("aria-expanded", "false");
      },
      { capture: true }
    );
  }

  function destroy() {
    if (observer) {
      observer.disconnect();
      observer = null;
    }
    if (scrollHandler) {
      window.removeEventListener("scroll", scrollHandler);
      scrollHandler = null;
    }
    window.clearTimeout(saveTimer);
  }

  window.STORY.reader = {
    render,
    destroy,
    setMode,
    scrollToSection,
    scrollToEvidence(ev) {
      window.STORY.dossier.scrollToEvidence(resolveEvidence(ev));
    },
    get currentChapterId() {
      return currentChapterId;
    },
  };
})();
