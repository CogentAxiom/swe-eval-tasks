"""Mechanical gates. Each gate is a pure function that returns violations.

A rule that exists only as text an agent reads does not reliably execute. A gate
is a rule that can block the output: the merge refuses while any gate reports a
violation. Gates never rewrite an entry; they report, and the merge decides.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Iterable

from .model import ASSISTANT, Conversation, Entry, Severity

EXACT, NORMALIZED, PIECEWISE, ABSENT = "exact", "normalized", "piecewise", "absent"
_WS = re.compile(r"\s+")


@dataclass
class Violation:
    gate: str
    entry_id: str
    detail: str


@dataclass
class GateResult:
    gate: str
    checked: int
    violations: list[Violation] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.violations


def _ws(s: str) -> str:
    return _WS.sub(" ", s).strip()


_TYPO = str.maketrans({"‘": "'", "’": "'", "“": '"', "”": '"', "–": "-", "—": "-"})


def normalize(s: str) -> str:
    """The original audit's normalisation, reproduced exactly: typographic quotes and
    dashes to ASCII, the ellipsis character to '...', markdown emphasis and code
    marks removed (``**``, ``*``, ``__``, backtick), whitespace runs collapsed."""
    s = (s or "").translate(_TYPO).replace("…", "...")
    for mark in ("**", "*", "__", "`"):
        s = s.replace(mark, "")
    return _WS.sub(" ", s).strip()


_FRAGMENT_SPLIT = re.compile(r"\[\.\.\.\]|\.\.\.|\n")
MIN_FRAGMENT = 25


def quote_status(quote: str, text: str) -> str:
    """Classify how a quote is anchored in its own message.

    exact      -- a contiguous, character-for-character substring;
    normalized -- a substring once both sides are normalised (``normalize``);
    piecewise  -- split at ellipses and line breaks, every fragment of at least 25
                  characters occurs, normalised, in order;
    absent     -- none of the above.

    The original audit matched against the whole conversation file. This gate
    matches against the one message the entry names, which is stricter: a quote
    that exists elsewhere in the conversation but not at its site is absent here.
    """
    if quote and quote in text:
        return EXACT
    nq, nt = normalize(quote), normalize(text)
    if nq and nq in nt:
        return NORMALIZED
    parts = [normalize(p) for p in _FRAGMENT_SPLIT.split(quote or "")]
    parts = [p for p in parts if len(p) >= MIN_FRAGMENT]
    if parts:
        pos = 0
        for p in parts:
            i = nt.find(p, pos)
            if i < 0:
                return ABSENT
            pos = i + len(p)
        return PIECEWISE
    return ABSENT


def site_gate(entries: Iterable[Entry], convs: dict[str, Conversation]) -> GateResult:
    """The conversation and message exist."""
    r = GateResult("site", 0)
    for e in entries:
        r.checked += 1
        c = convs.get(e.conv_id)
        if c is None:
            r.violations.append(Violation("site", e.entry_id, f"conversation {e.conv_id!r} not in record"))
        elif c.message(e.msg) is None:
            r.violations.append(Violation("site", e.entry_id, f"{e.conv_id} has no message {e.msg}"))
    return r


def sender_gate(entries: Iterable[Entry], convs: dict[str, Conversation]) -> GateResult:
    """Every entry sits at an assistant message, read from the raw sender field.

    The user's messages are never entries. (An early ledger logged 205 of the
    user's own messages as model failures because a rendering mislabeled them.)
    """
    r = GateResult("sender", 0)
    for e in entries:
        c = convs.get(e.conv_id)
        m = c.message(e.msg) if c else None
        if m is None:
            continue  # site gate reports it
        r.checked += 1
        if m.sender != ASSISTANT:
            r.violations.append(Violation("sender", e.entry_id, f"{e.conv_id} msg {e.msg} sender is {m.sender!r}"))
    return r


def quote_gate(entries: Iterable[Entry], convs: dict[str, Conversation], accept: tuple[str, ...] = (EXACT,)) -> GateResult:
    """The quote is anchored in its own message. Sets ``entry.quote_status``.

    The default accepts exact substrings only. Accepting normalized or piecewise
    anchoring is an explicit, recorded choice, never a silent fallback.
    """
    r = GateResult("quote", 0)
    for e in entries:
        c = convs.get(e.conv_id)
        m = c.message(e.msg) if c else None
        if m is None:
            continue
        r.checked += 1
        e.quote_status = quote_status(e.quote, m.text)
        if e.quote_status not in accept:
            r.violations.append(Violation("quote", e.entry_id, f"quote is {e.quote_status} at {e.conv_id} msg {e.msg}: {e.quote[:80]!r}"))
    return r


def type_gate(entries: Iterable[Entry]) -> GateResult:
    """Field types are what downstream counting assumes.

    Four string-typed message numbers once held a headline count three low.
    """
    r = GateResult("type", 0)
    for e in entries:
        r.checked += 1
        problems = []
        if not isinstance(e.msg, int) or isinstance(e.msg, bool):
            problems.append(f"msg is {type(e.msg).__name__}")
        for name in ("entry_id", "conv_id", "category", "driver", "severity", "quote", "note"):
            if not isinstance(getattr(e, name), str) or not getattr(e, name):
                problems.append(f"{name} missing or not a string")
        if not isinstance(e.tags, list):
            problems.append("tags is not a list")
        if problems:
            r.violations.append(Violation("type", e.entry_id, "; ".join(problems)))
    return r


def codebook_gate(entries: Iterable[Entry], codebook) -> GateResult:
    """Class, driver and tags are drawn from the pinned codebook; the severity vector parses and
    respects every cap its tags declare (``cap`` in the tag's definition).

    Tags may also match a declared pattern (``tag_patterns`` in the codebook, e.g.
    ``instructed:<clause>``).
    """
    patterns = tuple(codebook.data.get("tag_patterns", [])) if getattr(codebook, "data", None) else ()
    r = GateResult("codebook", 0)
    for e in entries:
        r.checked += 1
        problems = []
        if codebook.classes.get(e.category) is None:
            problems.append(f"class {e.category!r} not in codebook {codebook.version}")
        if e.driver not in codebook.drivers:
            problems.append(f"driver {e.driver!r} not in codebook")
        bad_tags = [t for t in e.tags if t not in codebook.tags and not (patterns and t.startswith(patterns))]
        if bad_tags:
            problems.append(f"tags not in codebook: {bad_tags}")
        try:
            sev = Severity.parse(e.severity)
        except ValueError as exc:
            problems.append(str(exc))
            sev = None
        for t in e.tags:
            for dim, top in ((codebook.tags.get(t) or {}).get("cap") or {}).items():
                if sev is not None and getattr(sev, dim) > top:
                    problems.append(f"tag {t!r} caps {dim} at {top}; the entry has {dim}{getattr(sev, dim)}")
        if problems:
            r.violations.append(Violation("codebook", e.entry_id, "; ".join(problems)))
    return r


def severity_candidates(entries: Iterable[Entry], codebook) -> list[Violation]:
    """Vectors a person should re-examine; never a rejection.

    An all-zero vector is a flag to re-examine the category. V0 means there is no
    truth claim in the output to assess (the defect is an act); on a class defined
    by an asserted proposition it is usually, not always, a misreading.
    """
    out = []
    for e in entries:
        try:
            s = Severity.parse(e.severity)
        except ValueError:
            continue
        cls = codebook.classes.get(e.category) or {}
        if s.total == 0:
            out.append(Violation("severity-review", e.entry_id, "all-zero vector: re-examine the category"))
        elif s.V == 0 and not cls.get("act_class", False):
            out.append(Violation("severity-review", e.entry_id, f"V0 on {e.category}, a class defined by an asserted proposition"))
    return out


def provenance_gate(entries: Iterable[Entry], required: tuple[str, ...] = ("pass", "coder")) -> GateResult:
    """Every entry carries the pass and coder that produced it. Prior labels are prior, never authority."""
    r = GateResult("provenance", 0)
    for e in entries:
        r.checked += 1
        missing = [k for k in required if not e.provenance.get(k)]
        if missing:
            r.violations.append(Violation("provenance", e.entry_id, f"missing provenance: {missing}"))
    return r


def unique_id_gate(entries: Iterable[Entry]) -> GateResult:
    r = GateResult("unique-id", 0)
    seen: set[str] = set()
    for e in entries:
        r.checked += 1
        if e.entry_id in seen:
            r.violations.append(Violation("unique-id", e.entry_id, "duplicate entry id"))
        seen.add(e.entry_id)
    return r


def containment_gate(entries: list[Entry]) -> GateResult:
    """The same failure, differently quoted, merges.

    Two entries at the same site and class where one quote contains the other are
    one failure counted twice. Different claims in one message are distinct
    entries and pass.
    """
    r = GateResult("containment", 0)
    groups: dict[tuple, list[Entry]] = {}
    for e in entries:
        groups.setdefault((e.conv_id, e.msg, e.category), []).append(e)
    for group in groups.values():
        r.checked += len(group)
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                qa, qb = _ws(a.quote), _ws(b.quote)
                if qa and qb and (qa in qb or qb in qa):
                    r.violations.append(Violation("containment", b.entry_id, f"same site and class as {a.entry_id}, quote contained"))
    return r


def settled_pin_gate(entries: Iterable[Entry], pins: list[dict]) -> GateResult:
    """Adjudicated questions are not relitigated by a coder or verifier.

    A pin names a site and the adjudicated verdict; an entry that convicts what a
    pin has settled as true is refused. Pin shape:
    {"conv_id", "msg", "forbid_categories": [...], "ruling": "..."}.
    """
    r = GateResult("settled-pin", 0)
    for e in entries:
        r.checked += 1
        for p in pins:
            if p["conv_id"] == e.conv_id and p["msg"] == e.msg and e.category in p.get("forbid_categories", []):
                r.violations.append(Violation("settled-pin", e.entry_id, f"relitigates a settled ruling: {p.get('ruling', '')}"))
    return r


_CONCEDES = re.compile(
    r"\b(?:not (?:a|an) (?:error|failure)|is (?:true|correct|accurate)|was (?:true|correct|accurate)|no false|nothing false|accurate statement|true statement)\b",
    re.I,
)


def note_label_candidates(entries: Iterable[Entry]) -> list[Violation]:
    """Entries whose own note concedes the act was not a failure.

    A candidate finder, never an automatic purge: each candidate goes to a person.
    """
    return [Violation("note-vs-label", e.entry_id, f"note may concede no failure: {m.group(0)!r}")
            for e in entries if (m := _CONCEDES.search(e.note or ""))]


def canary_gate(entries: Iterable[Entry], canaries: list[dict]) -> GateResult:
    """Known findings seeded through the corpus must all survive the merge.

    A canary is {"canary_id", "conv_id", "msg"} with an optional "categories" list
    and an optional "quote_contains". It is matched by a live entry at that site
    (and, when given, of one of those classes, with a quote containing that text).
    One missing canary halts the merge: an incomplete merge cannot report totals.

    The original audit matched canaries on site alone, against a pool that included
    escalations and unmerged sweep items, after the corpus had been written. This
    gate matches live entries only and runs before anything is written.
    """
    live = list(entries)
    r = GateResult("canary", len(canaries))
    for k in canaries:
        cats = k.get("categories")
        hit = any(
            e.conv_id == k["conv_id"] and e.msg == k["msg"]
            and (not cats or e.category in cats)
            and (not k.get("quote_contains") or k["quote_contains"] in e.quote)
            for e in live
        )
        if not hit:
            r.violations.append(Violation("canary", k["canary_id"], f"canary missing: {k['conv_id']} msg {k['msg']}"))
    return r
