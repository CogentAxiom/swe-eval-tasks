"""Mutation testing for the gates: break each rule in turn; the suite must notice.

A gate that silently stops gating is the failure this system exists to prevent,
so the test suite is itself tested. Each mutant is one textual change to a copy of
the package. A mutant is CAUGHT when the test suite fails against it. Any mutant
that survives is a gap in the tests, and the run exits non-zero.

    py -3 mutation/run_mutants.py            # run all, write MUTATION_REPORT.md
"""
from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# (id, file, original text, mutated text, what the mutant breaks)
MUTANTS = [
    ("quote-any", "auditkit/gates.py", "if quote and quote in text:\n        return EXACT", "if quote:\n        return EXACT", "quote gate: any non-empty quote counts as exact"),
    ("quote-accept-all", "auditkit/gates.py", "accept: tuple[str, ...] = (EXACT,)) -> GateResult:", "accept: tuple[str, ...] = (EXACT, NORMALIZED, PIECEWISE)) -> GateResult:", "quote gate: normalized and piecewise accepted by default"),
    ("quote-whole-conversation", "auditkit/gates.py", "e.quote_status = quote_status(e.quote, m.text)", "e.quote_status = quote_status(e.quote, \"\\n\".join(x.text for x in c.messages))", "quote gate: matched anywhere in the conversation, not at the entry's message"),
    ("normalize-keeps-markdown", "auditkit/gates.py", 'for mark in ("**", "*", "__", "`"):', "for mark in ():", "normalisation: markdown marks no longer removed"),
    ("piecewise-unordered", "auditkit/gates.py", "i = nt.find(p, pos)", "i = nt.find(p)", "piecewise: fragments accepted out of order"),
    ("piecewise-short-fragments", "auditkit/gates.py", "MIN_FRAGMENT = 25", "MIN_FRAGMENT = 1", "piecewise: short fragments anchor a quote"),
    ("sender-off", "auditkit/gates.py", "if m.sender != ASSISTANT:", "if False:", "sender gate disabled: entries at the user's messages admitted"),
    ("site-msg-off", "auditkit/gates.py", "elif c.message(e.msg) is None:", "elif False:", "site gate: missing messages admitted"),
    ("type-string-msg", "auditkit/gates.py", "if not isinstance(e.msg, int) or isinstance(e.msg, bool):", "if not isinstance(e.msg, (int, str)):", "type gate: string and boolean message numbers admitted"),
    ("codebook-class-off", "auditkit/gates.py", "if codebook.classes.get(e.category) is None:", "if False:", "codebook gate: classes outside the codebook admitted"),
    ("codebook-driver-off", "auditkit/gates.py", "if e.driver not in codebook.drivers:", "if False:", "codebook gate: drivers outside the codebook admitted"),
    ("codebook-tags-off", "auditkit/gates.py", "bad_tags = [t for t in e.tags if t not in codebook.tags and not (patterns and t.startswith(patterns))]", "bad_tags = []", "codebook gate: tags outside the codebook admitted"),
    ("severity-review-v0-off", "auditkit/gates.py", 'elif s.V == 0 and not cls.get("act_class", False):', "elif False:", "severity review: V0 on an assertion class no longer flagged"),
    ("severity-review-zero-off", "auditkit/gates.py", "if s.total == 0:", "if False:", "severity review: all-zero vectors no longer flagged"),
    ("tag-cap-off", "auditkit/gates.py", "if sev is not None and getattr(sev, dim) > top:", "if False:", "codebook gate: a tag's severity cap not enforced"),
    ("tag-pattern-any", "auditkit/gates.py", "not (patterns and t.startswith(patterns))", "not patterns", "codebook gate: any tag admitted when patterns exist"),
    ("provenance-empty-ok", "auditkit/gates.py", "missing = [k for k in required if not e.provenance.get(k)]", "missing = [k for k in required if k not in e.provenance]", "provenance gate: empty provenance values admitted"),
    ("unique-id-off", "auditkit/gates.py", "if e.entry_id in seen:", "if False:", "unique-id gate disabled"),
    ("containment-equal-only", "auditkit/gates.py", "if qa and qb and (qa in qb or qb in qa):", "if qa and qb and qa == qb:", "containment: only identical quotes merge"),
    ("pin-ignores-category", "auditkit/gates.py", ' and e.category in p.get("forbid_categories", []):', ":", "settled pin: forbids every class at the site"),
    ("pin-off", "auditkit/gates.py", "r.violations.append(Violation(\"settled-pin\"", "(lambda *a: None)(Violation(\"settled-pin\"", "settled pin disabled"),
    ("canary-site-only", "auditkit/gates.py", "and (not cats or e.category in cats)", "", "canary: declared classes ignored"),
    ("canary-off", "auditkit/gates.py", "        if not hit:\n", "        if False:\n", "canary gate disabled"),
    ("merge-no-halt", "auditkit/merge.py", "if strict and rejected:", "if False:", "merge: rejections do not halt a strict merge"),
    ("merge-canary-no-halt", "auditkit/merge.py", "    if not canary.passed:\n", "    if False:\n", "merge: a missing canary does not halt"),
    ("merge-canary-before-gates", "auditkit/merge.py", "canary = G.canary_gate(accepted, canaries or [])", "canary = G.canary_gate(entries, canaries or [])", "merge: canaries counted on entries that failed the gates"),
    ("severity-range", "auditkit/model.py", 'r"V([0-2])H([0-2])C([0-2])T([0-2])R([0-2])I([0-2])"', 'r"V([0-3])H([0-3])C([0-3])T([0-3])R([0-3])I([0-3])"', "severity accepts level 3"),
    ("reader-user-alias", "auditkit/transcripts.py", '_SENDER_ALIASES = {"user": HUMAN,', '_SENDER_ALIASES = {"user": "assistant",', "reader: 'user' messages read as assistant"),
    ("rate-window-ignored", "auditkit/build.py", "and (lo is None or m.index >= lo) and (hi is None or m.index <= hi)]", "]", "rate: declared windows ignored"),
    ("gini-wrong", "auditkit/build.py", "return (2 * cum) / (n * s) - (n + 1) / n", "return (2 * cum) / (n * s) - 1", "gini formula broken"),
    ("units-overflow", "auditkit/passes.py", "if size and size + len(m.text) > max_chars:", "if size and size + len(m.text) > max_chars * 2:", "units: a unit may exceed its size budget"),
    ("units-empty-unit", "auditkit/passes.py", "if size and size + len(m.text) > max_chars:", "if size + len(m.text) > max_chars:", "units: an oversize first message opens an empty unit"),
    ("pass0-evidence-off", "auditkit/passes.py", 'if r.evidence_msg is None or c.message(r.evidence_msg) is None:', "if False:", "Pass 0: settled verdicts without evidence admitted"),
    ("tree-cycle-off", "auditkit/tree.py", '            problems.append("cycle: " + " -> ".join(path + [nid]))\n            return', "            return", "tree: cycles not detected"),
    ("codebook-duplicates-ok", "auditkit/codebook.py", "        if k in out:\n            raise", "        if False:\n            raise", "codebook: duplicate keys silently replace earlier definitions"),
    ("codebook-pin-off", "auditkit/codebook.py", "    if pinned != sha:\n", "    if False:\n", "codebook: a changed codebook loads against an old pin"),
    ("codebook-no-pin-ok", "auditkit/codebook.py", "    if not pin_path.exists():\n        raise", "    if False:\n        raise", "codebook: a codebook with no pin loads, skipping the freeze check"),
]


