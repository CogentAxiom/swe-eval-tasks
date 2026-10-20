"""Regional weather bias (methodology section 4)."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from .io import dec, read_csv


def base_bias(data_dir, month: str, coef: dict) -> dict[str, Decimal]:
    """w0(r) = alpha * load_pressure - omega * max(0, wind - wind_ref)."""
    out = {r: Decimal(0) for r in coef}
    for row in read_csv(Path(data_dir) / "weather" / f"{month}.csv"):
        c = coef[row["region"]]
        wind = c["omega"] * max(Decimal(0), dec(row["wind_10m"]) - c["wind_ref"]) if c["omega"] > 0 else Decimal(0)
        out[row["region"]] = c["alpha"] * dec(row["load_pressure"]) - wind
    return out


def load_events(data_dir, month: str) -> list[dict]:
    events: dict[str, dict] = {}
    for row in read_csv(Path(data_dir) / "events" / f"{month}.csv"):
        e = events.setdefault(row["event_id"], {"event_id": row["event_id"], "type": row["type"],
                                                "probability": dec(row["probability"]), "regions": {}})
        e["regions"][row["region"]] = {"intensity": dec(row["intensity"]), "outage": dec(row["outage_fraction"])}
    return list(events.values())


def scenario_bias(base: dict[str, Decimal], coef: dict, event: dict | None) -> dict[str, Decimal]:
    """Regional bias in one scenario: extreme weather raises demand, and the region's price with it."""
    w = dict(base)
    if event is None:
        return w
    for region, v in event["regions"].items():
        w[region] = base[region] + coef[region]["beta_" + event["type"]] * v["intensity"]
    return w
