# Agent Skill Board

A tiny local dashboard for managing Agent Skills across tools such as Claude Code, Codex, and Hermes.

Agent Skill Board scans a folder of `SKILL.md` files, shows them as searchable cards, detects likely host compatibility, surfaces health and usage metadata, and lets you tag skills without introducing a database or frontend build step.

It is a single Python standard-library app.

## Features

- Recursively scans `SKILL.md` files.
- Skips common noise folders such as `.git`, `node_modules`, caches, and archives.
- Shows name, description, version, relative path, host badges, health badges, usage counts, and tags.
- Detects likely compatibility with Hermes, Claude Code, Codex, or generic skill usage.
- Reads optional sidecar files:
  - `.skill-tags.json`
  - `.skill-desc-zh.json`
  - `.usage.json`
- Supports local-only open actions for files and directories inside the configured skills folder.
- Exposes small JSON APIs for local automation.
- Requires no third-party Python packages.

## Quick Start

```bash
git clone https://github.com/Sukerr/agent-skill-board.git
cd agent-skill-board
python3 skill_board.py
```

Open:

```text
http://127.0.0.1:8777/
```

By default the app scans:

```text
~/ai-workspace/shared-skills
```

You can override paths and port with environment variables:

```bash
SKILL_BOARD_SKILLS_DIR="$HOME/.agents/skills" \
SKILL_BOARD_PORT=8788 \
python3 skill_board.py
```

Optional variables:

| Variable | Default |
| --- | --- |
| `SKILL_BOARD_SKILLS_DIR` | `~/ai-workspace/shared-skills` |
| `SKILL_BOARD_ICLOUD_DIR` | `~/Library/Mobile Documents/com~apple~CloudDocs/ai-skills` |
| `SKILL_BOARD_HOST` | `127.0.0.1` |
| `SKILL_BOARD_PORT` | `8777` |

## Sidecar Files

Agent Skill Board works without sidecar files. If present, it uses:

```text
.skill-tags.json
.skill-desc-zh.json
.usage.json
```

Tags are written back to `.skill-tags.json` when edited in the UI.

The app only opens files/directories inside `SKILL_BOARD_SKILLS_DIR`. It does not delete, archive, publish, or sync skills from the web UI.

## API

```text
GET  /
GET  /api/skills
GET  /api/status
POST /api/tags
POST /api/open
```

`POST /api/tags`:

```json
{
  "skill": "demo-skill",
  "tags": ["example", "workflow"]
}
```

`POST /api/open`:

```json
{
  "kind": "file",
  "path": "/absolute/path/inside/skills/SKILL.md"
}
```

## Example Skill

See `examples/skills/demo-skill/SKILL.md`.

## Sync Templates

The `scripts/` folder contains optional templates for syncing a skills folder to another local folder or iCloud-backed folder. Review and edit them before use.

## Security Notes

Do not publish your real skills folder without review. Skills often contain local paths, private infrastructure notes, usernames, internal URLs, or operational details. See `SECURITY.md`.

## License

MIT
