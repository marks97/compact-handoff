#!/usr/bin/env python3

import argparse
import json
import os
import sys
import time
from pathlib import Path

TAIL_BYTES = 65536
HEAD_LINES = 300


def slug_for_cwd(cwd):
    return cwd.replace("/", "-")


def fmt_size(n):
    if n < 1024:
        return f"{n}B"
    if n < 1024 * 1024:
        return f"{n/1024:.0f}KB"
    if n < 1024 * 1024 * 1024:
        return f"{n/1048576:.1f}MB"
    return f"{n/1073741824:.2f}GB"


def extract_text(content):
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "text":
                return block.get("text", "")
    return ""


SKIP_PREFIXES = (
    "<",
    "Caveat:",
    "This session is being continued from a previous conversation",
    "Your task is to create a detailed summary",
    "[Request interrupted",
    "API Error",
    "Please continue the conversation from where",
)


def clean(s, limit):
    if not s:
        return ""
    s = " ".join(s.split())
    for pref in SKIP_PREFIXES:
        if s.startswith(pref):
            return ""
    if len(s) < 3:
        return ""
    return s[:limit]


def scan_head(path):
    title = None
    first_user = None
    first_ts = None
    branch = None
    resumed = False
    with open(path, "r", errors="replace") as fh:
        for i, line in enumerate(fh):
            if i > HEAD_LINES:
                break
            try:
                o = json.loads(line)
            except Exception:
                continue
            if first_ts is None and o.get("timestamp"):
                first_ts = o["timestamp"]
            if branch is None and o.get("gitBranch"):
                branch = o["gitBranch"]
            if o.get("customTitle") and not title:
                title = o["customTitle"]
            if o.get("type") == "user":
                raw = " ".join(extract_text(o.get("message", {}).get("content")).split())
                if raw.startswith("This session is being continued from a previous conversation"):
                    resumed = True
                if first_user is None:
                    txt = clean(raw, 160)
                    if txt:
                        first_user = txt
    return title, first_user, first_ts, branch, resumed


def scan_tail(path, size):
    title = None
    last_ts = None
    last_prompt = None
    with open(path, "rb") as fh:
        if size > TAIL_BYTES:
            fh.seek(size - TAIL_BYTES)
            fh.readline()
        chunk = fh.read().decode("utf-8", errors="replace")
    for line in chunk.splitlines():
        try:
            o = json.loads(line)
        except Exception:
            continue
        if o.get("timestamp"):
            last_ts = o["timestamp"]
        if o.get("customTitle"):
            title = o["customTitle"]
        if o.get("lastPrompt"):
            lp = o["lastPrompt"]
            if isinstance(lp, str):
                last_prompt = clean(lp, 160)
    return title, last_ts, last_prompt


def scan_sidecars(session_dir, want_detail):
    info = {
        "subagents": 0,
        "subagent_bytes": 0,
        "workflow_agents": 0,
        "workflow_agent_bytes": 0,
        "workflow_runs": 0,
        "journals": 0,
        "journal_bytes": 0,
        "tool_results": 0,
        "tool_result_bytes": 0,
        "workflows": 0,
        "agents": [],
    }
    if not session_dir.is_dir():
        return info
    sub = session_dir / "subagents"
    if sub.is_dir():
        metas = []
        runs = set()
        for root, _dirs, files in os.walk(sub):
            in_workflow = f"{os.sep}workflows{os.sep}" in f"{root}{os.sep}"
            if in_workflow:
                runs.add(os.path.basename(root))
            for name in files:
                full = os.path.join(root, name)
                if name.endswith(".jsonl"):
                    try:
                        size = os.path.getsize(full)
                    except OSError:
                        size = 0
                    if name == "journal.jsonl":
                        info["journals"] += 1
                        info["journal_bytes"] += size
                    elif in_workflow:
                        info["workflow_agents"] += 1
                        info["workflow_agent_bytes"] += size
                    else:
                        info["subagents"] += 1
                        info["subagent_bytes"] += size
                elif name.endswith(".meta.json"):
                    metas.append(full)
        info["workflow_runs"] = len({r for r in runs if r.startswith("wf_")})
        if want_detail:
            for m in metas:
                try:
                    with open(m, "r", errors="replace") as fh:
                        o = json.load(fh)
                except Exception:
                    continue
                info["agents"].append(
                    {
                        "type": o.get("agentType", ""),
                        "name": o.get("name", ""),
                        "description": o.get("description", ""),
                        "model": o.get("model", ""),
                        "depth": o.get("spawnDepth", ""),
                    }
                )
    tr = session_dir / "tool-results"
    if tr.is_dir():
        for root, _dirs, files in os.walk(tr):
            for name in files:
                try:
                    info["tool_result_bytes"] += os.path.getsize(os.path.join(root, name))
                except OSError:
                    pass
                info["tool_results"] += 1
    wf = session_dir / "workflows"
    if wf.is_dir():
        for root, _dirs, files in os.walk(wf):
            info["workflows"] += len(files)
    return info


