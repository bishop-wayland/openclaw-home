"""Paddle-board-alert main pipeline.

Hops:
  1. load_config       — read config.json
  2. fetch_forecast    — Open-Meteo /v1/forecast (free, no auth)
  3. evaluate_window   — max wind in 6-9 AM window vs threshold
  4. deliver_or_suppress — iMessage on go-day; silence on no-go

Default mode: --dry-send (no real iMessage). Use --real-send to actually deliver.
Two-flag arrangement is intentional — it makes "harness ran without forgetting
to dry" visually obvious in cron entries vs. test invocations.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
import traceback
import urllib.parse
import urllib.request
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
CONFIG_PATH = SKILL_DIR / "config.json"

sys.path.insert(0, str(SCRIPT_DIR))
from logger import RunLogger  # noqa: E402
from deliver import send_imessage  # noqa: E402

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def load_config(log: RunLogger) -> dict:
    cfg = json.loads(CONFIG_PATH.read_text())
    log.emit(
        "config_loaded",
        location=cfg["location"]["name"],
        threshold_mph=cfg["threshold_mph"],
        window_start_hour=cfg["window_start_hour"],
        window_end_hour=cfg["window_end_hour"],
    )
    return cfg


def fetch_forecast(cfg: dict, log: RunLogger) -> dict:
    params = {
        "latitude": cfg["location"]["latitude"],
        "longitude": cfg["location"]["longitude"],
        "hourly": "wind_speed_10m",
        "wind_speed_unit": "mph",
        "timezone": "America/Los_Angeles",
        "forecast_days": 1,
    }
    url = f"{OPEN_METEO_URL}?{urllib.parse.urlencode(params)}"
    with urllib.request.urlopen(url, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    hourly = data.get("hourly") or {}
    times = hourly.get("time") or []
    winds = hourly.get("wind_speed_10m") or []
    raw_unit = (data.get("hourly_units") or {}).get("wind_speed_10m", "?")
    # Open-Meteo writes "mp/h" for what we requested as "mph". Normalize the
    # logged unit to "mph" (the spec's canonical form) and bail loudly if the
    # API ever returns something other than an mph-shaped unit.
    if raw_unit not in ("mp/h", "mph"):
        raise RuntimeError(f"unexpected wind unit from Open-Meteo: {raw_unit!r} (asked mph)")
    forecast_date = times[0][:10] if times else None
    log.emit(
        "forecast_fetched",
        n_hours=len(times),
        units="mph",
        raw_units=raw_unit,
        forecast_for_date=forecast_date,
    )
    return {"times": times, "winds": winds, "units": "mph", "date": forecast_date}


def evaluate_window(cfg: dict, forecast: dict, log: RunLogger) -> dict:
    start = cfg["window_start_hour"]
    end = cfg["window_end_hour"]
    threshold = float(cfg["threshold_mph"])
    breakdown = []
    for t, w in zip(forecast["times"], forecast["winds"]):
        # Open-Meteo returns naive ISO strings in the requested timezone.
        try:
            hour = int(t[11:13])
        except (TypeError, ValueError):
            continue
        if start <= hour < end:
            breakdown.append({"hour": hour, "wind_mph": float(w) if w is not None else None})
    if not breakdown:
        raise RuntimeError(
            f"no forecast hours in window [{start},{end}); got {len(forecast['times'])} hours total"
        )
    valid = [b for b in breakdown if b["wind_mph"] is not None]
    if not valid:
        raise RuntimeError("all forecast values in window are None")
    max_wind = max(b["wind_mph"] for b in valid)
    decision = "go" if max_wind <= threshold else "no-go"
    log.emit(
        "evaluated",
        max_wind_in_window=round(max_wind, 2),
        threshold=threshold,
        decision=decision,
        hourly_breakdown=breakdown,
    )
    return {"decision": decision, "max_wind": max_wind, "breakdown": breakdown}


def render_message(cfg: dict, max_wind: float) -> str:
    return cfg["message_template"].format(
        threshold=float(cfg["threshold_mph"]),
        location=cfg["location"]["name"],
        max_wind=max_wind,
        window_start=cfg["window_start_hour"],
        window_end=cfg["window_end_hour"],
    )


def deliver_or_suppress(cfg: dict, eval_result: dict, *, real_send: bool, log: RunLogger):
    decision = eval_result["decision"]
    if decision == "no-go":
        log.emit(
            "suppressed",
            reason=f"max_wind={eval_result['max_wind']:.2f} mph > threshold={cfg['threshold_mph']:.2f} mph",
        )
        return
    text = render_message(cfg, eval_result["max_wind"])
    if not real_send:
        log.emit("deliver_skipped", would_send=text)
        return
    ok, detail = send_imessage(text)
    if not ok:
        log.emit("error", hop="deliver", detail=detail, would_send=text)
        raise RuntimeError(f"BB delivery failed: {detail}")
    log.emit("delivered", message=text, bb_response_status=detail.get("status"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Paddle-board-alert: morning wind forecast check.")
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--dry-send", action="store_true", help="default; emit deliver_skipped instead of sending")
    g.add_argument("--real-send", action="store_true", help="actually send the iMessage on go-days")
    args = ap.parse_args(argv)
    real_send = bool(args.real_send)  # dry by default

    log = RunLogger()
    log.emit("triggered", real_send=real_send, dry_send=not real_send)
    try:
        cfg = load_config(log)
        forecast = fetch_forecast(cfg, log)
        result = evaluate_window(cfg, forecast, log)
        deliver_or_suppress(cfg, result, real_send=real_send, log=log)
        log.emit("done", ok=True, decision=result["decision"])
        # Stdout summary for cron-side Haiku to ignore (it's exec-only) and humans to scan.
        print(json.dumps({
            "decision": result["decision"],
            "max_wind_in_window": round(result["max_wind"], 2),
            "threshold": cfg["threshold_mph"],
            "real_send": real_send,
            "log": str(log.path),
        }))
        return 0
    except Exception as e:
        log.emit(
            "error",
            hop="main",
            exc_type=type(e).__name__,
            message=str(e),
            traceback=traceback.format_exc(limit=4),
        )
        log.emit("done", ok=False)
        print(f"FAIL: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    finally:
        log.close()


if __name__ == "__main__":
    sys.exit(main())
