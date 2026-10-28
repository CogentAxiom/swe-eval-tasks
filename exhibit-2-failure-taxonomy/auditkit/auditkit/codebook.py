"""The codebook: classes, drivers, tags, protections, severity, gates.

The codebook is data (``codebook/codebook.json``). It is pinned by the sha256 of
its canonical form, recorded in ``codebook/PIN``. Loading a codebook whose hash
does not match its pin is refused, and so is loading one with no pin at all — a
missing pin would skip the pin check, so the check would pass vacuously. Any
change to the codebook declares a new version and a new pin (gate G8).
The human-readable ``CODEBOOK.md`` is generated from the JSON, never edited by hand.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

REQUIRED_TOP = ("name", "version", "norm", "preconditions", "classes", "drivers", "tags",
                "protections", "severity", "evidence_gates", "mechanical_gates", "counting_rules",
                "tiebreaks")
REQUIRED_CLASS = ("name", "definition", "convicting_test", "excludes", "act_class")


class CodebookError(ValueError):
    pass


def canonical_bytes(data: dict[str, Any]) -> bytes:
    return json.dumps(data, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def digest(data: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_bytes(data)).hexdigest()


def _strict_pairs(pairs):
    out = {}
    for k, v in pairs:
        if k in out:
            raise CodebookError(f"duplicate key {k!r}: a later definition would silently replace an earlier one")
        out[k] = v
    return out


@dataclass
class Codebook:
    data: dict[str, Any]
    sha256: str

    @property
    def version(self) -> str:
        return self.data["version"]

    @property
    def classes(self) -> dict[str, dict]:
        return self.data["classes"]

    @property
    def drivers(self) -> dict[str, dict]:
        return self.data["drivers"]

    @property
    def tags(self) -> dict[str, dict]:
        return self.data["tags"]

    @property
    def protections(self) -> dict[str, dict]:
        return self.data["protections"]


def validate(data: dict[str, Any]) -> list[str]:
    problems = [f"missing top-level key {k!r}" for k in REQUIRED_TOP if k not in data]
    for slug, c in (data.get("classes") or {}).items():
        problems += [f"class {slug}: missing {k!r}" for k in REQUIRED_CLASS if k not in c]
        if not str(c.get("definition", "")).strip():
            problems.append(f"class {slug}: empty definition")
    for kind in ("drivers", "tags", "protections"):
        for slug, d in (data.get(kind) or {}).items():
            if not str(d.get("meaning") or d.get("excludes") or "").strip():
                problems.append(f"{kind} {slug}: no meaning stated")
    dims = (data.get("severity") or {}).get("dimensions", {})
    for d in ("V", "H", "C", "T", "R", "I"):
        levels = (dims.get(d) or {}).get("levels")
        if not levels or len(levels) != 3:
            problems.append(f"severity dimension {d}: needs exactly three level definitions (0, 1, 2)")
    return problems


def load(path: str | Path, pin_path: str | Path | None = None) -> Codebook:
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_strict_pairs)
    problems = validate(data)
    if problems:
        raise CodebookError("codebook invalid:\n  " + "\n  ".join(problems))
    sha = digest(data)
    pin_path = Path(pin_path) if pin_path else path.with_name("PIN")
    if not pin_path.exists():
        raise CodebookError(
            f"no pin for this codebook ({pin_path} missing): a missing pin would skip the "
            "pin check (G8). Pin it with: python -m auditkit codebook pin"
        )
    pinned = pin_path.read_text(encoding="utf-8").split()[0]
    if pinned != sha:
        raise CodebookError(
            f"codebook hash {sha[:12]} does not match its pin {pinned[:12]}: "
            "the codebook changed without a declared amendment and new pin"
        )
    return Codebook(data, sha)


def write_pin(path: str | Path) -> str:
    path = Path(path)
    data = json.loads(path.read_text(encoding="utf-8"), object_pairs_hook=_strict_pairs)
    sha = digest(data)
    path.with_name("PIN").write_text(f"{sha}  {data['version']}\n", encoding="utf-8")
    return sha
