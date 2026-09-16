"""
Pulls every body-composition measurement from your Renpho cloud account and
appends it to a local history file, so nothing your scale measures gets lost
(unlike syncing through Apple Health / Google Fit, which only keeps a handful
of fields).

Run this on a schedule (e.g. Windows Task Scheduler, every morning) BEFORE
the daily briefing report is generated, so the report always has fresh data.

Setup:
  1. pip install -r requirements.txt
  2. Copy .env.example to .env and fill in your own Renpho account email/password.
     Never commit or share the .env file.
  3. Test it manually:  python renpho_sync.py
  4. Wire it into Task Scheduler (see ../SETUP.md).

This uses the unofficial `renpho-api` community library (reverse-engineered
from Renpho's app traffic), since Renpho has no official public API. It could
break if Renpho changes their backend -- if this script starts failing, check
https://github.com/danvaneijck/renpho-api for updates.
"""

import csv
import json
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv
from renpho import RenphoClient

SCRIPT_DIR = Path(__file__).resolve().parent
DATA_DIR = SCRIPT_DIR.parent / "data"
HISTORY_CSV = DATA_DIR / "renpho_history.csv"
LATEST_JSON = DATA_DIR / "renpho_latest.json"
RAW_JSON_DIR = DATA_DIR / "renpho_raw"
LOG_FILE = SCRIPT_DIR / "sync.log"

# Every metric Renpho scales can report. Not all models report all fields --
# missing ones are left blank rather than guessed.
FIELDS = [
    "measured_at",
    "weight_kg",
    "bmi",
    "body_fat_pct",
    "muscle_pct",
    "water_pct",
    "bone_pct",
    "protein_pct",
    "visceral_fat",
    "subcutaneous_fat_pct",
    "bmr_kcal",
    "body_age",
    "lean_mass_kg",
    "heart_rate_bpm",
]

# Renpho's raw field names vary by scale model / library version -- map every
# alias we've seen to our normalized column name.
FIELD_ALIASES = {
    "weight_kg": ["weight"],
    "bmi": ["bmi"],
    "body_fat_pct": ["bodyfat", "body_fat", "bodyFat"],
    "muscle_pct": ["muscle", "muscle_percent"],
    "water_pct": ["water", "body_water"],
    "bone_pct": ["bone", "bone_mass"],
    "protein_pct": ["protein"],
    "visceral_fat": ["visfat", "visceral_fat"],
    "subcutaneous_fat_pct": ["subfat", "subcutaneous_fat"],
    "bmr_kcal": ["bmr"],
    "body_age": ["bodyage", "body_age"],
    "lean_mass_kg": ["sinew", "lean_body_mass", "fat_free_weight"],
    "heart_rate_bpm": ["heartRate", "heart_rate"],
}


def normalize(raw: dict) -> dict:
    row = {}
    for field, aliases in FIELD_ALIASES.items():
        value = None
        for alias in aliases:
            if alias in raw and raw[alias] not in (None, ""):
                value = raw[alias]
                break
        row[field] = value

    ts = raw.get("timeStamp") or raw.get("time_stamp") or raw.get("timestamp") or raw.get("createdAt")
    if ts:
        try:
            # Renpho's `timeStamp` field is unix seconds (UTC).
            row["measured_at"] = datetime.fromtimestamp(
                int(ts), tz=timezone.utc
            ).isoformat()
        except (ValueError, TypeError):
            row["measured_at"] = str(ts)
    elif raw.get("localCreatedAt"):
        # Fallback: naive local timestamp string, no reliable timezone info.
        row["measured_at"] = str(raw["localCreatedAt"])
    else:
        # No timestamp field at all in this record -- do not fabricate one.
        row["measured_at"] = None

    return row


def load_existing_timestamps() -> set:
    if not HISTORY_CSV.exists():
        return set()
    with open(HISTORY_CSV, newline="", encoding="utf-8") as f:
        return {r["measured_at"] for r in csv.DictReader(f)}


def append_history(rows: list[dict]) -> int:
    write_header = not HISTORY_CSV.exists()
    existing = load_existing_timestamps()
    new_rows = [r for r in rows if r["measured_at"] not in existing]

    if not new_rows:
        return 0

    with open(HISTORY_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        if write_header:
            writer.writeheader()
        for row in sorted(new_rows, key=lambda r: r["measured_at"]):
            writer.writerow(row)

    return len(new_rows)


def main() -> int:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    RAW_JSON_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(
        filename=LOG_FILE,
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )

    load_dotenv(SCRIPT_DIR / ".env")
    email = os.environ.get("RENPHO_EMAIL")
    password = os.environ.get("RENPHO_PASSWORD")
    if not email or not password:
        logging.error("RENPHO_EMAIL / RENPHO_PASSWORD not set -- check .env")
        print("ERROR: RENPHO_EMAIL / RENPHO_PASSWORD not set in .env", file=sys.stderr)
        return 1

    try:
        client = RenphoClient(email, password)
        client.login()
        raw_measurements = client.get_all_measurements()
    except Exception:
        logging.exception("Renpho sync failed")
        print("ERROR: Renpho sync failed -- see sync.log", file=sys.stderr)
        return 1

    if not raw_measurements:
        logging.info("No measurements returned")
        print("No measurements returned from Renpho.")
        return 0

    # Keep the full raw payload too, so no field the library exposes -- even
    # ones we haven't mapped above -- is ever lost.
    raw_dump_path = RAW_JSON_DIR / f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}.json"
    with open(raw_dump_path, "w", encoding="utf-8") as f:
        json.dump(raw_measurements, f, indent=2, default=str)

    normalized = [normalize(r) for r in raw_measurements]
    undated = [r for r in normalized if not r["measured_at"]]
    dated = [r for r in normalized if r["measured_at"]]
    if undated:
        logging.warning("%d measurement(s) had no usable timestamp -- skipped", len(undated))

    added = append_history(dated)

    if not dated:
        logging.warning("No dated measurements to record as latest")
        print(f"Synced {len(normalized)} measurements, but none had usable timestamps.")
        return 0

    latest = max(dated, key=lambda r: r["measured_at"])
    with open(LATEST_JSON, "w", encoding="utf-8") as f:
        json.dump(latest, f, indent=2)

    logging.info("Synced %d measurements, %d new", len(normalized), added)
    print(f"Synced {len(normalized)} measurements ({added} new). Latest: {latest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
