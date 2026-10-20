"""Read the original audit's corpus file (MERGED_V12.json) into Entries.

The original file carries the audit's whole provenance trail in underscore
fields. This adapter maps the fields the system needs and keeps the rest under
``provenance`` untouched, so nothing is lost in translation.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from ..model import Entry, LedgerRow

_SESSION_SUFFIX = re.compile(r"_s\d+$")


def base_conv_id(wid: str) -> str:
    """The original build keyed every site on the base conversation id: a unit id
    such as ``wNNN_sMM`` names a slice of ``wNNN``, not another conversation."""
    return _SESSION_SUFFIX.sub("", wid)

# The codebook's six tags, the three erroneous-claim shape tags, plus instructed:<clause>. Every other tag in the original
# file records which pass touched an entry; it is provenance, not a modifier, and is
# kept as such.
CODEBOOK_TAGS = {"self-referential", "standing-repair", "institution-favourable", "instrumental", "quantifier-overreach", "user-deference",
                 "shape:strictly-unknowable", "shape:unfounded", "shape:unverified-certified"}
TAG_PATTERNS = ("instructed:",)


def is_codebook_tag(t: str) -> bool:
    return t in CODEBOOK_TAGS or t.startswith(TAG_PATTERNS)

STRIKE_LEDGERS = {
    "struck_confession_convictions": "confession-conviction",
    "struck_protection_applied": "protection-applied",
    "struck_label_hygiene": "label-hygiene",
    "struck_failed_verification": "failed-verification",
    "struck_pending_review": "pending-review",
}


def load(path: str | Path) -> tuple[list[Entry], dict[str, Any]]:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    entries: list[Entry] = []
    for i, e in enumerate(doc["entries"]):
        tags = list(e.get("tags") or [])
        prov = {k: v for k, v in e.items() if k.startswith("_") and k not in ("_wid", "_driver", "_tid")}
        prov["pass"] = e.get("_batch", "")
        prov["coder"] = "fleet:" + str(e.get("_batch", ""))
        prov["process_tags"] = [t for t in tags if not is_codebook_tag(t)]
        if base_conv_id(e["_wid"]) != e["_wid"]:
            prov["conv_id_raw"] = e["_wid"]
        entries.append(Entry(
            entry_id=e.get("_tid") or f"untid-{i}",
            conv_id=base_conv_id(e["_wid"]),
            msg=e["msg"],
            category=e["category"],
            driver=e.get("_driver", ""),
            severity=e["severity"],
            quote=e["quote"],
            note=e.get("note", ""),
            tags=[t for t in tags if is_codebook_tag(t)],
            provenance=prov,
        ))
    return entries, doc


def strike_ledger(doc: dict[str, Any]) -> list[LedgerRow]:
    rows: list[LedgerRow] = []
    for key, rule in STRIKE_LEDGERS.items():
        for i, r in enumerate(doc.get(key) or []):
            struck = r.get("_struck") or {}
            rows.append(LedgerRow(
                entry_id=r.get("_tid") or f"{key}-{i}",
                action="struck",
                reason=str(struck.get("reason") or r.get("reason") or ""),
                rule=rule,
                pass_id=str(struck.get("pass") or key),
                detail={"category": r.get("category"), "conv_id": r.get("_wid") or r.get("wid"), "msg": r.get("msg")},
            ))
    return rows
