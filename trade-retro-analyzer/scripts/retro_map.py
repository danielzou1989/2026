#!/usr/bin/env python3
"""
Generate patch suggestions from retro_summary output.

Reads summary JSON and applies rule-mapping heuristics to produce
JSON suggestions targeting risk_config.json and strategy defaults.

Usage:
  python scripts/retro_map.py summary.json --config path/to/risk_config.json
"""

import argparse
import json
import math
import os
from typing import Dict, Any, List, Optional


def load_json(path: str) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def pct_adjust(value: float, delta: float, min_value: float = 0.0) -> float:
    return max(value * (1 + delta), min_value)


def get_by_path(data: Dict[str, Any], path: str) -> Optional[Any]:
    current = data
    for key in path.split("."):
        if not isinstance(current, dict) or key not in current:
            return None
        current = current[key]
    return current


def eval_rule(rule: str, metrics: Dict[str, Any]) -> bool:
    expression = rule.replace("&&", " and ").replace("||", " or ")
    safe_locals = {k: metrics.get(k, 0) for k in metrics}
    try:
        return bool(eval(expression, {"__builtins__": {}}, safe_locals))
    except (SyntaxError, NameError, TypeError, ValueError):
        return False


def apply_target(target: Dict[str, Any], config: Dict[str, Any]) -> Dict[str, Any]:
    op = target.get("op", "text")
    path = target.get("path")
    current = get_by_path(config, path) if path else None

    if op == "pct_adjust":
        if current is None:
            return {"current": None, "suggested": None}
        delta = float(target.get("delta", 0))
        min_value = float(target.get("min", 0))
        suggested = round(pct_adjust(float(current), delta, min_value=min_value), 6)
        return {"current": current, "suggested": suggested}

    if op == "scale_levels":
        if not isinstance(current, list):
            return {"current": current, "suggested": None}
        scale = float(target.get("scale", 1.0))
        start_index = int(target.get("start_index", 0))
        updated = list(current)
        for i in range(len(updated)):
            if i >= start_index and isinstance(updated[i], (int, float)):
                updated[i] = round(updated[i] * scale, 6)
        return {"current": current, "suggested": updated}

    if op == "text":
        return {"current": current, "suggested": target.get("suggested")}

    return {"current": current, "suggested": None}


def build_suggestions(summary: Dict[str, Any], config: Dict[str, Any],
                      rules: Dict[str, Any]) -> List[Dict[str, Any]]:
    suggestions: List[Dict[str, Any]] = []
    overall = summary.get("overall", {})

    metrics = {
        "expectancy": overall.get("expectancy", 0.0),
        "mae_mean": overall.get("mae_mean", 0.0) or 0.0,
        "mfe_mean": overall.get("mfe_mean", 0.0) or 0.0,
        "cost_ratio": overall.get("cost_ratio", 0.0),
        "holding_mean": overall.get("holding_mean", 0.0) or 0.0,
        "avg_loss": overall.get("avg_loss", 0.0),
        "avg_win": overall.get("avg_win", 0.0),
    }

    for rule in rules.get("rules", []):
        rule_expr = rule.get("rule", "")
        if not rule_expr or not eval_rule(rule_expr, metrics):
            continue

        for target in rule.get("targets", []):
            target_result = apply_target(target, config if target.get("target") == "risk_config.json" else {})
            suggestions.append({
                "target": target.get("target"),
                "path": target.get("path"),
                "current": target_result.get("current"),
                "suggested": target_result.get("suggested"),
                "rule": rule_expr,
                "rule_cn": rule.get("rule_cn"),
                "reason": target.get("reason")
            })

    return suggestions


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate patch suggestions from retro summary")
    parser.add_argument("summary", help="retro_summary output JSON")
    parser.add_argument("--config", required=True, help="risk_config.json path")
    parser.add_argument(
        "--rules",
        help="rule-thresholds.json path",
        default=os.path.join(os.path.dirname(__file__), "..", "references", "rule-thresholds.json"),
    )
    args = parser.parse_args()

    summary = load_json(args.summary)
    config = load_json(args.config)
    rules = load_json(args.rules)

    suggestions = build_suggestions(summary, config, rules)

    result = {
        "suggestions": suggestions,
        "count": len(suggestions)
    }

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
