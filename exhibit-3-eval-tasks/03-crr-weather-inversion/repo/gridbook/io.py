"""Readers for the engine's data directory."""
from __future__ import annotations

import csv
import json
from decimal import Decimal
from pathlib import Path


def read_csv(path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    with path.open(newline="", encoding="utf-8") as f:
        return [dict(r) for r in csv.DictReader(f)]


def read_jsonl(path) -> list[dict]:
    path = Path(path)
    if not path.exists():
        return []
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def num(x, default: float = 0.0) -> float:
    return float(x) if x not in (None, "") else default


def dec(x) -> Decimal:
    """Exact decimal for valuation arithmetic; a blank field is zero."""
    return Decimal(str(x).strip()) if x not in (None, "") else Decimal(0)


def points(data_dir) -> dict[str, str]:
    """Settlement Point -> weather region."""
    return {r["point"]: r["region"] for r in read_csv(Path(data_dir) / "points.csv")}


def coefficients(data_dir) -> dict[str, dict[str, Decimal]]:
    return {r["region"]: {k: dec(v) for k, v in r.items() if k != "region"}
            for r in read_csv(Path(data_dir) / "coefficients.csv")}


def paths(data_dir) -> list[dict]:
    return read_csv(Path(data_dir) / "paths.csv")
