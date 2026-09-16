"""
Pulls activity (steps, distance, calories, heart rate) and sleep data from
the Withings API for your Withings watch, and appends it to a local history
file. Run this each morning as part of the daily briefing pipeline, after
the one-time authorize.py setup has produced a refresh token in .env.

Withings rotates the refresh token every time it's used -- this script
always writes the new one back to .env, so the next run keeps working.
"""

import csv
import json
import os
import zoneinfo
from datetime import datetime, timedelta, timezone
from pathlib import Path

LOCAL_TZ = zoneinfo.ZoneInfo("America/New_York")

import requests
from dotenv import load_dotenv, set_key

SCRIPT_DIR = Path(__file__).resolve().parent
ENV_PATH = SCRIPT_DIR / ".env"
DATA_DIR = SCRIPT_DIR.parent / "data"
HISTORY_CSV = DATA_DIR / "withings_history.csv"
LATEST_JSON = DATA_DIR / "withings_latest.json"
RAW_JSON_DIR = DATA_DIR / "withings_raw"

ACCOUNT_URL = "https://account.withings.com"
WBSAPI_URL = "https://wbsapi.withings.net"

FIELDS = [
    "date",
    "steps",
    "distance_m",
    "calories_active",
    "avg_heart_rate",
    "sleep_total_min",
    "sleep_efficiency_pct",
    "sleep_deep_min",
    "sleep_light_min",
    "sleep_rem_min",
    "sleep_wake_min",
    "resting_heart_rate",
    "sleep_start",
    "sleep_end",
]


def refresh_access_token():
    client_id = os.environ["WITHINGS_CLIENT_ID"]
    client_secret = os.environ["WITHINGS_CLIENT_SECRET"]
    refresh_token = os.environ["WITHINGS_REFRESH_TOKEN"]

    # NOTE: Withings deprecated the old account.withings.com/oauth2/token
    # endpoint -- token refresh now goes through the same wbsapi "action"
    # pattern every other Withings API call uses.
    resp = requests.post(f"{WBSAPI_URL}/v2/oauth2", data={
        "action": "requesttoken",
        "grant_type": "refresh_token",
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
    }).json()

    if resp.get("status") != 0:
        raise RuntimeError(f"Token refresh failed: {resp}")

    body = resp.get("body", resp)
    # Withings invalidates the previous refresh token ~8h after a new one is
    # issued -- always persist the new one immediately.
    set_key(str(ENV_PATH), "WITHINGS_REFRESH_TOKEN", body["refresh_token"])
    return body["access_token"]


def api_post(path, token, **params):
    resp = requests.post(
        f"{WBSAPI_URL}{path}",
        headers={"Authorization": f"Bearer {token}"},
        data=params,
    ).json()
    if resp.get("status") != 0:
        raise RuntimeError(f"Withings API error on {path} action={params.get('action')}: {resp}")
    return resp.get("body", {})


def fetch_activity(token, start_ymd, end_ymd):
    body = api_post(
        "/v2/measure", token,
        action="getactivity",
        startdateymd=start_ymd,
        enddateymd=end_ymd,
        data_fields="steps,distance,calories,hr_average",
    )
    return {row["date"]: row for row in body.get("activities", [])}, body


def fetch_sleep(token, start_ymd, end_ymd):
    body = api_post(
        "/v2/sleep", token,
        action="getsummary",
        startdateymd=start_ymd,
        enddateymd=end_ymd,
        data_fields="total_sleep_time,sleep_efficiency,deepsleepduration,"
                     "lightsleepduration,remsleepduration,wakeupduration,hr_min",
    )
    by_date = {}
    for series in body.get("series", []):
        d = series.get("date")
        if d:
            # Keep startdate/enddate (Unix timestamps for when the sleep
            # session actually began/ended) alongside the data dict, not just
            # the data dict -- normalize() below needs them for bedtime/wake time.
            by_date[d] = {
                "data": series.get("data", {}),
                "startdate": series.get("startdate"),
                "enddate": series.get("enddate"),
            }
    return by_date, body


