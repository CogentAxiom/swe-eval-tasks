"""gridbook command line.

    python -m gridbook.cli value    --data data --month 2026-11    [--out out/valuation_2026-11.csv]
    python -m gridbook.cli dispatch --data data --day 2026-11-17   [--out out/dispatch_2026-11-17.csv]
    python -m gridbook.cli backtest --data data --day 2026-11-10   [--out out/backtest_2026-11-10.csv]
    python -m gridbook.cli explain  --data data --day 2026-11-10   [--hours 8,9]
"""
from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path

from . import backtest, io, valuation
from .dispatch import dispatch_day, hour_cost, units


def _write(path, header, rows):
    if path is None:
        w = csv.writer(sys.stdout, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)
        return
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(header)
        w.writerows(rows)


def cmd_value(a):
    values = valuation.value_paths(a.data, a.month)
    kinds = {p["path_id"]: p["type"] for p in io.paths(a.data)}
    _write(a.out, ["path_id", "type", "value_per_mwh"], [(p, kinds[p], f"{v:.2f}") for p, v in values.items()])


def cmd_dispatch(a):
    plan = dispatch_day(a.data, a.day)
    us = units(a.data)
    rows = []
    for h in sorted(plan):
        rows += [(h, uid, "gen", f"{mw:.3f}") for uid, mw in plan[h]["gen"].items()]
        rows += [(h, nd, "shed", f"{mw:.3f}") for nd, mw in plan[h]["shed"].items()]
    _write(a.out, ["hour", "resource", "kind", "mw"], rows)
    total = sum(hour_cost(us, plan[h]["gen"], plan[h]["shed"]) for h in plan)
    shed = sum(sum(plan[h]["shed"].values()) for h in plan)
    print(f"{a.day}: production cost ${total:,.2f}; load shed {shed:,.3f} MWh", file=sys.stderr)


def cmd_backtest(a):
    res = backtest.backtest_day(a.data, a.day)
    _write(a.out, ["hour", "node", "predicted_lmp", "realized_lmp", "error"],
           [(r["hour"], r["node"], f"{r['predicted_lmp']:.2f}",
             "" if r["realized_lmp"] is None else f"{r['realized_lmp']:.2f}",
             "" if r["error"] is None else f"{r['error']:.2f}") for r in res["lmp"]])
    if a.out:
        con = Path(a.out).with_name(Path(a.out).stem + "_constraints.csv")
        _write(con, ["hour", "element", "flow_mw", "limit_mw", "predicted_binding", "realized_shadow_price", "realized_binding"],
               [(r["hour"], r["element"], f"{r['flow_mw']:.3f}", "" if r["limit_mw"] is None else f"{r['limit_mw']:.0f}",
                 r["predicted_binding"], f"{r['realized_shadow_price']:.2f}", r["realized_binding"]) for r in res["constraints"]])
    s = res["summary"]
    print(f"BACKTEST {'PASS' if s['passed'] else 'FAIL'} {a.day}: {s['hours']} hours; LMP MAE ${s['lmp_mae']:.2f}, "
          f"max ${s['lmp_max_abs_error']:.2f}; prices off by more than $0.05 in hours {s['price_mismatch_hours']}; "
          f"binding predicted {s['binding_predicted']}, published {s['binding_realized']}, matched {s['binding_matched']}, "
          f"missed {s['binding_missed']}, false alarms {s['binding_false_alarm']} (hours {s['binding_mismatch_hours']})",
          file=sys.stderr)


def cmd_explain(a):
    hours = [int(x) for x in a.hours.split(",")] if a.hours else backtest.backtest_day(a.data, a.day)["summary"]["price_mismatch_hours"]
    for h in hours:
        hits = backtest.explain_hour(a.data, a.day, h)
        print(f"hour {h}: " + ("; ".join(hits) if hits else "no single change to the inputs reproduces PGO's prices"))


def main(argv=None):
    ap = argparse.ArgumentParser(prog="gridbook")
    sub = ap.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("value")
    v.add_argument("--data", default="data")
    v.add_argument("--month", required=True)
    v.add_argument("--out")
    v.set_defaults(fn=cmd_value)
    for name, fn in (("dispatch", cmd_dispatch), ("backtest", cmd_backtest)):
        p = sub.add_parser(name)
        p.add_argument("--data", default="data")
        p.add_argument("--day", required=True)
        p.add_argument("--out")
        p.set_defaults(fn=fn)
    e = sub.add_parser("explain")
    e.add_argument("--data", default="data")
    e.add_argument("--day", required=True)
    e.add_argument("--hours", help="comma-separated; default: the hours the backtest misses")
    e.set_defaults(fn=cmd_explain)
    a = ap.parse_args(argv)
    a.fn(a)


if __name__ == "__main__":
    main()
