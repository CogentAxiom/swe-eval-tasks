"""Command line: python -m auditkit <command> ...

  codebook validate|pin|render   check, pin, or regenerate CODEBOOK.md
  gate     run every per-entry gate over a corpus and print the report
  merge    gate coder batches into a corpus, or refuse
  build    compute every statistic, write stats.json, STATS.md and charts
  tree     render the decision tree (Markdown with a Mermaid diagram)
  selftest run the synthetic fixture end to end

Exit status is non-zero whenever a gate refuses, so the commands compose in CI.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import build as B
from . import codebook as CB
from . import gates as G
from . import merge as M
from . import render as R
from .model import Entry, LedgerRow
from .transcripts import load_conversations

HERE = Path(__file__).resolve().parent.parent
DEFAULT_CODEBOOK = HERE / "codebook" / "codebook.json"


def _load_corpus(fmt: str, path: str):
    if fmt == "merged_v12":
        from .adapters import merged_v12
        entries, doc = merged_v12.load(path)
        return entries, merged_v12.strike_ledger(doc)
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    entries = [Entry.from_json(d) for d in doc["entries"]]
    ledger = [LedgerRow(**r) for r in doc.get("ledger", [])]
    return entries, ledger


def _accept(spec: str) -> tuple[str, ...]:
    allowed = {G.EXACT, G.NORMALIZED, G.PIECEWISE}
    vals = tuple(s.strip() for s in spec.split(",") if s.strip())
    bad = [v for v in vals if v not in allowed]
    if bad:
        raise SystemExit(f"unknown quote level(s) {bad}; choose from {sorted(allowed)}")
    return vals


def cmd_codebook(a) -> int:
    if a.action == "pin":
        print("pinned", CB.write_pin(a.codebook))
        return 0
    cb = CB.load(a.codebook)
    print(f"OK codebook {cb.version}: {len(cb.classes)} classes, {len(cb.drivers)} drivers, {len(cb.tags)} tags, "
          f"{len(cb.protections)} protections; sha256 {cb.sha256}")
    if a.action == "render":
        out = Path(a.codebook).with_name("CODEBOOK.md")
        out.write_text(R.codebook_md(cb), encoding="utf-8")
        print("wrote", out)
    return 0


def cmd_gate(a) -> int:
    entries, _ = _load_corpus(a.format, a.corpus)
    convs = load_conversations(a.convs)
    cb = CB.load(a.codebook) if a.codebook else None
    results = [G.type_gate(entries), G.site_gate(entries, convs), G.sender_gate(entries, convs),
               G.quote_gate(entries, convs, accept=_accept(a.accept)), G.unique_id_gate(entries), G.containment_gate(entries)]
    if cb:
        results.append(G.codebook_gate(entries, cb))
    worst = 0
    for r in results:
        print(f"{r.gate:12s} checked {r.checked:6d}  violations {len(r.violations):5d}")
        for v in r.violations[: a.show]:
            print(f"    {v.entry_id}: {v.detail}")
        worst = worst or (1 if r.violations else 0)
    from collections import Counter
    print("quote anchoring:", dict(Counter(e.quote_status for e in entries)))
    return worst


def cmd_merge(a) -> int:
    entries = M.load_coder_outputs(a.batches)
    convs = load_conversations(a.convs)
    cb = CB.load(a.codebook)
    canaries = json.loads(Path(a.canaries).read_text(encoding="utf-8")) if a.canaries else []
    pins = json.loads(Path(a.pins).read_text(encoding="utf-8")) if a.pins else []
    res = M.merge(entries, convs, cb, canaries, pins, accept_quotes=_accept(a.accept), strict=not a.lenient)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "merge_report.json").write_text(json.dumps(res.report(), indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in res.report().items() if k not in ("rejections",)}, indent=2)[:4000])
    if res.halted:
        print("MERGE HALTED:", "; ".join(res.halt_reasons))
        return 2
    (out / "corpus.json").write_text(json.dumps({"codebook": {"version": cb.version, "sha256": cb.sha256},
                                                 "entries": [e.to_json() for e in res.accepted]}, indent=1, ensure_ascii=False), encoding="utf-8")
    print("wrote", out / "corpus.json", len(res.accepted), "entries")
    return 0


def cmd_build(a) -> int:
    entries, ledger = _load_corpus(a.format, a.corpus)
    convs = load_conversations(a.convs)
    cb = CB.load(a.codebook) if a.codebook and Path(a.codebook).exists() else None
    gate_results = [G.type_gate(entries), G.site_gate(entries, convs), G.sender_gate(entries, convs),
                    G.quote_gate(entries, convs, accept=_accept(a.accept)), G.unique_id_gate(entries), G.containment_gate(entries)]
    if cb:
        gate_results.append(G.codebook_gate(entries, cb))
    if a.canaries:
        gate_results.append(G.canary_gate(entries, json.loads(Path(a.canaries).read_text(encoding="utf-8"))))
    inputs = {"corpus": a.corpus, "conversations": a.convs}
    stats = {"label": a.label, "stamp": B.stamp(inputs, cb, a.built_at), "corpus": B.corpus_stats(entries, cb),
             "gates": [{"gate": r.gate, "checked": r.checked, "violations": len(r.violations),
                        "detail": [] if a.public else [v.__dict__ for v in r.violations[:200]]} for r in gate_results]}
    stats["corpus"]["conv_id_repairs"] = sum(1 for e in entries if "conv_id_raw" in (e.provenance or {}))
    if a.public:
        for v in stats["stamp"]["inputs"].values():
            v["path"] = Path(v["path"]).name
    if a.population:
        stats["rate"] = B.rate_stats(entries, convs, json.loads(Path(a.population).read_text(encoding="utf-8")))
    if ledger:
        stats["ledger"] = B.ledger_stats(ledger)
    if a.notes:
        stats["notes"] = json.loads(Path(a.notes).read_text(encoding="utf-8"))
    if a.expect:
        stats["reproduction"] = B.compare_expected(stats, json.loads(Path(a.expect).read_text(encoding="utf-8")))
    out = Path(a.out)
    B.write_json(stats, out / "stats.json")
    files = R.chart_set(stats, out / "charts", a.label)
    (out / "STATS.md").write_text(R.stats_md(stats, a.label, "charts", files), encoding="utf-8")
    c = stats["corpus"]
    print(f"BUILD {a.label}: {c['entries']} entries, {c['sites']} sites, {c['classes_in_use']} classes")
    if "rate" in stats:
        r = stats["rate"]
        print(f"RATE  {r['failure_carrying_replies']}/{r['assistant_replies']} = {r['rate_pct']}% (one in {r['one_in']})")
    for g in stats["gates"]:
        print(f"GATE  {g['gate']:12s} checked {g['checked']:6d} violations {g['violations']}")
    for x in stats.get("reproduction", []):
        print(f"REPRO {'MATCH ' if x['match'] else 'DIFFER'} {x['path']}: expected {x['expected']} ({x['source']}), built {x['actual']}")
    print("wrote", out / "stats.json", out / "STATS.md", out / "charts")
    return 0


def cmd_tree(a) -> int:
    from .tree import render_markdown, validate_tree
    doc = json.loads(Path(a.tree).read_text(encoding="utf-8"))
    cb = json.loads(Path(a.codebook).read_text(encoding="utf-8")) if a.codebook and Path(a.codebook).exists() else None
    problems = validate_tree(doc, cb)
    if problems:
        print("TREE INVALID:\n  " + "\n  ".join(problems))
        return 1
    out = Path(a.out)
    out.write_text(render_markdown(doc), encoding="utf-8")
    print("wrote", out)
    return 0


def cmd_selftest(a) -> int:
    from .selftest import run
    return run(verbose=a.verbose)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="auditkit", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("codebook")
    s.add_argument("action", choices=["validate", "pin", "render"])
    s.add_argument("--codebook", default=str(DEFAULT_CODEBOOK))
    s.set_defaults(fn=cmd_codebook)

    for name, fn in (("gate", cmd_gate), ("build", cmd_build)):
        s = sub.add_parser(name)
        s.add_argument("--corpus", required=True)
        s.add_argument("--format", choices=["auditkit", "merged_v12"], default="auditkit")
        s.add_argument("--convs", required=True, help="directory of conversation text files, or a JSON bundle")
        s.add_argument("--codebook", default=str(DEFAULT_CODEBOOK))
        s.add_argument("--accept", default="exact", help="quote anchoring levels the gate accepts, comma-separated")
        s.set_defaults(fn=fn)
        if name == "gate":
            s.add_argument("--show", type=int, default=10)
        else:
            s.add_argument("--population", help="JSON: {conversations: [...], windows: {id: [lo, hi]}}")
            s.add_argument("--notes", help="JSON list of notes to carry into STATS.md")
            s.add_argument("--label", required=True)
            s.add_argument("--out", required=True)
            s.add_argument("--built-at", default="")
            s.add_argument("--canaries", help="JSON list of canaries to check against the live entries")
            s.add_argument("--expect", help="JSON list of {path, value, source}: published figures this build must reproduce or explain")
            s.add_argument("--public", action="store_true", help="omit violation details and local paths from the output")

    s = sub.add_parser("merge")
    s.add_argument("--batches", nargs="+", required=True)
    s.add_argument("--convs", required=True)
    s.add_argument("--codebook", default=str(DEFAULT_CODEBOOK))
    s.add_argument("--canaries")
    s.add_argument("--pins")
    s.add_argument("--accept", default="exact")
    s.add_argument("--lenient", action="store_true", help="return rejections without halting (never hides canary failures)")
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_merge)

    s = sub.add_parser("tree")
    s.add_argument("--tree", default=str(HERE / "codebook" / "decision_tree.json"))
    s.add_argument("--codebook", default=str(DEFAULT_CODEBOOK), help="protected/register terminal refs must resolve to its keys")
    s.add_argument("--out", default=str(HERE / "codebook" / "DECISION_TREE.md"))
    s.set_defaults(fn=cmd_tree)

    s = sub.add_parser("selftest")
    s.add_argument("--verbose", action="store_true")
    s.set_defaults(fn=cmd_selftest)

    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
