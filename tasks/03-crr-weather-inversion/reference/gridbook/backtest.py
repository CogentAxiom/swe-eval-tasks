"""Backtest the shadow dispatch against a day PGO has already settled (DISPATCH_RULES section 7).

As-of replay: the model sees only what it would have seen that morning (load forecast, weather feed,
SCADA). PGO's published prices are read only to score it.
"""
from __future__ import annotations

from . import dispatch, feeds, io

BIND_TOL_MW = 0.5
PRICE_TOL = 0.05


def predicted_lmps(data_dir, day) -> dict[int, dict[str, float]]:
    """Model price at each node: the change in the hour's optimal cost when 1 MW more load sits at the node."""
    inp = dispatch.day_inputs(data_dir, day)
    nodes = sorted(io.points(data_dir))
    out: dict[int, dict[str, float]] = {}
    for h in sorted(inp["load"]):
        args = (inp["units"], inp["avail"][h], inp["limits"].get(h, {}), inp["sf"])
        base = dispatch.solve_hour(inp["units"], inp["load"][h], *args[1:])[2]
        out[h] = {}
        for nd in nodes:
            load = dict(inp["load"][h])
            load[nd] = load.get(nd, 0.0) + 1.0
            out[h][nd] = dispatch.solve_hour(inp["units"], load, *args[1:])[2] - base
    return out


def _hour_prices(inp: dict, h: int, nodes: list[str]) -> dict[str, float]:
    args = (inp["avail"][h], inp["limits"].get(h, {}), inp["sf"])
    base = dispatch.solve_hour(inp["units"], inp["load"][h], *args)[2]
    out = {}
    for nd in nodes:
        load = dict(inp["load"][h])
        load[nd] = load.get(nd, 0.0) + 1.0
        out[nd] = dispatch.solve_hour(inp["units"], load, *args)[2] - base
    return out


def explain_hour(data_dir, day, h) -> list[str]:
    """Which single change to the model's inputs reproduces PGO's published prices in hour h, within $0.05 at
    every Settlement Point? Tried: each unit out of service; each monitored element at each limit or rating the
    day's own records give it (SCADA's post-contingency limits in any hour, its normal and emergency ratings,
    the weather feed's rating)."""
    import copy
    inp = dispatch.day_inputs(data_dir, day)
    nodes = sorted(io.points(data_dir))
    real = feeds.realized_lmps(data_dir, day).get(h, {})
    cands: list[tuple[str, dict]] = []
    for u in inp["units"]:
        if inp["avail"][h][u["unit_id"]] > 0:
            alt = copy.deepcopy(inp)
            alt["avail"][h][u["unit_id"]] = 0.0
            cands.append((f"{u['unit_id']} out of service", alt))
    values: dict[str, set[float]] = {}
    for rec in feeds.scada(data_dir, day):
        el = rec["element"]
        for k in ("post_contingency_limit_mw", "rating_normal_mw", "rating_emergency_mw"):
            if rec.get(k) is not None:
                values.setdefault(el, set()).add(float(rec[k]))
    for hh, row in feeds.advisory_ratings(data_dir, day).items():
        for el, v in row.items():
            values.setdefault(el, set()).add(v)
    for el in sorted(inp["limits"].get(h, {})):
        for v in sorted(values.get(el, ())):
            if v != inp["limits"][h][el]:
                alt = copy.deepcopy(inp)
                alt["limits"][h][el] = v
                cands.append((f"{el} at {v:.0f} MW instead of {inp['limits'][h][el]:.0f}", alt))
    hits = []
    for label, alt in cands:
        try:
            p = _hour_prices(alt, h, nodes)
        except Exception:
            continue
        if real and all(abs(p[nd] - real[nd]) <= PRICE_TOL for nd in nodes if nd in real):
            hits.append(label)
    return hits


def backtest_day(data_dir, day) -> dict:
    inp = dispatch.day_inputs(data_dir, day)
    plan = dispatch.dispatch_day(data_dir, day)
    pred = predicted_lmps(data_dir, day)
    real = feeds.realized_lmps(data_dir, day)
    shadow = feeds.realized_constraints(data_dir, day)
    lmp_rows = []
    for h in sorted(pred):
        for nd in sorted(pred[h]):
            p, r = pred[h][nd], real.get(h, {}).get(nd)
            lmp_rows.append({"hour": h, "node": nd, "predicted_lmp": p, "realized_lmp": r,
                             "error": None if r is None else p - r})
    con_rows = []
    for h in sorted(plan):
        f = dispatch.flows(inp["sf"], inp["units"], inp["load"][h], plan[h]["gen"], plan[h]["shed"])
        for el in sorted(f):
            lim = inp["limits"].get(h, {}).get(el)
            mu = shadow.get(h, {}).get(el, 0.0)
            con_rows.append({"hour": h, "element": el, "flow_mw": f[el], "limit_mw": lim,
                             "predicted_binding": lim is not None and abs(f[el]) >= lim - BIND_TOL_MW,
                             "realized_shadow_price": mu, "realized_binding": mu > 0})
    errs = [abs(r["error"]) for r in lmp_rows if r["error"] is not None]
    price_miss = sorted({r["hour"] for r in lmp_rows if r["error"] is not None and abs(r["error"]) > PRICE_TOL})
    bind_miss = sorted({r["hour"] for r in con_rows if r["predicted_binding"] != r["realized_binding"]})
    summary = {
        "passed": not price_miss and not bind_miss and bool(errs),
        "price_mismatch_hours": price_miss,
        "binding_mismatch_hours": bind_miss,
        "hours": len(plan),
        "lmp_mae": sum(errs) / len(errs) if errs else None,
        "lmp_max_abs_error": max(errs) if errs else None,
        "binding_predicted": sum(r["predicted_binding"] for r in con_rows),
        "binding_realized": sum(r["realized_binding"] for r in con_rows),
        "binding_matched": sum(r["predicted_binding"] and r["realized_binding"] for r in con_rows),
        "binding_missed": sum(r["realized_binding"] and not r["predicted_binding"] for r in con_rows),
        "binding_false_alarm": sum(r["predicted_binding"] and not r["realized_binding"] for r in con_rows),
    }
    return {"lmp": lmp_rows, "constraints": con_rows, "summary": summary}
