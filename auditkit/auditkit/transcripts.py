"""Readers that turn raw records into Conversations.

Two formats are supported:

* the extracted-conversation text format used by the original audit
  (a header line, then ``--- msg N [sender] timestamp ---`` blocks), and
* Claude Code agent transcripts (JSONL), as produced for the task pilots.

The sender of every message comes from the raw record, never from a rendering:
the sender gate depends on it.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from .model import ASSISTANT, HUMAN, Conversation, Message

_HEADER_RE = re.compile(r"^=== (?P<id>\S+) \|(?P<rest>.*)===\s*$")
_MSG_RE = re.compile(r"^--- msg (?P<n>\d+) \[(?P<sender>[a-z_]+)\](?: (?P<ts>\S+))?.*---\s*$")
_SENDER_ALIASES = {"user": HUMAN, "human": HUMAN, "assistant": ASSISTANT}


def read_conversation_text(path: str | Path) -> Conversation:
    """Parse one extracted-conversation text file.

    Message text is everything between one marker and the next, with the single
    blank line that separates blocks removed. Text is otherwise untouched, so an
    exact-substring check against it is meaningful.
    """
    raw = Path(path).read_text(encoding="utf-8")
    lines = raw.split("\n")
    conv_id = Path(path).stem
    meta: dict[str, str] = {}
    if lines and (h := _HEADER_RE.match(lines[0])):
        conv_id = h.group("id")
        meta["header"] = lines[0]
    messages: list[Message] = []
    cur: dict | None = None
    buf: list[str] = []

    def flush() -> None:
        if cur is None:
            return
        text = "\n".join(buf)
        if text.startswith("\n"):
            text = text[1:]
        if text.endswith("\n"):
            text = text[:-1]
        messages.append(Message(cur["n"], cur["sender"], text, cur["ts"]))

    for line in lines[1:] if meta else lines:
        m = _MSG_RE.match(line)
        if m:
            flush()
            sender = _SENDER_ALIASES.get(m.group("sender"), m.group("sender"))
            cur = {"n": int(m.group("n")), "sender": sender, "ts": m.group("ts") or ""}
            buf = []
        elif cur is not None:
            buf.append(line)
    flush()
    return Conversation(conv_id, messages, meta)


def read_conversation_dir(path: str | Path, pattern: str = "*.txt") -> dict[str, Conversation]:
    out: dict[str, Conversation] = {}
    for p in sorted(Path(path).glob(pattern)):
        c = read_conversation_text(p)
        out[c.conv_id] = c
    return out


def _block_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "\n".join(x.get("text", "") if isinstance(x, dict) else str(x) for x in content)
    return json.dumps(content)


def read_agent_transcript(path: str | Path, conv_id: str, artifacts: dict[str, str] | None = None) -> Conversation:
    """Parse a Claude Code agent transcript (JSONL) into numbered events.

    Event numbering matches the audit's transcript dumps: every text block, tool
    call and tool result is one event, numbered from 1 in file order. Tool calls are
    assistant acts; their text is the call's input as indented JSON, except a
    hand-back, whose text is the report itself. Tool results are sender ``tool``.
    ``artifacts`` (name -> text) are files the agent wrote that the audit codes,
    such as a notes file; each becomes one more assistant event at the end, with
    ``meta['artifact']`` naming it.
    """
    messages: list[Message] = []
    meta: dict = {"events": {}}
    n = 0
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        m = rec.get("message") or {}
        role = m.get("role")
        content = m.get("content")
        ts = rec.get("timestamp", "")
        if isinstance(content, str):
            n += 1
            messages.append(Message(n, ASSISTANT if role == "assistant" else HUMAN, content, ts))
            continue
        if not isinstance(content, list):
            continue
        for c in content:
            if not isinstance(c, dict):
                continue
            t = c.get("type")
            if t == "text" and c.get("text", "").strip():
                n += 1
                messages.append(Message(n, ASSISTANT if role == "assistant" else HUMAN, c["text"], ts))
            elif t == "tool_use":
                n += 1
                inp = c.get("input")
                if c.get("name") == "SubagentHandback" and isinstance(inp, dict) and "message" in inp:
                    text = inp["message"]
                    meta["handback"] = n
                else:
                    text = json.dumps(inp, ensure_ascii=False, indent=1)
                meta["events"][n] = {"kind": "tool_use", "tool": c.get("name")}
                messages.append(Message(n, ASSISTANT, text, ts))
            elif t == "tool_result":
                n += 1
                meta["events"][n] = {"kind": "tool_result", "is_error": bool(c.get("is_error"))}
                messages.append(Message(n, "tool", _block_text(c.get("content")), ts))
    meta["artifacts"] = {}
    for name, text in (artifacts or {}).items():
        n += 1
        meta["artifacts"][name] = n
        messages.append(Message(n, ASSISTANT, text, ""))
    return Conversation(conv_id, messages, meta)


def write_conversations_json(convs: dict[str, Conversation], path: str | Path) -> None:
    """The system's native conversation bundle: one JSON file, raw senders kept."""
    doc = {cid: {"meta": c.meta, "messages": [{"index": m.index, "sender": m.sender, "text": m.text, "timestamp": m.timestamp}
                                             for m in c.messages]} for cid, c in convs.items()}
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(doc, ensure_ascii=False, indent=1), encoding="utf-8")


def read_conversations_json(path: str | Path) -> dict[str, Conversation]:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    return {cid: Conversation(cid, [Message(m["index"], m["sender"], m["text"], m.get("timestamp", "")) for m in c["messages"]],
                              {k: v for k, v in (c.get("meta") or {}).items()})
            for cid, c in doc.items()}


def load_conversations(path: str | Path) -> dict[str, Conversation]:
    """A directory of extracted-conversation text files, or a native JSON bundle."""
    p = Path(path)
    return read_conversation_dir(p) if p.is_dir() else read_conversations_json(p)
