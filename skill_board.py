#!/usr/bin/env python3
"""skill-board -- 本地 Skill 看板

扫描 ~/ai-workspace/shared-skills/ 下所有 SKILL.md，在浏览器里
以卡片形式展示，支持搜索、标签筛选、宿主/健康状态筛选、内联打标签、
本地打开文件/目录，并展示本地 + iCloud 同步概览。

零第三方依赖，仅用 Python 标准库。
"""

import json
import os
import re
import subprocess
import sys
import webbrowser
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse

HOME = os.path.expanduser("~")
DEFAULT_SKILLS_DIR = os.path.join(HOME, "ai-workspace", "shared-skills")
DEFAULT_ICLOUD_DIR = os.path.join(HOME, "Library", "Mobile Documents", "com~apple~CloudDocs", "ai-skills")
SKILLS_DIR = os.path.abspath(os.path.expanduser(os.environ.get("SKILL_BOARD_SKILLS_DIR", DEFAULT_SKILLS_DIR)))
ICLOUD_DIR = os.path.abspath(os.path.expanduser(os.environ.get("SKILL_BOARD_ICLOUD_DIR", DEFAULT_ICLOUD_DIR)))
TAGS_FILE = os.path.join(SKILLS_DIR, ".skill-tags.json")
DESC_FILE = os.path.join(SKILLS_DIR, ".skill-desc-zh.json")
USAGE_FILE = os.path.join(SKILLS_DIR, ".usage.json")
HOST = os.environ.get("SKILL_BOARD_HOST", "127.0.0.1")
PORT = int(os.environ.get("SKILL_BOARD_PORT", "8777"))

SKIP_DIRS = {
    ".git",
    "_public",
    ".archive",
    ".curator_backups",
    "__pycache__",
    ".pytest_cache",
    ".mypy_cache",
    ".ruff_cache",
    ".cache",
    "node_modules",
}

# 首次运行时按关键词预填的分类标签
SEED_RULES = [
    ("内容创作", ["content", "文案", "小红书", "图文", "social card", "script", "脚本", "公众号", "封面", "帖"]),
    ("研究", ["research", "调研", "last30days", "搜集", "信息"]),
    ("开发流程", ["plan", "implement", "development", "worktree", "branch", "subagent", "tdd", "test-driven", "executing"]),
    ("调试", ["debug", "bug", "调试", "connectivity", "troubleshoot"]),
    ("代码审查", ["review", "审查", "verification", "code-review"]),
    ("工具", ["tool", "工具", "skill", "config", "setup", "gateway"]),
    ("AI行业", ["ai 行业", "ai industry", "ai发展", "模型"]),
    ("艺术", ["art", "艺术", "画", "guizang"]),
]


def read_text(path, limit=None):
    try:
        with open(path, "r", encoding="utf-8") as f:
            text = f.read(limit) if limit else f.read()
    except OSError:
        return ""
    return text


