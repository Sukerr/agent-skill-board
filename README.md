# Agent Skill Hub

一个轻量的本地 Agent Skills 控制台，用来管理 Claude Code、Codex、Hermes 等工具共享的 `SKILL.md` 技能库。

它包含两个零依赖 Python 工具：

- `skill_board.py`：本地网页看板，用来浏览、搜索、打标签、查看健康状态。
- `skillhub.py`：本地共享命令行，用来扫描 skills，并把兼容的 skill 链接或复制到 Claude Code、Codex、Hermes 的目标目录。

整个项目不需要数据库，也不需要前端构建工具。

English documentation is available below.

## 功能

- 递归扫描所有 `SKILL.md`。
- 自动跳过 `.git`、`node_modules`、缓存、归档等噪音目录。
- 展示名称、简介、版本、相对路径、宿主徽标、健康状态、使用次数和标签。
- 自动识别技能大概率适用于 Hermes、Claude Code、Codex，还是通用 Agent Skill。
- 可读取可选的侧车文件：
  - `.skill-tags.json`
  - `.skill-desc-zh.json`
  - `.usage.json`
- 支持在网页里给 skill 打标签。
- 支持从网页打开本地 `SKILL.md` 或所在目录，但只允许打开配置的技能目录内部路径。
- 支持用 CLI 查看宿主同步状态，并把 skill 链接或复制到指定宿主目录。
- 提供简单 JSON API，方便本地自动化。
- 零第三方 Python 依赖。

## 快速开始

```bash
git clone https://github.com/Sukerr/agent-skill-hub.git
cd agent-skill-hub
python3 skill_board.py
```

打开：

```text
http://127.0.0.1:8777/
```

默认扫描目录：

```text
~/ai-workspace/shared-skills
```

你可以用环境变量指定自己的技能目录和端口：

```bash
SKILL_BOARD_SKILLS_DIR="$HOME/.agents/skills" \
SKILL_BOARD_PORT=8788 \
python3 skill_board.py
```

可选环境变量：

| 变量 | 默认值 |
| --- | --- |
| `SKILL_BOARD_SKILLS_DIR` | `~/ai-workspace/shared-skills` |
| `SKILL_BOARD_ICLOUD_DIR` | `~/Library/Mobile Documents/com~apple~CloudDocs/ai-skills` |
| `SKILL_BOARD_HOST` | `127.0.0.1` |
| `SKILL_BOARD_PORT` | `8777` |

## 侧车文件

没有侧车文件也可以正常使用。如果技能目录里存在这些文件，看板会自动读取：

```text
.skill-tags.json
.skill-desc-zh.json
.usage.json
```

在网页里编辑标签时，会写回 `.skill-tags.json`。

看板只会打开 `SKILL_BOARD_SKILLS_DIR` 内部的文件或目录。网页界面不会删除、归档、同步或发布 skill。

## SkillHub 共享 CLI

`skillhub.py` 负责把同一份 `SKILL.md` 技能库分发给不同宿主。它默认从 `~/ai-workspace/shared-skills` 扫描，也可以用 `--source` 或 `SKILLHUB_SOURCE` 指定目录。

扫描技能：

```bash
python3 skillhub.py --source examples/skills scan
```

查看某个宿主目录里哪些 skill 已同步：

```bash
python3 skillhub.py --source examples/skills status \
  --host claude \
  --target /tmp/claude-skills
```

把兼容的 skill 链接到宿主目录：

```bash
python3 skillhub.py --source examples/skills link \
  --host claude \
  --target /tmp/claude-skills \
  --mode link
```

使用复制模式：

```bash
python3 skillhub.py --source examples/skills link \
  --host codex \
  --project /path/to/project \
  --mode copy
```

默认宿主目录：

| 宿主 | 默认目标 |
| --- | --- |
| Claude Code | `~/.claude/skills` |
| Hermes | `~/.hermes/skills` |
| Codex | `<project>/.agents/skills` |

可选 `.skillhub.json` 清单可以覆盖单个 skill 的宿主兼容性、可见性和同步方式。参考 `.skillhub.example.json`。

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

## 示例 Skill

见 `examples/skills/demo-skill/SKILL.md`。

## 同步脚本模板

`scripts/` 目录里有可选的同步脚本模板，可以把技能目录同步到另一个本地目录或 iCloud 目录。`skillhub.py` 处理本机宿主分发，脚本模板处理目录级备份/分发；使用前请先按自己的环境检查和修改。

## 安全提醒

不要未经检查就公开自己的真实 skills 目录。技能文件里经常会包含本机路径、私有基础设施说明、用户名、内部 URL 或个人工作流细节。更多说明见 `SECURITY.md`。

## 许可证

MIT

---

## English

A tiny local Agent Skills hub for sharing `SKILL.md` folders across tools such as Claude Code, Codex, and Hermes.

It includes two zero-dependency Python tools:

- `skill_board.py`: a local web dashboard for browsing, searching, tagging, and checking skill health.
- `skillhub.py`: a local CLI for scanning skills and linking or copying compatible skills into Claude Code, Codex, or Hermes targets.

No database or frontend build step is required.

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
- Includes a CLI for host sync status and link/copy distribution.
- Exposes small JSON APIs for local automation.
- Requires no third-party Python packages.

## Quick Start

```bash
git clone https://github.com/Sukerr/agent-skill-hub.git
cd agent-skill-hub
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

Agent Skill Hub works without sidecar files. If present, it uses:

```text
.skill-tags.json
.skill-desc-zh.json
.usage.json
```

Tags are written back to `.skill-tags.json` when edited in the UI.

The app only opens files/directories inside `SKILL_BOARD_SKILLS_DIR`. It does not delete, archive, publish, or sync skills from the web UI.

## SkillHub CLI

`skillhub.py` distributes the same `SKILL.md` source folder to multiple local agent hosts. It scans `~/ai-workspace/shared-skills` by default; use `--source` or `SKILLHUB_SOURCE` to override it.

Scan skills:

```bash
python3 skillhub.py --source examples/skills scan
```

Check sync status for a host target:

```bash
python3 skillhub.py --source examples/skills status \
  --host claude \
  --target /tmp/claude-skills
```

Link compatible skills into a host target:

```bash
python3 skillhub.py --source examples/skills link \
  --host claude \
  --target /tmp/claude-skills \
  --mode link
```

Copy instead of symlinking:

```bash
python3 skillhub.py --source examples/skills link \
  --host codex \
  --project /path/to/project \
  --mode copy
```

Default host targets:

| Host | Default target |
| --- | --- |
| Claude Code | `~/.claude/skills` |
| Hermes | `~/.hermes/skills` |
| Codex | `<project>/.agents/skills` |

An optional `.skillhub.json` manifest can override per-skill host compatibility, visibility, and sync mode. See `.skillhub.example.json`.

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

The `scripts/` folder contains optional templates for syncing a skills folder to another local folder or iCloud-backed folder. `skillhub.py` handles local host distribution; the scripts are for folder-level backup/distribution. Review and edit them before use.

## Security Notes

Do not publish your real skills folder without review. Skills often contain local paths, private infrastructure notes, usernames, internal URLs, or operational details. See `SECURITY.md`.

## License

MIT