def count_turns(path):
    needle = b'"type":"user"'
    total = 0
    with open(path, "rb") as fh:
        while True:
            block = fh.read(4 * 1024 * 1024)
            if not block:
                break
            total += block.count(needle)
    return total


def index_dir(project_dir, limit, days, count_all, current_id, want_detail=False):
    files = sorted(
        Path(project_dir).glob("*.jsonl"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    cutoff = time.time() - days * 86400 if days else None
    rows = []
    for p in files:
        st = p.stat()
        if cutoff and st.st_mtime < cutoff:
            continue
        if limit and len(rows) >= limit:
            break
        title, first_user, first_ts, branch, resumed = scan_head(p)
        tail_title, last_ts, last_prompt = scan_tail(p, st.st_size)
        turns = count_turns(p) if (count_all or st.st_size < 20 * 1024 * 1024) else None
        side = scan_sidecars(p.with_suffix(""), want_detail)
        rows.append(
            {
                "session_id": p.stem,
                "path": str(p),
                "sidecar": side,
                "title": tail_title or title or "",
                "size": st.st_size,
                "mtime": st.st_mtime,
                "first_prompt": first_user or "",
                "last_prompt": last_prompt or "",
                "branch": branch or "",
                "turns": turns,
                "resumed": resumed,
                "is_current": p.stem == current_id,
            }
        )
    return rows


def render_md(rows, project_dir):
    total = sum(r["size"] for r in rows)
    sub_total = sum(r["sidecar"]["subagents"] for r in rows)
    sub_bytes = sum(r["sidecar"]["subagent_bytes"] for r in rows)
    wfa_total = sum(r["sidecar"]["workflow_agents"] for r in rows)
    wfa_bytes = sum(r["sidecar"]["workflow_agent_bytes"] for r in rows)
    wfr_total = sum(r["sidecar"]["workflow_runs"] for r in rows)
    tr_total = sum(r["sidecar"]["tool_results"] for r in rows)
    tr_bytes = sum(r["sidecar"]["tool_result_bytes"] for r in rows)
    out = []
    out.append("## Transcript index")
    out.append("")
    out.append(f"Project transcript dir: `{project_dir}`")
    out.append("")
    out.append(
        f"Every session in this project is listed, not a recent slice: {len(rows)} main transcripts ({fmt_size(total)}), "
        f"plus {sub_total} directly spawned subagent transcripts ({fmt_size(sub_bytes)}), "
        f"{wfa_total} workflow-spawned agent transcripts across {wfr_total} workflow runs ({fmt_size(wfa_bytes)}), "
        f"and {tr_total} offloaded tool-result files ({fmt_size(tr_bytes)})."
    )
    out.append("")
    out.append(
        "A session's sidecar lives at the transcript path with `.jsonl` dropped. Layout: "
        "`subagents/agent-*.jsonl` for direct spawns, `subagents/workflows/wf_<runid>/agent-*.jsonl` for workflow-spawned agents, "
        "`subagents/workflows/wf_<runid>/journal.jsonl` recording each agent's actual return value, "
        "`workflows/wf_<runid>.json` for run manifests, and `tool-results/*.txt` for offloaded outputs. "
        "Agent work does not appear in the main transcript beyond its final report, so when a past finding came from a fan-out, "
        "the reasoning is only in these files, and the matching `agent-*.meta.json` names what each one was for."
    )
    out.append("")
    out.append(
        "Do not grep these files first. Escalate in this order, because the largest single transcript here exceeds 75MB and loading one wastes an entire context window:"
    )
    out.append("")
    out.append(
        "1. Search your session transcripts for a distinctive phrase to find *which* session holds it, rather than opening files blind (use a transcript-search tool if your Claude Code setup exposes one, otherwise `grep -l` the phrase across the `.jsonl` files listed below)."
    )
    out.append(
        "2. Once you know the session, page through that session's turns instead of loading the whole transcript at once."
    )
    out.append(
        "3. Only if those miss, `grep -c` then `grep -n` the specific `.jsonl` below and `Read` the matched line range with `offset`/`limit`."
    )
    out.append(
        "4. For subagent or offloaded-output detail, `grep -l` across that session's sidecar dir, then read only the matching file."
    )
    out.append("")
    out.append("| Session | Title | Modified | Size | Turns | Sub | Tool out | Opened with |")
    out.append("|---|---|---|---|---|---|---|---|")
    for r in rows:
        when = time.strftime("%Y-%m-%d %H:%M", time.localtime(r["mtime"]))
        sid = r["session_id"][:8]
        if r["is_current"]:
            sid += " (current)"
        title = (r["title"] or "(untitled)").replace("|", "\\|")
        if r["resumed"]:
            title += " [resumed]"
        topic = (r["first_prompt"] or "").replace("|", "\\|")
        turns = str(r["turns"]) if r["turns"] is not None else "n/a"
        s = r["sidecar"]
        agents = s["subagents"] + s["workflow_agents"]
        sub = str(agents) if agents else ""
        if s["workflow_runs"]:
            sub += f" ({s['workflow_runs']}wf)"
        tr = fmt_size(s["tool_result_bytes"]) if s["tool_results"] else ""
        out.append(
            f"| `{sid}` | {title} | {when} | {fmt_size(r['size'])} | {turns} | {sub} | {tr} | {topic} |"
        )
    out.append("")
    if any(r["resumed"] for r in rows):
        out.append(
            "`[resumed]` means that session opened as a continuation after compaction, so its earlier history lives in a different transcript, not the one listed."
        )
        out.append("")
    out.append("Full session ids and paths:")
    out.append("")
    for r in rows:
        line = f"- `{r['session_id']}` -> `{r['path']}`"
        s = r["sidecar"]
        if s["subagents"] or s["workflow_agents"] or s["tool_results"]:
            bits = []
            if s["subagents"]:
                bits.append(f"{s['subagents']} direct subagents")
            if s["workflow_agents"]:
                bits.append(
                    f"{s['workflow_agents']} workflow agents in {s['workflow_runs']} runs"
                )
            if s["tool_results"]:
                bits.append(f"{s['tool_results']} tool-result files")
            line += f" (sidecar: {', '.join(bits)})"
        out.append(line)

    detailed = [r for r in rows if r["sidecar"]["agents"]]
    if detailed:
        out.append("")
        out.append("### Subagent detail")
        out.append("")
        for r in detailed:
            when = time.strftime("%Y-%m-%d", time.localtime(r["mtime"]))
            out.append(f"**`{r['session_id'][:8]}` {r['title'] or '(untitled)'}** ({when})")
            out.append("")
            for a in r["sidecar"]["agents"]:
                label = a["name"] or "(unnamed)"
                desc = a["description"] or ""
                out.append(f"- `{label}` [{a['type']}] {desc}")
            out.append("")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--project-dir", default=None)
    ap.add_argument("--cwd", default=os.getcwd())
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--days", type=int, default=0)
    ap.add_argument("--count-all", action="store_true")
    ap.add_argument("--subagent-detail", action="store_true")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    project_dir = args.project_dir or os.path.join(
        str(Path.home()), ".claude", "projects", slug_for_cwd(args.cwd)
    )
    if not os.path.isdir(project_dir):
        print(f"No transcript dir at {project_dir}", file=sys.stderr)
        return 4

    current_id = os.environ.get("CLAUDE_CODE_SESSION_ID", "")
    rows = index_dir(
        project_dir, args.limit, args.days, args.count_all, current_id, args.subagent_detail
    )
    if not rows:
        print(f"No transcripts found in {project_dir}", file=sys.stderr)
        return 5
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        print(render_md(rows, project_dir))
    return 0


if __name__ == "__main__":
    sys.exit(main())
