#!/usr/bin/env python3

import argparse
import json
import os
import re
import sys
from pathlib import Path

TAIL_BYTES = 131072
TRAILING_NUM = re.compile(r"^(.*?)\s+(\d+)$")


def transcript_path(session_id, cwd):
    slug = cwd.replace("/", "-")
    return Path.home() / ".claude" / "projects" / slug / f"{session_id}.jsonl"


def latest_title(path):
    if not path.is_file():
        return None
    size = path.stat().st_size
    title = None
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
        if o.get("customTitle"):
            title = o["customTitle"]
    if title:
        return title
    with open(path, "r", errors="replace") as fh:
        for i, line in enumerate(fh):
            if i > 400:
                break
            try:
                o = json.loads(line)
            except Exception:
                continue
            if o.get("customTitle"):
                title = o["customTitle"]
    return title


HANDOFF_REF = re.compile(r"(/(?:private/)?tmp/claude-handoffs/[A-Za-z0-9._-]+\.md)")


def find_parent_handoff(path, self_path=""):
    if not path.is_file():
        return None
    with open(path, "r", errors="replace") as fh:
        for i, line in enumerate(fh):
            if i > 2000:
                break
            try:
                o = json.loads(line)
            except Exception:
                continue
            if o.get("type") != "user":
                continue
            content = o.get("message", {}).get("content")
            if isinstance(content, list):
                text = " ".join(
                    b.get("text", "") for b in content if isinstance(b, dict)
                )
            else:
                text = content if isinstance(content, str) else ""
            for m in HANDOFF_REF.finditer(text):
                cand = m.group(1)
                if self_path and os.path.abspath(cand) == os.path.abspath(self_path):
                    continue
                if os.path.isfile(cand):
                    return cand
            return None
    return None


def bump(title):
    m = TRAILING_NUM.match(title.strip())
    if m and len(m.group(2)) <= 3:
        return f"{m.group(1)} {int(m.group(2)) + 1}"
    return f"{title.strip()} 2"


def slugify(title):
    s = re.sub(r"[^a-z0-9]+", "-", title.lower()).strip("-")
    return s[:48] or "handoff"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--session-id", default=os.environ.get("CLAUDE_CODE_SESSION_ID", ""))
    ap.add_argument("--cwd", default=os.getcwd())
    ap.add_argument("--fallback", default="Handoff")
    ap.add_argument("--self", dest="self_path", default="")
    args = ap.parse_args()

    current = None
    parent = None
    if args.session_id:
        tp = transcript_path(args.session_id, args.cwd)
        current = latest_title(tp)
        parent = find_parent_handoff(tp, args.self_path)

    if not current:
        current = args.fallback
        print("TITLE_SOURCE=fallback")
    else:
        print("TITLE_SOURCE=transcript")

    nxt = bump(current)
    print(f"CURRENT_TITLE={current}")
    print(f"NEXT_TITLE={nxt}")
    print(f"NEXT_SLUG={slugify(nxt)}")
    print(f"PARENT_HANDOFF={parent or 'none'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
