"""The merge: coder output in, gated corpus out, or a refusal.

Order matters and is fixed:

1. per-entry gates (type, site, sender, quote, codebook, provenance, unique id,
   settled pins). A failing entry never enters the corpus; it goes back to its
   coder on the rejection list, with the gate and the reason.
2. containment: the same failure differently quoted is a merge candidate for a
   person, never silently dropped.
3. the canary gate, on what survived. One missing canary halts the merge: an
   incomplete merge may not report totals.
4. note-vs-label candidates are listed for adjudication; they never purge.

A merge that halts writes its report and no corpus.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import gates as G
from .model import Conversation, Entry

PER_ENTRY_GATES = ("type", "site", "sender", "quote", "codebook", "provenance", "unique-id", "settled-pin")


@dataclass
class MergeResult:
    accepted: list[Entry]
    rejected: list[dict[str, Any]]
    gate_results: list[G.GateResult]
    containment: list[G.Violation]
    canary: G.GateResult
    review_candidates: list[G.Violation]
    halted: bool
    halt_reasons: list[str] = field(default_factory=list)

    def report(self) -> dict[str, Any]:
        return {
            "halted": self.halted,
            "halt_reasons": self.halt_reasons,
            "accepted": len(self.accepted),
            "rejected": len(self.rejected),
            "gates": [{"gate": g.gate, "checked": g.checked, "violations": len(g.violations)} for g in self.gate_results],
            "containment_candidates": [v.__dict__ for v in self.containment],
            "canary": {"checked": self.canary.checked, "missing": [v.__dict__ for v in self.canary.violations]},
            "review_candidates": [v.__dict__ for v in self.review_candidates],
            "rejections": self.rejected,
        }


def merge(entries: list[Entry], convs: dict[str, Conversation], codebook, canaries: list[dict] | None = None,
          pins: list[dict] | None = None, accept_quotes: tuple[str, ...] = (G.EXACT,),
          strict: bool = True) -> MergeResult:
    """Run every gate. ``strict`` halts on any rejection; otherwise rejections are returned and the rest proceeds."""
    results = [
        G.type_gate(entries),
        G.site_gate(entries, convs),
        G.sender_gate(entries, convs),
        G.quote_gate(entries, convs, accept=accept_quotes),
        G.codebook_gate(entries, codebook),
        G.provenance_gate(entries),
        G.unique_id_gate(entries),
        G.settled_pin_gate(entries, pins or []),
    ]
    failures: dict[str, list[G.Violation]] = {}
    for r in results:
        for v in r.violations:
            failures.setdefault(v.entry_id, []).append(v)
    accepted = [e for e in entries if e.entry_id not in failures]
    rejected = [{"entry_id": eid, "violations": [{"gate": v.gate, "detail": v.detail} for v in vs]}
                for eid, vs in failures.items()]
    containment = G.containment_gate(accepted).violations
    canary = G.canary_gate(accepted, canaries or [])
    review = G.note_label_candidates(accepted) + G.severity_candidates(accepted, codebook)
    halt = []
    if strict and rejected:
        halt.append(f"{len(rejected)} entries failed per-entry gates")
    if not canary.passed:
        halt.append(f"{len(canary.violations)} canaries missing: the merge is incomplete and may not report totals")
    return MergeResult(accepted, rejected, results, containment, canary, review, bool(halt), halt)


def load_coder_outputs(paths: list[str | Path]) -> list[Entry]:
    """Coder batch files: {"batch": id, "coder": model, "pass": id, "entries": [...]}."""
    out: list[Entry] = []
    for p in paths:
        doc = json.loads(Path(p).read_text(encoding="utf-8"))
        for d in doc["entries"]:
            e = Entry.from_json(d)
            e.provenance = {"pass": doc.get("pass", ""), "coder": doc.get("coder", ""), "batch": doc.get("batch", ""), **(e.provenance or {})}
            out.append(e)
    return out
