"""The build: every reported number is computed here, from the corpus, in one call.

No count may be claimed unless a build printed it in the same call that wrote it
(the build-in-same-call gate). ``build()`` returns a stats document stamped with
the sha256 of every input; ``STATS.md`` and the charts are rendered from that
document, never typed.
"""
from __future__ import annotations

import hashlib
import json
import statistics
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Iterable

from .model import ASSISTANT, SEVERITY_DIMS, Conversation, Entry, LedgerRow, Severity

SUBSTANTIVE_CHARS = 800  # the audit's split between substantive and short replies


def sha256_file(path: str | Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_path(path: str | Path) -> str:
    """A file's sha256, or for a directory the sha256 of its sorted (name, file sha256) lines."""
    p = Path(path)
    if p.is_file():
        return sha256_file(p)
    lines = "".join(f"{f.relative_to(p).as_posix()} {sha256_file(f)}\n" for f in sorted(p.rglob("*")) if f.is_file())
    return hashlib.sha256(lines.encode("utf-8")).hexdigest()


def gini(values: list[int]) -> float:
    v = sorted(values)
    n, s = len(v), sum(v)
    if n == 0 or s == 0:
        return 0.0
    cum = sum((i + 1) * x for i, x in enumerate(v))
    return (2 * cum) / (n * s) - (n + 1) / n


def _pct(a: int, b: int) -> float:
    return round(100 * a / b, 1) if b else 0.0


def corpus_stats(entries: list[Entry], codebook=None) -> dict[str, Any]:
    by_class = Counter(e.category for e in entries)
    by_driver = Counter(e.driver for e in entries)
    tagset = set(codebook.tags) if codebook else None
    patterns = tuple(codebook.data.get("tag_patterns", [])) if codebook else ()
    by_tag = Counter(t for e in entries for t in e.tags
                     if tagset is None or t in tagset or (patterns and t.startswith(patterns)))
    sev_dims: dict[str, Counter] = {d: Counter() for d in SEVERITY_DIMS}
    totals: Counter = Counter()
    class_dim_mean: dict[str, dict[str, float]] = {}
    per_class: dict[str, list[Severity]] = defaultdict(list)
    for e in entries:
        s = Severity.parse(e.severity)
        for d in SEVERITY_DIMS:
            sev_dims[d][getattr(s, d)] += 1
        totals[s.total] += 1
        per_class[e.category].append(s)
    for c, sevs in per_class.items():
        class_dim_mean[c] = {d: round(statistics.mean(getattr(s, d) for s in sevs), 2) for d in SEVERITY_DIMS}
    xtab: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for e in entries:
        xtab[e.category][e.driver] += 1
    sites = Counter(e.site for e in entries)
    per_conv = Counter(e.conv_id for e in entries)
    loads = sorted(per_conv.values(), reverse=True)
    top_n = max(1, round(len(loads) / 10))
    return {
        "entries": len(entries),
        "sites": len(sites),
        "conversations_with_entries": len(per_conv),
        "classes_in_use": len(by_class),
        "by_class": dict(by_class.most_common()),
        "by_driver": dict(by_driver.most_common()),
        "by_tag": dict(by_tag.most_common()),
        "severity": {
            "by_dimension": {d: {str(k): sev_dims[d][k] for k in (0, 1, 2)} for d in SEVERITY_DIMS},
            "total_distribution": {str(k): totals[k] for k in sorted(totals)},
            "class_dimension_mean": class_dim_mean,
        },
        "class_x_driver": {c: dict(d) for c, d in xtab.items()},
        "entries_per_site": {str(k): v for k, v in sorted(Counter(sites.values()).items())},
        "concentration": {
            "entries_per_conversation_max": loads[0] if loads else 0,
            "entries_per_conversation_median": statistics.median(loads) if loads else 0,
            "top_decile_conversations": top_n,
            "top_decile_share_pct": _pct(sum(loads[:top_n]), len(entries)),
            "gini": round(gini(loads), 3),
            "loads_desc": loads,
        },
        "quote_anchoring": dict(Counter(e.quote_status or "unchecked" for e in entries).most_common()),
        "model_field": dict(Counter(str(e.provenance.get("_model")) for e in entries if (e.provenance or {}).get("_model")).most_common()),
    }


def rate_stats(entries: list[Entry], convs: dict[str, Conversation], population: dict[str, Any]) -> dict[str, Any]:
    """Rates over a declared population of assistant replies.

    ``population`` is {"conversations": [ids], "windows": {id: [lo, hi]}} where a
    window restricts a partly-swept conversation to the messages actually coded.
    The population and every exclusion from it are declared, never implied.
    """
    ids = population["conversations"]
    windows = population.get("windows", {})
    live_sites = {e.site for e in entries}
    entries_at = Counter(e.site for e in entries)
    total = carrying = subst_total = subst_carrying = all_messages = 0
    affected = 0
    first_positions: list[int] = []
    per_conv_rates: list[float] = []
    per_conv_entries: list[int] = []  # every population conversation, clean ones as 0
    per_conv_share: list[float] = []  # conversations with at least one reply; an empty one has no share
    empty = 0
    for cid in ids:
        c = convs.get(cid)
        if c is None:
            continue
        lo, hi = windows.get(cid, [None, None])
        replies = [m for m in c.messages if m.sender == ASSISTANT
                   and (lo is None or m.index >= lo) and (hi is None or m.index <= hi)]
        all_messages += sum(1 for m in c.messages if (lo is None or m.index >= lo) and (hi is None or m.index <= hi))
        hits = [m for m in replies if (cid, m.index) in live_sites]
        total += len(replies)
        carrying += len(hits)
        per_conv_entries.append(sum(entries_at[(cid, m.index)] for m in replies))
        if replies:
            per_conv_share.append(len(hits) / len(replies))
        else:
            empty += 1
        for m in replies:
            if len(m.text) >= SUBSTANTIVE_CHARS:
                subst_total += 1
                subst_carrying += (cid, m.index) in live_sites
        if hits:
            affected += 1
            per_conv_rates.append(len(hits) / len(replies))
            first_positions.append(next(i for i, m in enumerate(replies, 1) if (cid, m.index) in live_sites))
    n_aff = len(first_positions)
    counted = [n for n in per_conv_entries if n]

    def binned(values, edges, labels):
        return [{"bin": lab, "conversations": sum(1 for v in values if lo_ <= v <= hi_)}
                for (lo_, hi_), lab in zip(edges, labels)]
    return {
        "population_conversations": len(ids),
        "messages": all_messages,
        "assistant_replies": total,
        "failure_carrying_replies": carrying,
        "rate_pct": _pct(carrying, total),
        "one_in": round(total / carrying, 2) if carrying else None,
        "substantive": {"replies": subst_total, "carrying": subst_carrying, "rate_pct": _pct(subst_carrying, subst_total)},
        "short": {"replies": total - subst_total, "carrying": carrying - subst_carrying,
                  "rate_pct": _pct(carrying - subst_carrying, total - subst_total)},
        "affected_conversations": affected,
        "affected_pct": _pct(affected, len(ids)),
        "clean_conversations": len(ids) - affected,
        "empty_conversations": empty,
        "conversations_with_replies": len(per_conv_share),
        "affected_pct_of_conversations_with_replies": _pct(affected, len(per_conv_share)),
        "median_rate_within_affected_pct": round(100 * statistics.median(per_conv_rates), 1) if per_conv_rates else 0.0,
        "mean_rate_within_affected_pct": round(100 * statistics.mean(per_conv_rates), 1) if per_conv_rates else 0.0,
        "mean_rate_conversations_with_replies_pct": round(100 * statistics.mean(per_conv_share), 1) if per_conv_share else 0.0,
        "mean_replies_per_conversation": round(total / len(per_conv_entries), 1) if per_conv_entries else 0.0,
        "entries_in_population": sum(per_conv_entries),
        "mean_entries_per_conversation": round(statistics.mean(per_conv_entries), 2) if per_conv_entries else 0.0,
        "mean_entries_per_affected_conversation": round(statistics.mean(counted), 2) if counted else 0.0,
        "median_entries_per_affected_conversation": statistics.median(counted) if counted else 0,
        "entries_per_failure_reply": round(sum(per_conv_entries) / carrying, 2) if carrying else 0.0,
        "entries_per_conversation_hist": binned(per_conv_entries,
                                                [(0, 0), (1, 1), (2, 3), (4, 7), (8, 15), (16, 31), (32, 10**9)],
                                                ["0", "1", "2-3", "4-7", "8-15", "16-31", "32+"]),
        "share_of_replies_hist": binned([round(100 * s, 6) for s in per_conv_share],
                                        [(0, 0), (1e-9, 10), (10.000001, 25), (25.000001, 50), (50.000001, 75), (75.000001, 100)],
                                        ["none", "up to 10%", "10-25%", "25-50%", "50-75%", "over 75%"]),
        "first_failure_position_hist": binned(first_positions, [(1, 1), (2, 2), (3, 3), (4, 5), (6, 10), (11, 10**9)],
                                              ["1st", "2nd", "3rd", "4th-5th", "6th-10th", "11th+"]),
        "first_failure_at_reply_1_pct": _pct(sum(1 for p in first_positions if p == 1), n_aff),
        "first_failure_within_3_pct": _pct(sum(1 for p in first_positions if p <= 3), n_aff),
        "substantive_threshold_chars": SUBSTANTIVE_CHARS,
    }


def ledger_stats(rows: Iterable[LedgerRow]) -> dict[str, Any]:
    rows = list(rows)
    return {
        "rows": len(rows),
        "by_action": dict(Counter(r.action for r in rows).most_common()),
        "by_rule": dict(Counter(r.rule for r in rows).most_common()),
    }


def stamp(inputs: dict[str, str | Path], codebook=None, built_at: str = "") -> dict[str, Any]:
    return {
        "built_at": built_at,
        "inputs": {name: {"path": str(p), "sha256": sha256_path(p)} for name, p in inputs.items()},
        "codebook": {"version": codebook.version, "sha256": codebook.sha256} if codebook else None,
    }


def _get(doc: dict[str, Any], path: str):
    cur: Any = doc
    for part in path.split("."):
        if isinstance(cur, dict) and part in cur:
            cur = cur[part]
        else:
            return None
    return cur


def compare_expected(stats: dict[str, Any], expected: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Check this build against published figures. A difference is reported, never hidden;
    its explanation travels with it in ``why``."""
    out = []
    for x in expected:
        actual = _get(stats, x["path"])
        out.append({"path": x["path"], "expected": x["value"], "actual": actual, "match": actual == x["value"],
                    "source": x.get("source", ""), "why": x.get("why", "")})
    return out


def write_json(doc: dict[str, Any], path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
