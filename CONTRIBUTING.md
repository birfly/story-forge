# Contributing

Thanks for taking a look at Story Forge.

## Scope

Story Forge is a Claude Code plugin. The core is a Python engine that parses
Markdown into a static reading site; the skills and commands describe the
authoring workflow for Claude. Other hosts are not supported yet.

## Development

Requirements: Python 3.11+ (3.13 is the primary target). No mandatory
third-party packages. `pypdf` is optional and only needed for PDF ingestion.

```bash
# Run the full test suite
python -m unittest discover -s engine/tests -p "test_*.py" -v

# Lint
python -m ruff check engine/tools scripts/story.py

# Build the bundled example
python scripts/story.py build examples/mini-story --single
python scripts/story.py verify examples/mini-story
```

## Project layout

- `engine/tools/` — Python engine (parser, ingest, build, verify, audit, style).
- `engine/site/` — reader template (HTML/CSS/JS). Generated site output is not
  committed.
- `engine/content/` — schema and empty content templates.
- `skills/`, `commands/` — Claude Code workflows.
- `examples/mini-story/` — a small source project. `site/`, `dist/` and
  `build/` are generated and ignored.

## Rules

- Keep the source text byte-faithful: only structure normalization is allowed.
- Do not commit generated output, caches, personal stories or local paths.
- Add tests for new CLI behavior, especially failure exit codes.
- Keep the reading site offline: no CDN, external fonts, `fetch`, ES modules
  or web workers in built output.
- Do not commit credentials, API keys or private source texts.

## Pull requests

Describe the user-visible change, list the commands you ran, and include the
test results. For reader changes, include a screenshot or a short recording.
