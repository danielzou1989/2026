#!/usr/bin/env python3
"""
Quick trade summary tool.

Reads trades from CSV/JSON and prints aggregated metrics:
- win rate, avg win/loss, payoff, expectancy
- gross/net PnL, costs impact (fees+slippage)
- optional grouping by arbitrary fields

Expected columns (case-insensitive):
symbol, side/buy_sell, entry_price, exit_price, size/qty, pnl (net),
fee/fees, slippage, return_pct, timestamp, mae, mfe, holding_secs

If pnl is absent, will compute net pnl = (exit-entry)*signed_size - fees - slippage.
"""

import argparse
import csv
import json
import math
import sys
from collections import defaultdict
from statistics import mean
from typing import Dict, List, Any, Iterable


def load_rows(path: str) -> List[Dict[str, Any]]:
    if path.lower().endswith(".json"):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "trades" in data:
            return data["trades"]
        raise ValueError("JSON must be array of trades or contain key 'trades'")
    # csv
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def to_float(row: Dict[str, Any], keys: Iterable[str], default: float = 0.0) -> float:
    for k in keys:
        if k in row and row[k] not in (None, ""):
            try:
                return float(row[k])
            except (TypeError, ValueError):
                continue
    return default


def normalize_row(row: Dict[str, Any]) -> Dict[str, Any]:
    r = {k.lower(): v for k, v in row.items()}
    entry = to_float(r, ["entry_price", "entry"])
    exit_ = to_float(r, ["exit_price", "exit"])
    size = to_float(r, ["size", "qty", "quantity"])
    fees = to_float(r, ["fee", "fees"])
    slippage = to_float(r, ["slippage"])
    pnl = to_float(r, ["pnl", "net_pnl"])

    side_raw = (r.get("side") or r.get("buy_sell") or "").lower()
    side = "buy" if side_raw in ("buy", "long") else "sell"
    signed_size = size if side == "buy" else -size

    if pnl == 0.0 and entry and exit_ and size:
        pnl = (exit_ - entry) * signed_size - fees - slippage

    return {
        "symbol": r.get("symbol", "").upper(),
        "side": side,
        "entry": entry,
        "exit": exit_,
        "size": size,
        "fees": fees,
        "slippage": slippage,
        "pnl": pnl,
        "return_pct": to_float(r, ["return_pct", "ret_pct"], default=0.0),
        "mae": to_float(r, ["mae"]),
        "mfe": to_float(r, ["mfe"]),
        "holding_secs": to_float(r, ["holding_secs", "holding_seconds"]),
    }


def aggregate(rows: List[Dict[str, Any]]) -> Dict[str, Any]:
    if not rows:
        return {"trades": 0}

    wins = [r["pnl"] for r in rows if r["pnl"] > 0]
    losses = [r["pnl"] for r in rows if r["pnl"] < 0]
    trades = len(rows)
    win_rate = len(wins) / trades if trades else 0.0
    avg_win = mean(wins) if wins else 0.0
    avg_loss = abs(mean(losses)) if losses else 0.0
    payoff = (avg_win / avg_loss) if avg_loss else math.inf if avg_win > 0 else 0.0
    expectancy = win_rate * avg_win - (1 - win_rate) * avg_loss

    gross = sum(r["pnl"] + r["fees"] + r["slippage"] for r in rows)
    net = sum(r["pnl"] for r in rows)
    fee_total = sum(r["fees"] for r in rows)
    slippage_total = sum(r["slippage"] for r in rows)

    mae_values = [r["mae"] for r in rows if r["mae"]]
    mfe_values = [r["mfe"] for r in rows if r["mfe"]]

    return {
        "trades": trades,
        "win_rate": win_rate,
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "payoff": payoff,
        "expectancy": expectancy,
        "pnl_gross": gross,
        "pnl_net": net,
        "fees": fee_total,
        "slippage": slippage_total,
        "cost_ratio": (fee_total + slippage_total) / gross if gross else 0.0,
        "mae_mean": mean(mae_values) if mae_values else None,
        "mfe_mean": mean(mfe_values) if mfe_values else None,
        "holding_mean": mean([r["holding_secs"] for r in rows if r["holding_secs"]]) if rows else None,
    }


def group_by(rows: List[Dict[str, Any]], fields: List[str]) -> Dict[str, Any]:
    buckets = defaultdict(list)
    for r in rows:
        key = tuple(r.get(f, "") for f in fields)
        buckets[key].append(r)
    return {
        "fields": fields,
        "groups": {
            "|".join(str(k) for k in key): aggregate(rlist) for key, rlist in buckets.items()
        },
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Trade retro summary")
    parser.add_argument("path", help="CSV or JSON file of trades")
    parser.add_argument("--group-by", nargs="*", default=[], help="Fields to group by, e.g., symbol side")
    args = parser.parse_args(argv)

    raw = load_rows(args.path)
    rows = [normalize_row(r) for r in raw]

    result = {"overall": aggregate(rows)}
    if args.group_by:
        result["grouped"] = group_by(rows, args.group_by)

    json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
