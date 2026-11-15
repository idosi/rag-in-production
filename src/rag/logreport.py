"""Turn trace lines into a few numbers and decide which of them should wake someone up.

WHERE IT SITS
    trace.py writes ONE JSON line per question (step 3c). Cloud Run keeps those lines in
    Cloud Logging (step 3d). This module reads them back and answers "how is the SERVICE
    doing?" with the same three numbers Cloud Monitoring would compute: errors, latency
    (p50, p95) and cost, plus the cache hit rate.

        make report                                  last hour of the deployed service
        gcloud logging read ... | python -m rag.logreport    the same, by hand

    Exit code 0 = quiet, 1 = at least one alert fires (so a script or a cron can react).

summarize, percentile and check_alerts were written by Ido as exercises 3e-1 and 3e-2
(the 3e guide explains each decision). main() and the input handling are new.
"""

import json
import sys

# Alert limits for the deployed service. Cost: DAILY_BUDGET_USD is 1 in make deploy.
LIMITS = {"min_requests": 20, "max_error_rate": 0.05, "max_p95_ms": 8000.0, "max_cost_usd": 1.0}


def percentile(values: list[float], p: float) -> float:
    values = sorted(values)
    if not values:
        return 0.0
    n = len(values)
    rank = -(-p * n // 100)
    return values[rank - 1]


def summarize(lines) -> dict:
    count_requests = 0
    count_skipped = 0
    count_errors = 0
    count_rejected = 0
    count_cache_hit = 0
    cache_hits = 0
    total_ms_values = []
    total_cost_usd = 0.0

    for line in lines:
        try:
            json_object = json.loads(line)
        except json.JSONDecodeError:
            count_skipped += 1
            continue
        if isinstance(json_object, dict) and "request_id" in json_object:
            count_requests += 1
            # No status = unknown outcome, counted as an error:
            # a broken trace line must not look like a success.
            status = json_object.get("status", 500)

            if status >= 500 and status != 503:
                count_errors += 1
            elif status == 503:
                count_rejected += 1
            if "cache_hit" in json_object:
                if isinstance(json_object["cache_hit"], bool):
                    count_cache_hit += 1
                if json_object["cache_hit"]:
                    cache_hits += 1
            if "total_ms" in json_object:
                if isinstance(json_object["total_ms"], (int, float)):
                    total_ms_values.append(json_object["total_ms"])
            if "cost_usd" in json_object:
                if isinstance(json_object["cost_usd"], (int, float)):
                    total_cost_usd += json_object["cost_usd"]
        else:
            count_skipped += 1

    return {
        "requests": count_requests,
        "skipped": count_skipped,
        "errors": count_errors,
        "rejected": count_rejected,
        "error_rate": count_errors / count_requests if count_requests > 0 else 0.0,
        "cache_hit_rate": cache_hits / count_cache_hit if count_cache_hit > 0 else 0.0,
        "p50_ms": percentile(total_ms_values, 50),
        "p95_ms": percentile(total_ms_values, 95),
        "cost_usd": total_cost_usd,
    }


def check_alerts(summary: dict, limits: dict) -> list[str]:
    alerts = []
    enough_data = summary["requests"] >= limits["min_requests"]

    if enough_data and summary["error_rate"] > limits["max_error_rate"]:
        alerts.append("error_rate")
    if enough_data and summary["p95_ms"] > limits["max_p95_ms"]:
        alerts.append("latency_p95")
    if summary["cost_usd"] > limits["max_cost_usd"]:
        alerts.append("cost")
    if summary["rejected"] > 0:
        alerts.append("budget_rejections")
    return alerts


def lines_from_text(text: str) -> list[str]:
    """Accept both shapes the logs come in.

    - JSON lines, one trace per line (what the API writes, or `gcloud run services logs read`)
    - the JSON array that `gcloud logging read --format=json` prints: a list of log entries
      whose trace is in the "jsonPayload" field
    """
    stripped = text.lstrip()
    if stripped.startswith("["):
        try:
            entries = json.loads(stripped)
        except json.JSONDecodeError:
            return text.splitlines()
        return [
            json.dumps(e["jsonPayload"])
            for e in entries
            if isinstance(e, dict) and isinstance(e.get("jsonPayload"), dict)
        ]
    return text.splitlines()


def format_report(summary: dict, alerts: list[str]) -> str:
    """The summary as a few readable lines, then the alerts (or a quiet line)."""
    lines = [
        f"requests        {summary['requests']}   (skipped lines: {summary['skipped']})",
        f"errors          {summary['errors']}   rate {summary['error_rate']:.1%}",
        f"budget refused  {summary['rejected']}",
        f"latency         p50 {summary['p50_ms']:.0f} ms   p95 {summary['p95_ms']:.0f} ms",
        f"cache hit rate  {summary['cache_hit_rate']:.1%}",
        f"cost            ${summary['cost_usd']:.4f}",
        "",
    ]
    lines.append("ALERTS: " + ", ".join(alerts) if alerts else "no alerts")
    return "\n".join(lines)


def main() -> int:
    summary = summarize(lines_from_text(sys.stdin.read()))
    alerts = check_alerts(summary, LIMITS)
    print(format_report(summary, alerts))
    return 1 if alerts else 0


if __name__ == "__main__":
    sys.exit(main())
