"""Write docs/audit_rubric/PAPER_ERRORS.md from docs/audit_rubric/paper_errors.json.

    py -3 tools/paper_errors.py

The JSON holds every item checked against the two papers, with its status. The markdown lists the
items that hold (VERIFIED, or CORRECTED: a real error the earlier list stated wrongly) as errors, and
lists the rest under "Not counted as errors" with the reason. Counts are computed here, never typed.
"""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SRC = REPO / "docs" / "audit_rubric" / "paper_errors.json"
OUT = REPO / "docs" / "audit_rubric" / "PAPER_ERRORS.md"
HOLDS = ("VERIFIED", "CORRECTED")
WHY_NOT = {
    "RECORD-DEPENDENT": "rests on this project's private record, not on the paper",
    "ARGUMENT": "an argument or framing, not a checkable fact about the paper",
    "NOT SUPPORTED": "the paper's text does not show it",
    "OVERLAP": "covered by another item, so not counted twice",
}


def counts(doc: dict) -> dict:
    """Per paper: errors that hold, by category, and the items not counted, by status."""
    out = {}
    for p in doc["papers"]:
        held = [i for i in p["items"] if i["status"] in HOLDS]
        out[p["key"]] = {
            "errors": len(held),
            "by_category": dict(Counter(i["category"] for i in held).most_common()),
            "by_severity": dict(Counter(i.get("severity", "") for i in held if i.get("severity")).most_common()),
            "not_counted": dict(Counter(i["status"] for i in p["items"] if i["status"] not in HOLDS + ("REPRODUCES",)).most_common()),
            "reproduces": sum(1 for i in p["items"] if i["status"] == "REPRODUCES"),
            "checked": len(p["items"]),
        }
    return out


def render(doc: dict) -> str:
    c = counts(doc)
    L = ["# Errors in the two published papers", "",
         doc["intro"], ""]
    L += ["| Paper | Items checked | Errors that hold | Not counted |", "|---|---:|---:|---|"]
    for p in doc["papers"]:
        k = c[p["key"]]
        nc = ", ".join(f"{n} {s.lower()}" for s, n in k["not_counted"].items()) or "none"
        L.append(f"| {p['title']} ([arXiv:{p['arxiv']}](https://arxiv.org/abs/{p['arxiv']}{p['version']})) | {k['checked']} | {k['errors']} | {nc} |")
    L.append("")
    for p in doc["papers"]:
        k = c[p["key"]]
        L += [f"## {p['title']}", "", p["about"], ""]
        L += ["| Category | Errors |", "|---|---:|"] + [f"| {cat} | {n} |" for cat, n in k["by_category"].items()] + [""]
        for cat in k["by_category"]:
            L += [f"### {cat}", ""]
            for i in (x for x in p["items"] if x["status"] in HOLDS and x["category"] == cat):
                sev = f" · {i['severity']}" if i.get("severity") else ""
                L.append(f"- **{i['id']}{sev}.** {i['statement']}")
                if i.get("quote"):
                    L.append(f"  The paper: \"{i['quote']}\"")
                L.append(f"  *Checked:* {i['evidence']}")
            L.append("")
        ok = [x for x in p["items"] if x["status"] == "REPRODUCES"]
        if ok:
            L += ["### What reproduces", ""]
            L += [f"- {i['note']}" for i in ok] + [""]
        rest = [x for x in p["items"] if x["status"] not in HOLDS + ("REPRODUCES",)]
        if rest:
            L += ["### Not counted as errors, and why", ""]
            for i in rest:
                L.append(f"- **{i['id']}** ({WHY_NOT[i['status']]}). {i['note']}")
            L.append("")
    L += [doc["method"], ""]
    return "\n".join(L)


def main() -> int:
    doc = json.loads(SRC.read_text(encoding="utf-8"))
    OUT.write_text(render(doc), encoding="utf-8")
    for key, k in counts(doc).items():
        print(key, f"{k['errors']} errors of {k['checked']} checked;", k["by_category"], "| not counted:", k["not_counted"])
    print("wrote", OUT)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
