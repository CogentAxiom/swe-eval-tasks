"""Shift factors, shared by valuation and dispatch.

PGO's shift factor SF(n, c) is the flow on monitored element c per MW injected at node n and
withdrawn at the reference bus (methodology section 6).
"""
from __future__ import annotations

from pathlib import Path

from .io import dec, num, read_csv


def crr_constraints(data_dir, month: str) -> tuple[list[dict], dict]:
    """The auction network model for a month: constraints and their shift factors (exact decimals)."""
    data = Path(data_dir)
    cons = read_csv(data / "network" / f"{month}.csv")
    sf = {(r["constraint_id"], r["point"]): dec(r["shift_factor"]) for r in read_csv(data / "network" / f"{month}_sf.csv")}
    return cons, sf


def path_factor(sf: dict, constraint_id: str, source: str, sink: str):
    """A path's congestion exposure to one constraint. The path settles sink minus source."""
    return sf.get((constraint_id, sink), 0) - sf.get((constraint_id, source), 0)


def dispatch_shift_factors(data_dir) -> dict[tuple[str, str], float]:
    """The operating-day network: (element, node) -> shift factor."""
    return {(r["element"], r["node"]): num(r["shift_factor"])
            for r in read_csv(Path(data_dir) / "dispatch" / "shift_factors.csv")}


def flow(sf: dict, element: str, injections: dict[str, float]) -> float:
    """Flow on an element for net injections by node (generation minus served load)."""
    return sum(sf.get((element, node), 0.0) * mw for node, mw in injections.items())