def normalize(date_str, activity, sleep):
    row = {f: None for f in FIELDS}
    row["date"] = date_str
    if activity:
        row["steps"] = activity.get("steps")
        row["distance_m"] = activity.get("distance")
        row["calories_active"] = activity.get("calories")
        row["avg_heart_rate"] = activity.get("hr_average")
    if sleep:
        sleep_data = sleep.get("data", {})

        def mins(key):
            v = sleep_data.get(key)
            return round(v / 60) if v else None

        row["sleep_total_min"] = mins("total_sleep_time")
        row["sleep_efficiency_pct"] = sleep_data.get("sleep_efficiency")
        row["sleep_deep_min"] = mins("deepsleepduration")
        row["sleep_light_min"] = mins("lightsleepduration")
        row["sleep_rem_min"] = mins("remsleepduration")
        row["sleep_wake_min"] = mins("wakeupduration")
        row["resting_heart_rate"] = sleep_data.get("hr_min")
        # startdate/enddate are Unix timestamps for when the sleep session
        # itself began/ended (bedtime/wake time), not the summary's "date"
        # (which is the wake-up calendar date) -- store as local ISO timestamps
        # so the report can show an actual bedtime, not just a duration.
        if sleep.get("startdate"):
            row["sleep_start"] = datetime.fromtimestamp(sleep["startdate"], LOCAL_TZ).isoformat()
        if sleep.get("enddate"):
            row["sleep_end"] = datetime.fromtimestamp(sleep["enddate"], LOCAL_TZ).isoformat()
    return row


def upsert_history(rows):
    existing = {}
    if HISTORY_CSV.exists():
        with open(HISTORY_CSV, newline="", encoding="utf-8") as f:
            for r in csv.DictReader(f):
                existing[r["date"]] = r

    for row in rows:
        merged = existing.get(row["date"], {})
        for k, v in row.items():
            if v is not None:
                merged[k] = v
        merged["date"] = row["date"]
        existing[row["date"]] = merged

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(HISTORY_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for d in sorted(existing):
            writer.writerow({k: existing[d].get(k, "") for k in FIELDS})


def main():
    load_dotenv(ENV_PATH)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RAW_JSON_DIR.mkdir(parents=True, exist_ok=True)

    if not os.environ.get("WITHINGS_REFRESH_TOKEN"):
        print("ERROR: WITHINGS_REFRESH_TOKEN not set -- run authorize.py once first.")
        return 1

    try:
        token = refresh_access_token()

        end = datetime.now(timezone.utc).date()
        start = end - timedelta(days=7)
        start_ymd, end_ymd = start.isoformat(), end.isoformat()

        activity_by_date, raw_activity = fetch_activity(token, start_ymd, end_ymd)
        sleep_by_date, raw_sleep = fetch_sleep(token, start_ymd, end_ymd)
    except Exception as e:
        print(f"ERROR: Withings sync failed: {e}")
        return 1

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    with open(RAW_JSON_DIR / f"{stamp}-activity.json", "w", encoding="utf-8") as f:
        json.dump(raw_activity, f, indent=2, default=str)
    with open(RAW_JSON_DIR / f"{stamp}-sleep.json", "w", encoding="utf-8") as f:
        json.dump(raw_sleep, f, indent=2, default=str)

    all_dates = sorted(set(activity_by_date) | set(sleep_by_date))
    if not all_dates:
        print("No Withings data returned for the last 7 days.")
        return 0

    rows = [normalize(d, activity_by_date.get(d), sleep_by_date.get(d)) for d in all_dates]
    upsert_history(rows)

    latest = rows[-1]
    with open(LATEST_JSON, "w", encoding="utf-8") as f:
        json.dump(latest, f, indent=2)

    print(f"Synced Withings data for {len(rows)} day(s). Latest ({latest['date']}): {latest}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
