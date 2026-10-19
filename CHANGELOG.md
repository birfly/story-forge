# Changelog

All notable changes to Story Forge are documented here. This project follows
[Semantic Versioning](https://semver.org/).

## [1.2.0-preview.2] — 2026-10-19

### Added

- **Search-first gate for missing sources**: `source-check` now returns a
  structured `searchPlan` (priority sources, query templates, sources to avoid)
  and a state machine: `search_original` → `import_source` / `request_source`.
- **Search attempt recording**: `source-check --record-search --outcome …`
  writes every search attempt, query, candidate and note to
  `content/source_provenance.json` (`searchAttempts`).
- `source-check` refuses to move to “ask the user for a file” until at least
  one search attempt is recorded. Skills, commands, `status` and README now
  enforce the same order.
- New resource file `engine/source_sources.json` with official, public-domain,
  open-license, user-provided and reference source priorities.
- 8 additional tests for the search-first state machine.

### Changed

- `source-check` output adds `searchPlan`, `author`, `searchAttempts` and
  `lastSearchOutcome`; new states `import_source`, `request_source`,
  `reference_ready`.
- `project_status` next actions surface search recording and fallback-to-user
  steps.

## [1.2.0-preview.1] — 2026-10-19

Preview release. Focus: real input, long-project workflow, verifiable quality.

### Added

- **Source ingestion (`story.py ingest`)**: txt / md / epub / docx / html, with
  optional `pypdf` support for PDF. Encoding detection, chapter detection,
  repeated header/footer and page-number cleanup, `build/ingest_report.json`,
  conflict protection and `--update-project`.
- **Project status (`story.py status`)**: chapter × variant matrix, fidelity,
  stale detection, metadata/illustration coverage, deterministic next actions,
  and `build/status.json`.
- **Content audit (`story.py audit`)**: evidence checks, spoiler leaks,
  relations, chapter metadata, variant alignment, illustrations, volumes,
  timeline cycles, unlinked-name candidates, annotation coverage.
- **Quantitative style metrics (`story.py style`)**: sentence length, dialogue
  ratio, punctuation, person, long-sentence ratio, baseline drift for retold
  variants and authored metadata.
- **Source acquisition (`story.py source-check` + `story-source` skill)**:
  when required source text is missing, suggests WebSearch queries, records
  provenance in `content/source_provenance.json`, and fails `parse` with
  actionable guidance.
- **Arbitrary variants** (`variants` / `variantFiles`): translation, abridged
  and annotated variants alongside original/retold.
- **Volumes** (`volumes`): grouped TOC, home chapter strip and chapter cover.
- **Event timeline** (`content/timeline.json`, `#/timeline`): story time,
  participants, causes/consequences, evidence, spoiler-gated progress slider.
- **Glossary** (`#/glossary`): searchable term index with appearance/name sort.
- **Entity mention index** (`site/data/mentions.js`): “出现位置” in the dossier
  with direct jumps to sections.
- **Graph path finding**: shortest visible path between two entities.
- **CLI exit codes**: every subcommand now propagates tool failures to the
  caller, so CI and agents can detect errors.
- **CLI integration tests** for all three templates and failure paths.
- **Open-source release files**: LICENSE, CHANGELOG, CONTRIBUTING, CI workflow.

### Changed

- Fidelity normalization now keeps Latin letters and digits, so translation
  variants are checked as well as Chinese text.
- `retoldFiles` is now an alias for `variantFiles.retold`; existing projects
  continue to work without changes.
- `evidence` and `manual_links` may omit `section` when the quote is unique
  within the chapter.

## [1.1.0] — 2026-10

- Import / retelling / creation project templates.
- Rich reader: dossiers, relationship graph, recap, worldview cards, evidence
  jumps, anti-spoiler, original/retold switching.
- Illustration manifest, open-license fetching, placement and single-file
  inlining.
- Fidelity validation, offline scan and style lint.