def run_suite(root: Path) -> int:
    return subprocess.run([sys.executable, "-m", "unittest", "discover", "-s", str(root / "tests"), "-q"],
                          cwd=root, capture_output=True, text=True).returncode


def main() -> int:
    if run_suite(ROOT) != 0:
        print("baseline suite fails; fix it before mutation testing")
        return 2
    rows, survived = [], []
    for mid, rel, old, new, what in MUTANTS:
        with tempfile.TemporaryDirectory() as d:
            tmp = Path(d) / "auditkit_mut"
            shutil.copytree(ROOT, tmp, ignore=shutil.ignore_patterns("runs", "__pycache__", "*.pyc", "fixtures"))
            if (ROOT / "fixtures").exists():
                shutil.copytree(ROOT / "fixtures", tmp / "fixtures")
            f = tmp / rel
            src = f.read_text(encoding="utf-8")
            if src.count(old) != 1:
                rows.append((mid, what, f"NOT APPLIED (pattern found {src.count(old)} times)"))
                survived.append(mid)
                continue
            f.write_text(src.replace(old, new), encoding="utf-8")
            caught = run_suite(tmp) != 0
            rows.append((mid, what, "caught" if caught else "SURVIVED"))
            if not caught:
                survived.append(mid)
    lines = ["# Mutation report", "", "Generated by `py -3 mutation/run_mutants.py`. Each mutant breaks one rule in a copy of the package;",
             "the test suite must fail against it.", "",
             f"**{len(rows) - len(survived)} of {len(rows)} mutants caught.**", "", "| Mutant | What it breaks | Result |", "|---|---|---|"]
    lines += [f"| `{m}` | {w} | {r} |" for m, w, r in rows]
    (ROOT / "mutation" / "MUTATION_REPORT.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    for m, w, r in rows:
        print(f"{r:10s} {m:28s} {w}")
    print(f"{len(rows) - len(survived)} of {len(rows)} caught")
    return 1 if survived else 0


if __name__ == "__main__":
    sys.exit(main())
