"""The error decision tree as data: validate it, walk it, render it."""
from __future__ import annotations

from typing import Any


def validate_tree(doc: dict[str, Any], codebook: dict[str, Any] | None = None) -> list[str]:
    """Every option resolves, every path from the start ends at a terminal, no cycles.

    Given the codebook's data, every ``protected`` terminal's ref must be a codebook
    protection key and every ``register`` terminal's ref a codebook register key: a
    ref that resolves nowhere would send a coder to a rule that does not exist.
    """
    nodes = doc.get("nodes") or {}
    problems: list[str] = []
    start = doc.get("start")
    if start not in nodes:
        return [f"start node {start!r} does not exist"]
    ref_keys = {"protected": "protections", "register": "registers"}
    for nid, n in nodes.items():
        if n.get("kind") == "question":
            opts = n.get("options") or []
            if len(opts) < 2:
                problems.append(f"{nid}: a question needs at least two options")
            for o in opts:
                if o.get("to") not in nodes:
                    problems.append(f"{nid}: option {o.get('label')!r} points to missing node {o.get('to')!r}")
        elif n.get("kind") == "terminal":
            t = n.get("terminal") or {}
            if not t.get("type"):
                problems.append(f"{nid}: terminal without a type")
            elif codebook is not None and t.get("type") in ref_keys:
                table = ref_keys[t["type"]]
                if t.get("ref") not in (codebook.get(table) or {}):
                    problems.append(f"{nid}: {t['type']} ref {t.get('ref')!r} is not a key in codebook {table}")
        else:
            problems.append(f"{nid}: kind must be question or terminal")
    if problems:
        return problems
    state: dict[str, int] = {}

    def visit(nid: str, path: list[str]) -> None:
        if state.get(nid) == 1:
            problems.append("cycle: " + " -> ".join(path + [nid]))
            return
        if state.get(nid) == 2:
            return
        state[nid] = 1
        for o in nodes[nid].get("options") or []:
            visit(o["to"], path + [nid])
        state[nid] = 2

    visit(start, [])
    unreachable = [nid for nid in nodes if nid not in state]
    if unreachable:
        problems.append(f"unreachable nodes: {unreachable}")
    return problems


def walk(doc: dict[str, Any], answers: list[str]) -> list[str]:
    """Follow option labels from the start; returns the node path."""
    nodes, nid, path = doc["nodes"], doc["start"], [doc["start"]]
    for label in answers:
        opts = {o["label"]: o["to"] for o in nodes[nid].get("options") or []}
        if label not in opts:
            raise KeyError(f"{nid} has no option {label!r}; options are {list(opts)}")
        nid = opts[label]
        path.append(nid)
    return path


def _mm(s: str) -> str:
    return (s or "").replace('"', "'").replace("\n", " ")[:90]


def render_markdown(doc: dict[str, Any]) -> str:
    nodes = doc["nodes"]
    L = [f"# {doc.get('title', 'Decision tree')}", "",
         f"Version {doc.get('version', '')}. Generated from `decision_tree.json` by `python -m auditkit tree`; do not edit by hand.", ""]
    L += ["```mermaid", "flowchart TD"]
    for nid, n in nodes.items():
        label = _mm(n["text"])
        L.append(f'  {nid}{{"{label}"}}' if n["kind"] == "question" else f'  {nid}["{label}"]')
    for nid, n in nodes.items():
        for o in n.get("options") or []:
            L.append(f'  {nid} -- "{_mm(o["label"])}" --> {o["to"]}')
    L += ["```", ""]
    for st in doc.get("stages") or []:
        L += [f"## {st['title']}", "", st.get("summary", ""), ""]
        for nid, n in nodes.items():
            if n.get("stage") != st["id"]:
                continue
            if n["kind"] == "question":
                L.append(f"**{n['text']}** <a id=\"{nid}\"></a>")
                if n.get("help"):
                    L.append(f"  {n['help']}")
                for o in n["options"]:
                    tgt = nodes[o["to"]]
                    L.append(f"- {o['label']} -> {tgt['text']}")
            else:
                t = n["terminal"]
                L.append(f"- **{n['text']}** ({t['type']}{': ' + t['ref'] if t.get('ref') else ''})" + (f". {n['help']}" if n.get("help") else ""))
            L.append("")
    cs = doc.get("class_selection")
    if cs:
        L += ["## Choosing the class", ""] + [f"{i}. {q}" for i, q in enumerate(cs.get("order", []), 1)] + [""]
        L += [f"- {r}" for r in cs.get("rules", [])] + [""]
    if doc.get("worked_traces"):
        L += ["## Worked traces", ""]
        for t in doc["worked_traces"]:
            L += [f"**{t['title']}**: " + " -> ".join(nodes[p]["text"] if p in nodes else p for p in t["path"]) + f". Result: {t['result']}", ""]
    if doc.get("law_differences"):
        L += ["## Where the drawn tree and the rubric differ (the rubric governs)", ""] + [f"- {d}" for d in doc["law_differences"]] + [""]
    return "\n".join(L)
