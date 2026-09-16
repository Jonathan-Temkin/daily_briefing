"""
Appends (or updates, if already run today) one row to data/daily_log.csv --
the cross-domain history that lets the daily briefing chart real progress
over time, not just report today's numbers in isolation.

Called by the "daily-briefing" scheduled task after it has pulled Calendar
and Era data for the day. All fields are optional (pass only what you have --
a source being unavailable shouldn't block logging the rest).

Usage:
  python log_daily_snapshot.py \
    --date 2026-09-13 \
    --weight-lb 165.3 --body-fat-pct 19.6 --muscle-pct 45.6 --visceral-fat 5.0 \
    --day-spend 42.10 --mtd-spend 891.44 --top-category "Dining" \
    --net-worth 45230.11 \
    --meeting-hours 3.5 --open-hours 2.0
"""

import argparse
import csv
from pathlib import Path
from zoneinfo import ZoneInfo
from datetime import datetime

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
LOG_CSV = DATA_DIR / "daily_log.csv"

FIELDS = [
    "date",
    "weight_lb",
    "body_fat_pct",
    "muscle_pct",
    "visceral_fat",
    "day_spend",
    "mtd_spend",
    "top_category",
    "net_worth",
    "meeting_hours",
    "open_hours",
    "goal_weight_lb",
]


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument("--date", default=None, help="YYYY-MM-DD, defaults to today in America/New_York")
    p.add_argument("--weight-lb", type=float, default=None)
    p.add_argument("--body-fat-pct", type=float, default=None)
    p.add_argument("--muscle-pct", type=float, default=None)
    p.add_argument("--visceral-fat", type=float, default=None)
    p.add_argument("--day-spend", type=float, default=None)
    p.add_argument("--mtd-spend", type=float, default=None)
    p.add_argument("--top-category", default=None)
    p.add_argument("--net-worth", type=float, default=None)
    p.add_argument("--meeting-hours", type=float, default=None)
    p.add_argument("--open-hours", type=float, default=None)
    p.add_argument("--goal-weight-lb", type=float, default=None, help="This week's target weight from the calendar-based plan, if any")
    return p.parse_args()


def main():
    args = parse_args()
    date = args.date or datetime.now(ZoneInfo("America/New_York")).strftime("%Y-%m-%d")

    new_row = {
        "date": date,
        "weight_lb": args.weight_lb,
        "body_fat_pct": args.body_fat_pct,
        "muscle_pct": args.muscle_pct,
        "visceral_fat": args.visceral_fat,
        "day_spend": args.day_spend,
        "mtd_spend": args.mtd_spend,
        "top_category": args.top_category,
        "net_worth": args.net_worth,
        "meeting_hours": args.meeting_hours,
        "open_hours": args.open_hours,
        "goal_weight_lb": args.goal_weight_lb,
    }

    rows = {}
    if LOG_CSV.exists():
        with open(LOG_CSV, newline="", encoding="utf-8") as f:
            for row in csv.DictReader(f):
                rows[row["date"]] = row

    # Upsert: merge onto any existing row for the same date so a rerun today
    # (or a later run that has data an earlier run didn't) doesn't lose fields.
    existing = rows.get(date, {})
    for key, value in new_row.items():
        if value is not None and value != "":
            existing[key] = value
    existing["date"] = date
    rows[date] = existing

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(LOG_CSV, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDS)
        writer.writeheader()
        for d in sorted(rows):
            writer.writerow({k: rows[d].get(k, "") for k in FIELDS})

    print(f"Logged snapshot for {date}: {new_row}")


if __name__ == "__main__":
    main()