def load_json_file(path, default):
    if os.path.isfile(path):
        try:
            with open(path, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return default
    return default


def parse_frontmatter(path):
    """轻量解析 SKILL.md 的 YAML frontmatter，取常用顶层字段和 hermes 标记。"""
    text = read_text(path)
    m = re.match(r"^---\s*\n(.*?)\n---", text, re.DOTALL)
    if not m:
        return {}, False

    block = m.group(1)
    lines = block.splitlines()
    out = {}
    i = 0
    while i < len(lines):
        line = lines[i]
        i += 1
        if not line or line[0] in " \t#":
            continue
        fm = re.match(r"^([A-Za-z0-9_-]+):\s*(.*)$", line)
        if not fm:
            continue
        key, val = fm.group(1).lower(), fm.group(2).strip()
        if key not in ("name", "description", "version", "author", "license"):
            continue
        if val in ("|", ">", "|-", ">-", "|+", ">+"):
            collected = []
            while i < len(lines) and (lines[i] == "" or lines[i][0] in " \t"):
                collected.append(lines[i].strip())
                i += 1
            joiner = "\n" if val.startswith("|") else " "
            val = joiner.join(c for c in collected if c).strip()
        elif len(val) >= 2 and val[0] in "\"'" and val[-1] == val[0]:
            val = val[1:-1]
        out[key] = val
    has_hermes = bool(re.search(r"^\s{2,}hermes:\s*$|^metadata:\s*$[\s\S]*?^\s{2,}hermes:\s*$", block, re.MULTILINE))
    return out, has_hermes


def iter_skill_files(root):
    """递归扫描 SKILL.md，跟随目录软链，但用 realpath 去重避免循环。"""
    if not os.path.isdir(root):
        return
    seen_dirs = set()
    for current, dirs, files in os.walk(root, followlinks=True):
        dirs[:] = sorted(d for d in dirs if d not in SKIP_DIRS and not d.startswith(".venv"))
        real_current = os.path.realpath(current)
        if real_current in seen_dirs:
            dirs[:] = []
            continue
        seen_dirs.add(real_current)
        if "SKILL.md" in files:
            yield os.path.join(current, "SKILL.md")


def relpath(path):
    return os.path.relpath(path, SKILLS_DIR)


def skill_key_candidates(skill):
    return [
        skill.get("name", ""),
        skill.get("dir", ""),
        os.path.basename(skill.get("dir_path", "")),
        skill.get("relative_path", "").split(os.sep)[0],
    ]


def lookup_by_candidates(mapping, skill, default=None):
    for key in skill_key_candidates(skill):
        if key and key in mapping:
            return mapping[key]
    return default


def nearest_plugin_files(dir_path):
    """向上查找当前 skill 所在包的宿主插件标记。"""
    found = set()
    cur = dir_path
    root = os.path.abspath(SKILLS_DIR)
    while os.path.abspath(cur).startswith(root):
        if os.path.isdir(os.path.join(cur, ".claude-plugin")) or os.path.isfile(os.path.join(cur, "CLAUDE.md")):
            found.add("Claude Code")
        if os.path.isdir(os.path.join(cur, ".codex-plugin")) or os.path.isdir(os.path.join(cur, ".agents")):
            found.add("Codex")
        if cur == root:
            break
        cur = os.path.dirname(cur)
    return found


def detect_hosts(skill, frontmatter_has_hermes, text):
    blob = text.lower()
    hosts = set(nearest_plugin_files(skill["dir_path"]))
    strong = set()

    if frontmatter_has_hermes:
        hosts.add("Hermes")
        strong.add("Hermes")
    if re.search(r"\bhermes\b|gateway|kanban|curator|toolsets?|skill_view|terminal\(", blob):
        hosts.add("Hermes")
    if re.search(r"claude code|claude-code|\.claude-plugin|\bclaude\b", blob):
        hosts.add("Claude Code")
    if re.search(r"\bcodex\b|\.codex-plugin|\.agents/skills|openai codex", blob):
        hosts.add("Codex")

    if not hosts:
        hosts.add("通用")
    return sorted(hosts, key=lambda h: {"通用": 0, "Hermes": 1, "Claude Code": 2, "Codex": 3}.get(h, 9)), strong


def host_specific_unmarked(hosts, strong_hosts, dir_path):
    specific = {h for h in hosts if h != "通用"}
    if not specific:
        return False
    if strong_hosts:
        return False
    plugin_hosts = nearest_plugin_files(dir_path)
    return not bool(plugin_hosts & specific)


def parse_dt(value):
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def days_ago(value):
    dt = parse_dt(value)
    if not dt:
        return None
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return max(0, (now - dt).days)


def usage_status(name, usage):
    item = usage.get(name, {}) if isinstance(usage, dict) else {}
    state = item.get("state") or "unknown"
    use_count = item.get("use_count", 0) or 0
    view_count = item.get("view_count", 0) or 0
    last_used_at = item.get("last_used_at")
    stale = use_count == 0 and not last_used_at
    return {
        "state": state,
        "pinned": bool(item.get("pinned")),
        "use_count": use_count,
        "view_count": view_count,
        "patch_count": item.get("patch_count", 0) or 0,
        "last_used_at": last_used_at,
        "last_viewed_at": item.get("last_viewed_at"),
        "last_patched_at": item.get("last_patched_at"),
        "days_since_used": days_ago(last_used_at),
        "stale": stale,
    }


def health_for(skill, fm, hosts, strong_hosts, usage):
    badges = []
    if not fm:
        badges.append({"level": "warn", "label": "无 frontmatter"})
    if not fm.get("description"):
        badges.append({"level": "warn", "label": "缺简介"})
    if host_specific_unmarked(hosts, strong_hosts, skill["dir_path"]):
        badges.append({"level": "warn", "label": "宿主专用未标注"})
    if skill["is_symlink"]:
        badges.append({"level": "info", "label": "软链"})
    if usage.get("pinned"):
        badges.append({"level": "info", "label": "已固定"})
    if usage.get("state") and usage["state"] not in ("active", "unknown"):
        badges.append({"level": "warn", "label": usage["state"]})
    if usage.get("stale"):
        badges.append({"level": "muted", "label": "闲置"})
    if not badges:
        badges.append({"level": "ok", "label": "OK"})
    return badges


def scan_skills():
    """扫描 shared-skills，返回所有 SKILL.md 的结构化信息。"""
    skills = []
    if not os.path.isdir(SKILLS_DIR):
        return skills
    usage_map = load_json_file(USAGE_FILE, {})
    for skill_md in sorted(iter_skill_files(SKILLS_DIR), key=lambda p: relpath(p).lower()):
        dir_path = os.path.dirname(skill_md)
        relative_path = relpath(skill_md)
        category_path = os.path.dirname(relative_path)
        fm, has_hermes = parse_frontmatter(skill_md)
        text = read_text(skill_md, limit=120000)
        name = fm.get("name") or os.path.basename(dir_path)
        skill = {
            "dir": os.path.basename(dir_path),
            "name": name,
            "description": fm.get("description", ""),
            "version": fm.get("version", ""),
            "category_path": category_path,
            "relative_path": relative_path,
            "skill_md_path": skill_md,
            "dir_path": dir_path,
            "is_symlink": os.path.islink(dir_path) or os.path.islink(skill_md),
            "symlink_target": os.path.realpath(dir_path) if os.path.islink(dir_path) else "",
            "frontmatter_ok": bool(fm),
        }
        hosts, strong_hosts = detect_hosts(skill, has_hermes, text)
        usage = usage_status(name, usage_map)
        skill["hosts"] = hosts
        skill["usage"] = usage
        skill["health"] = health_for(skill, fm, hosts, strong_hosts, usage)
        skills.append(skill)
    return skills


def _kw_hit(keyword, haystack):
    """关键词命中判断：纯 ASCII 关键词用词边界匹配，含中文等非 ASCII 的用子串匹配。"""
    k = keyword.lower()
    if k.isascii():
        return re.search(r"\b" + re.escape(k) + r"\b", haystack) is not None
    return k in haystack


def seed_tags(skills):
    """按关键词为每个 skill 预填分类标签。"""
    tags = {}
    for s in skills:
        haystack = (s["name"] + " " + s["description"] + " " + s["relative_path"]).lower()
        matched = []
        for label, keywords in SEED_RULES:
            if any(_kw_hit(k, haystack) for k in keywords):
                matched.append(label)
        tags[s["name"]] = matched
    return tags


def load_tags():
    if os.path.isfile(TAGS_FILE):
        try:
            with open(TAGS_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except (OSError, json.JSONDecodeError):
            return {}
    return None


def save_tags(tags):
    with open(TAGS_FILE, "w", encoding="utf-8") as f:
        json.dump(tags, f, ensure_ascii=False, indent=2)
        f.write("\n")


def get_state():
    """返回 skill 列表（含标签 + 中文简介覆盖），首次运行自动预填标签文件。"""
    skills = scan_skills()
    tags = load_tags()
    if tags is None:
        tags = seed_tags(skills)
        save_tags(tags)
    desc_zh = load_json_file(DESC_FILE, {})
    for s in skills:
        s["tags"] = lookup_by_candidates(tags, s, [])
        desc = lookup_by_candidates(desc_zh, s, "")
        if isinstance(desc, str) and desc.strip():
            s["description_en"] = s["description"]
            s["description"] = desc
    return skills


def count_skill_files(path):
    if not os.path.isdir(path):
        return 0
    count = 0
    for current, dirs, files in os.walk(path, followlinks=True):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        if "SKILL.md" in files:
            count += 1
    return count


def get_status():
    skills = scan_skills()
    icloud_exists = os.path.isdir(ICLOUD_DIR)
    return {
        "local": {
            "path": SKILLS_DIR,
            "exists": os.path.isdir(SKILLS_DIR),
            "skill_count": len(skills),
        },
        "icloud": {
            "path": ICLOUD_DIR,
            "exists": icloud_exists,
            "skill_count": count_skill_files(ICLOUD_DIR) if icloud_exists else 0,
        },
        "nas": {
            "checked": False,
            "message": "未自动探测 NAS",
        },
    }


def allowed_shared_path(path):
    if not isinstance(path, str) or not path:
        return None
    abs_path = os.path.abspath(os.path.expanduser(path))
    root = os.path.abspath(SKILLS_DIR)
    if abs_path == root or abs_path.startswith(root + os.sep):
        return abs_path
    return None


def open_path(kind, path):
    abs_path = allowed_shared_path(path)
    if not abs_path:
        return 403, {"error": "path outside shared-skills"}
    if kind == "file":
        if not os.path.isfile(abs_path):
            return 400, {"error": "file not found"}
    elif kind == "dir":
        if not os.path.isdir(abs_path):
            return 400, {"error": "dir not found"}
    else:
        return 400, {"error": "bad kind"}

    try:
        subprocess.Popen(["open", abs_path], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except OSError as exc:
        return 500, {"error": str(exc)}
    return 200, {"ok": True}


HTML_PAGE = r"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Skill 看板</title>
<style>
  :root {
    --bg: #0f1115; --panel: #181b22; --panel2: #1f232c;
    --border: #2a2f3a; --text: #e6e9ef; --muted: #8b93a3;
    --accent: #6ea8fe; --accent-dim: #2b3a55; --chip: #232834;
    --ok: #7dd97d; --warn: #f4bd50; --bad: #ff7b72; --cyan: #72d6d6;
  }
  * { box-sizing: border-box; }
  body {
    margin: 0; background: var(--bg); color: var(--text);
    font-family: -apple-system, "PingFang SC", "Segoe UI", sans-serif;
    font-size: 14px; line-height: 1.5;
  }
  header {
    position: sticky; top: 0; z-index: 10; background: rgba(15,17,21,.94);
    backdrop-filter: blur(8px); border-bottom: 1px solid var(--border);
    padding: 16px 24px;
  }
  .title-row { display: flex; align-items: baseline; gap: 12px; margin-bottom: 12px; flex-wrap: wrap; }
  h1 { font-size: 18px; margin: 0; font-weight: 600; }
  .count, .sync { color: var(--muted); font-size: 13px; }
  .sync strong { color: var(--text); font-weight: 500; }
  #search {
    width: 100%; padding: 9px 12px; background: var(--panel2);
    border: 1px solid var(--border); border-radius: 8px; color: var(--text);
    font-size: 14px; outline: none;
  }
  #search:focus { border-color: var(--accent); }
  .filter-block { margin-top: 10px; display: flex; flex-direction: column; gap: 8px; }
  .filters { display: flex; flex-wrap: wrap; gap: 7px; align-items: center; }
  .filter-label { color: var(--muted); font-size: 12px; margin-right: 2px; }
  .chip {
    padding: 4px 10px; border-radius: 99px; background: var(--chip);
    border: 1px solid var(--border); color: var(--muted); cursor: pointer;
    font-size: 12px; user-select: none; transition: all .12s;
  }
  .chip:hover { color: var(--text); }
  .chip.active { background: var(--accent-dim); border-color: var(--accent); color: var(--accent); }
  main {
    padding: 20px 24px; display: grid; gap: 14px;
    grid-template-columns: repeat(auto-fill, minmax(330px, 1fr));
  }
  .card {
    background: var(--panel); border: 1px solid var(--border); border-radius: 10px;
    padding: 15px 16px; transition: border-color .12s, transform .12s;
    display: flex; flex-direction: column; gap: 9px; min-width: 0;
  }
  .card:hover { border-color: var(--accent-dim); transform: translateY(-1px); }
  .card-head { display: flex; align-items: baseline; gap: 8px; justify-content: space-between; }
  .name-line { display: flex; align-items: baseline; gap: 8px; min-width: 0; }
  .card-name { font-weight: 600; font-size: 14.5px; word-break: break-word; }
  .card-ver { color: var(--muted); font-size: 11px; white-space: nowrap; }
  .path { color: var(--muted); font-size: 11.5px; word-break: break-all; }
  .card-desc { color: var(--muted); font-size: 13px;
    display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden; }
  .card.expanded .card-desc { -webkit-line-clamp: unset; }
  .row { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }
  .badge, .tag {
    padding: 2px 8px; border-radius: 6px; font-size: 11.5px;
    display: inline-flex; align-items: center; gap: 4px; border: 1px solid transparent;
  }
  .host { background: #26313e; color: var(--cyan); border-color: #334c5a; }
  .health-ok { background: #1f3427; color: var(--ok); border-color: #31553c; }
  .health-warn { background: #3a3020; color: var(--warn); border-color: #5c4a28; }
  .health-info { background: #232f43; color: var(--accent); border-color: #34496c; }
  .health-muted { background: var(--chip); color: var(--muted); border-color: var(--border); }
  .tag { background: var(--accent-dim); color: var(--accent); }
  .tag .x { cursor: pointer; opacity: .65; font-weight: bold; }
  .tag .x:hover { opacity: 1; }
  .add-tag, .action {
    padding: 2px 8px; border-radius: 6px; background: var(--chip);
    border: 1px dashed var(--border); color: var(--muted); font-size: 11.5px;
    cursor: pointer;
  }
  .action { border-style: solid; }
  .add-tag:hover, .action:hover { color: var(--text); border-color: var(--accent); }
  .meta { color: var(--muted); font-size: 12px; display: none; }
  .card.expanded .meta { display: block; }
  .empty { color: var(--muted); padding: 40px; text-align: center; grid-column: 1/-1; }
</style>
</head>
<body>
<header>
  <div class="title-row">
    <h1>Skill 看板</h1>
    <span class="count" id="count"></span>
    <span class="sync" id="sync"></span>
  </div>
  <input id="search" placeholder="搜索 skill 名称、简介或路径…" autocomplete="off">
  <div class="filter-block">
    <div class="filters" id="hostFilters"></div>
    <div class="filters" id="healthFilters"></div>
    <div class="filters" id="tagFilters"></div>
  </div>
</header>
<main id="grid"></main>

<script>
let SKILLS = [];
let activeTags = new Set();
let activeHosts = new Set();
let activeHealth = new Set();
let query = "";

async function load() {
  const [skillsRes, statusRes] = await Promise.all([
    fetch("/api/skills"),
    fetch("/api/status")
  ]);
  SKILLS = await skillsRes.json();
  const status = await statusRes.json();
  renderStatus(status);
  render();
}

function renderStatus(status) {
  const local = status.local || {};
  const icloud = status.icloud || {};
  document.getElementById("sync").innerHTML =
    `本地 <strong>${local.skill_count || 0}</strong> · ` +
    `iCloud <strong>${icloud.exists ? (icloud.skill_count || 0) : "未找到"}</strong> · NAS 未探测`;
}

function valuesFrom(getter) {
  const s = new Set();
  SKILLS.forEach(k => (getter(k) || []).forEach(t => s.add(t)));
  return [...s].sort();
}

function drawFilter(id, label, values, activeSet) {
  const box = document.getElementById(id);
  box.innerHTML = `<span class="filter-label">${label}</span>`;
  values.forEach(v => {
    const c = document.createElement("span");
    c.className = "chip" + (activeSet.has(v) ? " active" : "");
    c.textContent = v;
    c.onclick = () => { activeSet.has(v) ? activeSet.delete(v) : activeSet.add(v); render(); };
    box.appendChild(c);
  });
}

function render() {
  drawFilter("hostFilters", "宿主", valuesFrom(k => k.hosts), activeHosts);
  drawFilter("healthFilters", "状态", valuesFrom(k => (k.health || []).map(h => h.label)), activeHealth);
  drawFilter("tagFilters", "标签", valuesFrom(k => k.tags), activeTags);

  const q = query.toLowerCase();
  const list = SKILLS.filter(k => {
    const text = [k.name, k.description, k.description_en, k.relative_path, k.category_path].join(" ").toLowerCase();
    const hitQ = !q || text.includes(q);
    const hitT = activeTags.size === 0 || [...activeTags].every(t => (k.tags||[]).includes(t));
    const hitH = activeHosts.size === 0 || [...activeHosts].every(t => (k.hosts||[]).includes(t));
    const healthLabels = (k.health || []).map(h => h.label);
    const hitS = activeHealth.size === 0 || [...activeHealth].every(t => healthLabels.includes(t));
    return hitQ && hitT && hitH && hitS;
  });

  document.getElementById("count").textContent = list.length + " / " + SKILLS.length + " 个 skill";

  const grid = document.getElementById("grid");
  grid.innerHTML = "";
  if (list.length === 0) {
    grid.innerHTML = '<div class="empty">没有匹配的 skill</div>';
    return;
  }
  list.forEach(k => grid.appendChild(card(k)));
}

function card(k) {
  const el = document.createElement("div");
  el.className = "card";
  el.onclick = (e) => {
    if (e.target.closest(".tag, .add-tag, .action")) return;
    el.classList.toggle("expanded");
  };

  const head = document.createElement("div");
  head.className = "card-head";
  head.innerHTML = `<div class="name-line"><span class="card-name">${esc(k.name)}</span>` +
    (k.version ? `<span class="card-ver">v${esc(k.version)}</span>` : "") +
    `</div>`;
  el.appendChild(head);

  const path = document.createElement("div");
  path.className = "path";
  path.textContent = k.relative_path;
  el.appendChild(path);

  const hosts = document.createElement("div");
  hosts.className = "row";
  (k.hosts || []).forEach(h => hosts.appendChild(badge(h, "host")));
  (k.health || []).forEach(h => hosts.appendChild(badge(h.label, "health-" + h.level)));
  el.appendChild(hosts);

  const desc = document.createElement("div");
  desc.className = "card-desc";
  desc.textContent = k.description || "（无简介）";
  el.appendChild(desc);

  const usage = k.usage || {};
  const meta = document.createElement("div");
  meta.className = "meta";
  meta.innerHTML =
    `使用 ${usage.use_count || 0} 次，查看 ${usage.view_count || 0} 次` +
    (usage.last_used_at ? `，最近使用 ${esc(usage.last_used_at)}` : "，暂无使用记录") +
    (k.is_symlink ? `<br>软链来源：${esc(k.symlink_target || "")}` : "") +
    (k.description_en ? `<br>英文简介：${esc(k.description_en)}` : "");
  el.appendChild(meta);

  const tags = document.createElement("div");
  tags.className = "row";
  (k.tags || []).forEach(t => {
    const tag = document.createElement("span");
    tag.className = "tag";
    tag.innerHTML = `${esc(t)} <span class="x">×</span>`;
    tag.querySelector(".x").onclick = () => removeTag(k, t);
    tags.appendChild(tag);
  });
  const add = document.createElement("span");
  add.className = "add-tag";
  add.textContent = "+ 标签";
  add.onclick = () => addTag(k);
  tags.appendChild(add);
  el.appendChild(tags);

  const actions = document.createElement("div");
  actions.className = "row";
  actions.appendChild(action("打开文件", () => openLocal("file", k.skill_md_path)));
  actions.appendChild(action("打开目录", () => openLocal("dir", k.dir_path)));
  el.appendChild(actions);

  return el;
}

function badge(text, cls) {
  const b = document.createElement("span");
  b.className = "badge " + cls;
  b.textContent = text;
  return b;
}

function action(text, fn) {
  const a = document.createElement("span");
  a.className = "action";
  a.textContent = text;
  a.onclick = fn;
  return a;
}

async function openLocal(kind, path) {
  const r = await fetch("/api/open", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({kind, path})
  });
  if (!r.ok) {
    const data = await r.json().catch(() => ({}));
    alert(data.error || "打开失败");
  }
}

async function addTag(k) {
  const t = prompt("给「" + k.name + "」添加标签：");
  if (!t) return;
  const tag = t.trim();
  if (!tag || (k.tags||[]).includes(tag)) return;
  k.tags = [...(k.tags||[]), tag];
  await saveTags(k);
  render();
}

async function removeTag(k, t) {
  k.tags = (k.tags||[]).filter(x => x !== t);
  await saveTags(k);
  render();
}

async function saveTags(k) {
  await fetch("/api/tags", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({ skill: k.name, tags: k.tags })
  });
}

function esc(s) {
  return String(s || "").replace(/[&<>"']/g, c =>
    ({"&":"&amp;","<":"&lt;",">":"&gt;","\"":"&quot;","'":"&#39;"}[c]));
}

document.getElementById("search").addEventListener("input", e => {
  query = e.target.value; render();
});

load();
</script>
</body>
</html>
"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(data)

    def _json_body(self):
        length = int(self.headers.get("Content-Length", 0))
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return None

    def do_HEAD(self):
        if self.path == "/" or self.path.startswith("/index"):
            self._send(200, b"", "text/html")
        else:
            self._send(404, b"")

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/" or path.startswith("/index"):
            self._send(200, HTML_PAGE, "text/html")
        elif path == "/api/skills":
            self._send(200, json.dumps(get_state(), ensure_ascii=False))
        elif path == "/api/status":
            self._send(200, json.dumps(get_status(), ensure_ascii=False))
        else:
            self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):
        path = urlparse(self.path).path
        payload = self._json_body()
        if payload is None:
            self._send(400, json.dumps({"error": "bad json"}))
            return

        if path == "/api/tags":
            skill = payload.get("skill")
            new_tags = payload.get("tags", [])
            if not skill or not isinstance(new_tags, list):
                self._send(400, json.dumps({"error": "bad payload"}))
                return
            tags = load_tags() or {}
            tags[skill] = [str(t).strip() for t in new_tags if str(t).strip()]
            save_tags(tags)
            self._send(200, json.dumps({"ok": True}))
            return

        if path == "/api/open":
            code, body = open_path(payload.get("kind"), payload.get("path"))
            self._send(code, json.dumps(body, ensure_ascii=False))
            return

        self._send(404, json.dumps({"error": "not found"}))

    def log_message(self, *args):
        pass


def main():
    if not os.path.isdir(SKILLS_DIR):
        print(f"shared-skills 目录不存在：{SKILLS_DIR}")
        return 1
    try:
        server = ThreadingHTTPServer((HOST, PORT), Handler)
    except OSError as exc:
        print(f"Skill 看板启动失败：无法监听 {HOST}:{PORT} ({exc})")
        print("如果已经打开过看板，请先关闭旧进程，或检查端口是否被占用。")
        return 1

    url = f"http://{HOST}:{PORT}/"
    n = len(scan_skills())
    print(f"Skill 看板已启动：{url}")
    print(f"共 {n} 个 skill，按 Ctrl+C 退出")
    try:
        webbrowser.open(url)
    except Exception:
        pass
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已退出。")
        server.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
