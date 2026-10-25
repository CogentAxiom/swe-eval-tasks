"""End-to-end selftest on the synthetic fixture.

Every batch in ``fixtures/synthetic`` goes through the real merge with the real,
pinned codebook. ``expected.json`` states what each batch must produce: the gold
batch merges clean; each defective batch is refused by the gate it targets and
by no other; a missing canary halts the merge.
"""
from __future__ import annotations

import json
from pathlib import Path

from . import codebook as CB
from . import merge as M
from .model import Pass0Row
from .passes import validate_pass0
from .transcripts import read_conversation_dir

ROOT = Path(__file__).resolve().parent.parent
FX = ROOT / "fixtures" / "synthetic"


def check_batch(name: str, exp: dict, convs, cb, canaries, pins) -> list[str]:
    entries = M.load_coder_outputs([FX / f"{name}.json"])
    res = M.merge(entries, convs, cb, canaries, pins)
    problems = []
    if res.halted != exp["halted"]:
        problems.append(f"{name}: halted={res.halted}, expected {exp['halted']} ({res.halt_reasons})")
    got_rej = sorted(r["entry_id"] for r in res.rejected)
    if got_rej != sorted(exp.get("rejected_ids", [])):
        problems.append(f"{name}: rejected {got_rej}, expected {sorted(exp.get('rejected_ids', []))}")
    got_gates = sorted({v["gate"] for r in res.rejected for v in r["violations"]}
                       | ({"containment"} if res.containment else set())
                       | ({"canary"} if res.canary.violations else set()))
    if got_gates != sorted(exp.get("gates", [])):
        problems.append(f"{name}: gates {got_gates}, expected {sorted(exp.get('gates', []))}")
    got_cont = sorted(v.entry_id for v in res.containment)
    if got_cont != sorted(exp.get("containment", [])):
        problems.append(f"{name}: containment {got_cont}, expected {sorted(exp.get('containment', []))}")
    got_can = sorted(v.entry_id for v in res.canary.violations)
    if got_can != sorted(exp.get("canary_missing", [])):
        problems.append(f"{name}: canaries missing {got_can}, expected {sorted(exp.get('canary_missing', []))}")
    return problems


def run(verbose: bool = False) -> int:
    if not FX.exists():
        print("no fixture at", FX)
        return 2
    cb = CB.load(ROOT / "codebook" / "codebook.json")
    convs = read_conversation_dir(FX / "convs")
    canaries = json.loads((FX / "canaries.json").read_text(encoding="utf-8"))
    pins = json.loads((FX / "pins.json").read_text(encoding="utf-8"))
    expected = json.loads((FX / "expected.json").read_text(encoding="utf-8"))
    problems: list[str] = []
    rows = [Pass0Row(**r) for r in json.loads((FX / "pass0.json").read_text(encoding="utf-8"))]
    problems += [f"pass0: {p}" for p in validate_pass0(rows, convs)]
    for name, exp in sorted(expected.items()):
        name = name[:-5] if name.endswith(".json") else name
        found = check_batch(name, exp, convs, cb, canaries, pins)
        problems += found
        if verbose:
            print(f"{'ok  ' if not found else 'FAIL'} {name}")
    print(f"selftest: {len(expected)} batches, {len(problems)} problems")
    for p in problems:
        print("  " + p)
    return 1 if problems else 0
