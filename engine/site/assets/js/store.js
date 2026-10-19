/* ============================================================
   STORY Archive — data index, state, utilities
   ============================================================ */

window.STORY = window.STORY || {};

(function () {
  "use strict";

  const chapters = window.STORY_CHAPTERS || [];
  const entityData = window.STORY_ENTITIES || { entities: [], relations: [] };
  const meta = window.STORY_META || {};
  const recap = window.STORY_RECAP || { eras: [] };
  const worldview = window.STORY_WORLDVIEW || { cards: [] };
  const timeline = window.STORY_TIMELINE || { events: [] };
  const mentions = window.STORY_MENTIONS || {};
  const config = window.STORY_CONFIG || {};

  const volumes = Array.isArray(config.volumes) ? config.volumes : [];
  const volumeById = new Map(volumes.map((volume) => [String(volume.id), volume]));

  const entityById = new Map(entityData.entities.map((e) => [e.id, e]));
  const chapterById = new Map(chapters.map((c) => [String(c.id), c]));
  const chapterByOrder = new Map(chapters.map((c) => [Number(c.order), c]));
  const relationByEntity = new Map();
  const relationKey = (a, b) => [a, b].sort().join("::");

  for (const relation of entityData.relations) {
    for (const id of [relation.from, relation.to]) {
      if (!relationByEntity.has(id)) relationByEntity.set(id, []);
      relationByEntity.get(id).push(relation);
    }
  }

  function modeNamesOf(chapter) {
    if (!chapter) return ["original"];
    if (Array.isArray(chapter.modeNames) && chapter.modeNames.length) {
      return chapter.modeNames.slice();
    }
    return [chapter.defaultMode || "original"];
  }

  function variantOf(chapter, mode) {
    if (!chapter) return null;
    const wanted = mode || chapter.defaultMode;
    if (chapter.variants && chapter.variants[wanted]) {
      return chapter.variants[wanted];
    }
    if (chapter.parts && modeNamesOf(chapter).includes(wanted)) {
      return chapter;
    }
    return null;
  }

  const sectionById = new Map();
  for (const chapter of chapters) {
    const names = modeNamesOf(chapter);
    const defaultMode = chapter.defaultMode || names[0];
    const orderedModes = [defaultMode].concat(
      names.filter((name) => name !== defaultMode)
    );
    for (const mode of orderedModes) {
      const variant = variantOf(chapter, mode);
      if (!variant || !Array.isArray(variant.parts)) continue;
      for (const part of variant.parts) {
        for (const section of part.sections || []) {
          const entry = { chapter, part, section, mode };
          sectionById.set(`${chapter.id}:${mode}:${section.id}`, entry);
          const plainKey = `${chapter.id}:${section.id}`;
          if (!sectionById.has(plainKey)) sectionById.set(plainKey, entry);
        }
      }
    }
  }

  const STORAGE = {
    theme: "story-theme",
    font: "story-font",
    spoiler: "story-spoiler",
    mode: "story-mode",
    pos: "story-pos",
  };

  function read(key, fallback) {
    try {
      const value = window.localStorage.getItem(key);
      return value === null ? fallback : value;
    } catch (error) {
      return fallback;
    }
  }

  function write(key, value) {
    try {
      window.localStorage.setItem(key, value);
    } catch (error) {
      /* file:// or private mode: reading still works, persistence is optional */
    }
  }

  const defaultChapter = chapters[0] || null;
  const readyIds =
    config.ready && config.ready.length
      ? config.ready.map(String)
      : chapters.map((chapter) => String(chapter.id));
  const firstChapterId =
    config.firstChapterId != null
      ? String(config.firstChapterId)
      : readyIds[0] || (defaultChapter ? String(defaultChapter.id) : null);
  const firstChapter =
    chapterById.get(firstChapterId) || defaultChapter || null;

  const state = {
    theme: read(STORAGE.theme, "dark"),
    font: parseInt(read(STORAGE.font, "19"), 10) || 19,
    spoiler: read(STORAGE.spoiler, "on") !== "off",
    mode: read(STORAGE.mode, ""),
    chapterId: firstChapterId,
    chapterOrder: firstChapter ? Number(firstChapter.order || 1) : 1,
    sectionId: null,
    ready: new Set(readyIds),
    route: "home",
  };

  function resolveMode(chapter) {
    const names = modeNamesOf(chapter);
    if (names.includes(state.mode)) return state.mode;
    if (chapter && names.includes(chapter.defaultMode)) return chapter.defaultMode;
    return names[0];
  }

  function setMode(mode) {
    state.mode = mode || "";
    write(STORAGE.mode, state.mode);
  }

  function applyTheme(theme) {
    state.theme = theme === "light" ? "light" : "dark";
    document.documentElement.dataset.theme = state.theme;
    write(STORAGE.theme, state.theme);
  }

  function toggleTheme() {
    applyTheme(state.theme === "dark" ? "light" : "dark");
  }

  const FONT_STEPS = [17, 19, 21, 23];

  function applyFont(size) {
    state.font = FONT_STEPS.includes(size) ? size : 19;
    document.documentElement.style.setProperty("--reader-size", `${state.font}px`);
    write(STORAGE.font, String(state.font));
  }

  function cycleFont() {
    const index = FONT_STEPS.indexOf(state.font);
    applyFont(FONT_STEPS[(index + 1) % FONT_STEPS.length]);
  }

  function setSpoiler(on) {
    state.spoiler = Boolean(on);
    write(STORAGE.spoiler, state.spoiler ? "on" : "off");
  }

  function isVisible(entity, chapterOrder) {
    if (!entity) return false;
    if (!state.spoiler) return true;
    const threshold = Number(entity.spoilerFrom);
    if (!Number.isFinite(threshold)) return true;
    return threshold <= (chapterOrder || state.chapterOrder || 1);
  }

  function savePosition(chapterId, sectionId, order) {
    if (chapterId == null) return;
    write(
      STORAGE.pos,
      JSON.stringify({
        chapterId: String(chapterId),
        order: Number(order || state.chapterOrder || 1),
        sectionId: sectionId || null,
      })
    );
  }

  function getPosition() {
    try {
      return JSON.parse(read(STORAGE.pos, "null"));
    } catch (error) {
      return null;
    }
  }

  const TYPE_LABELS = {
    character: "人物",
    faction: "势力",
    location: "地点",
    term: "术语",
    event: "事件",
  };

  const TYPE_ORDER = ["character", "faction", "location", "term", "event"];

  const TYPE_COLORS = {
    character: "#e23a4e",
    faction: "#c9a227",
    location: "#7fd6d6",
    term: "#8a93a0",
    event: "#d98c5f",
  };

  const KIND_LABELS = {
    ally: "盟友",
    hostile: "敌对",
    family: "亲属",
    mentor: "师徒",
    contract: "契约",
    unknown: "未知",
  };

  const KIND_COLORS = {
    ally: "var(--accent-2)",
    hostile: "var(--accent)",
    family: "var(--gold)",
    contract: "var(--text-faint)",
    unknown: "var(--text-faint)",
  };

  function esc(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function typeLabel(type) {
    return TYPE_LABELS[type] || type || "";
  }

  function kindLabel(kind) {
    return KIND_LABELS[kind] || kind || "";
  }

  function kindColor(kind) {
    return KIND_COLORS[kind] || KIND_COLORS.unknown;
  }

  function relationsOf(entityId, chapterOrder) {
    const list = relationByEntity.get(entityId) || [];
    const order = chapterOrder || state.chapterOrder || 1;
    return list.filter((relation) => {
      const otherId = relation.from === entityId ? relation.to : relation.from;
      const other = entityById.get(otherId);
      if (!other) return false;
      if (state.spoiler && Number(relation.spoilerFrom) > order) {
        return false;
      }
      return isVisible(other, order);
    });
  }

  function otherOf(relation, entityId) {
    const otherId = relation.from === entityId ? relation.to : relation.from;
    return entityById.get(otherId);
  }

  function chapterMeta(chapterId) {
    return meta[String(chapterId)] || null;
  }

  function chapterNumber(chapter) {
    if (!chapter) return "";
    const number = chapter.displayNumber != null ? chapter.displayNumber : chapter.order;
    return String(number).padStart(2, "0");
  }

  function chapterOrderOf(chapterId) {
    const chapter = chapterById.get(String(chapterId));
    return chapter ? Number(chapter.order || 1) : 1;
  }

  function chapterRange() {
    if (!chapters.length) return "";
    const orders = chapters.map((chapter) => Number(chapter.order)).filter(Number.isFinite);
    if (!orders.length) return "";
    const first = Math.min(...orders);
    const last = Math.max(...orders);
    return first === last ? `${first}` : `${first}—${last}`;
  }

  function entityRelationsCount(entityId) {
    return (relationByEntity.get(entityId) || []).length;
  }

  function volumeOf(chapter) {
    if (!chapter) return null;
    const id = chapter.volume != null ? String(chapter.volume) : "";
    if (id && volumeById.has(id)) return volumeById.get(id);
    return (
      volumes.find((volume) =>
        (volume.chapters || []).some(
          (chapterId) => String(chapterId) === String(chapter.id)
        )
      ) || null
    );
  }

  function mentionsOf(entityId, chapterOrder) {
    const list = mentions[entityId] || [];
    const order = Number(chapterOrder || state.chapterOrder || 1);
    return list.filter(
      (item) => !state.spoiler || Number(item.chapterOrder) <= order
    );
  }

  function toast(message, duration) {
    const node = document.getElementById("toast");
    if (!node) return;
    node.textContent = message;
    node.hidden = false;
    window.clearTimeout(toast._timer);
    toast._timer = window.setTimeout(() => {
      node.hidden = true;
    }, duration || 2200);
  }

  window.STORY.data = {
    config,
    chapters,
    entities: entityData.entities,
    relations: entityData.relations,
    meta,
    recap,
    worldview,
    timeline,
    mentions,
    volumes,
    volumeById,
    entityById,
    chapterById,
    chapterByOrder,
    sectionById,
    relationByEntity,
    relationKey,
    firstChapter,
    typeOrder: TYPE_ORDER,
    typeColors: TYPE_COLORS,
  };

  window.STORY.store = {
    state,
    config,
    firstChapter,
    modeNamesOf,
    variantOf,
    resolveMode,
    setMode,
    applyTheme,
    toggleTheme,
    applyFont,
    cycleFont,
    setSpoiler,
    isVisible,
    savePosition,
    getPosition,
    relationsOf,
    otherOf,
    chapterMeta,
    chapterNumber,
    chapterOrderOf,
    chapterRange,
    entityRelationsCount,
    volumeOf,
    mentionsOf,
    toast,
  };

  window.STORY.util = {
    esc,
    typeLabel,
    kindLabel,
    kindColor,
  };
})();
