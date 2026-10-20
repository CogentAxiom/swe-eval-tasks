"""Regional weather bias (methodology section 4)."""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from .io import dec, read_csv

KNOCKOUT_THRESHOLD = Decimal("0.15")
KNOCKOUT_TYPES = ("hurricane", "freeze")


def base_bias(data_dir, month: str, coef: dict) -> dict[str, Decimal]:
    """w0(r) = alpha * load_pressure - omega * max(0, wind at hub height - wind_ref)."""
    out = {r: Decimal(0) for r in coef}
    for row in read_csv(Path(data_dir) / "weather" / f"{month}.csv"):
        c = coef[row["region"]]
        wind = c["omega"] * max(Decimal(0), dec(row["wind_100m"]) - c["wind_ref"]) if c["omega"] > 0 else Decimal(0)
        out[row["region"]] = c["alpha"] * dec(row["load_pressure"]) - wind
    return out


def load_events(data_dir, month: str) -> list[dict]:
    events: dict[str, dict] = {}
    for row in read_csv(Path(data_dir) / "events" / f"{month}.csv"):
        e = events.setdefault(row["event_id"], {"event_id": row["event_id"], "type": row["type"],
                                                "probability": dec(row["probability"]), "regions": {}})
        e["regions"][row["region"]] = {"intensity": dec(row["intensity"]), "outage": dec(row["outage_fraction"])}
    return list(events.values())


def knocked_out(event: dict | None) -> set[str]:
    """Regions a hurricane or freeze knocks out: outage fraction at or above the threshold (4.2 b)."""
    if not event or event["type"] not in KNOCKOUT_TYPES:
        return set()
    return {r for r, v in event["regions"].items() if v["outage"] >= KNOCKOUT_THRESHOLD}


def scenario_bias(base: dict[str, Decimal], coef: dict, event: dict | None) -> dict[str, Decimal]:
    """Regional bias in one scenario: the demand curve, or its inversion for a knocked-out region."""
    w = dict(base)
    if event is None:
        return w
    out = knocked_out(event)
    for region, v in event["regions"].items():
        c = coef[region]
        if region in out:
            w[region] = base[region] - c["lambda"] * v["outage"]
        else:
            w[region] = base[region] + c["beta_" + event["type"]] * v["intensity"]
    return w
