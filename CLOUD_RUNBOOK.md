# Daily Briefing -- Cloud Runbook

You are running as a scheduled cloud routine with **no memory of any previous
run** and **no access to any local computer**. Everything you need is either
in this git repo (already checked out) or in the Google Drive folder named
**`daily-briefing-cloud-data`**. Follow these steps in order. If a step's
data source is unavailable or a connector isn't attached, skip that step's
contribution to the report (note it as "no data" or omit the section) rather
than failing the whole run or inventing numbers.

Today's date: run `date` (or use your session's current date) in
America/New_York. Use that as "today" throughout.

## 1. Pull down persisted state from Drive

Using the Google Drive connector, find the folder named
`daily-briefing-cloud-data` (search by title) and download these files from
inside it:

- `renpho.env` -> write to `renpho-sync/.env` in this checkout
- `withings.env` -> write to `withings-sync/.env` in this checkout
- `daily-briefing-data.zip` -> unzip into `data/` at the repo root (this
  restores `data/renpho_history.csv`, `data/withings_history.csv`,
  `data/daily_log.csv`, `data/goals.json`, `data/merchant_categories.json`,
  `data/category_totals.json`, `data/top_merchants.json`,
  `data/photos/pool/*`, and the `data/*_raw/` archive dirs)

If any of these three files don't exist yet (first-ever run), proceed with
empty/default state -- the scripts all handle missing history gracefully.

## 2. Sync body-composition and activity data

```
pip install -r renpho-sync/requirements.txt -r withings-sync/requirements.txt -r scripts/requirements.txt
python renpho-sync/renpho_sync.py
python withings-sync/withings_sync.py
```

- `withings_sync.py` rewrites `withings-sync/.env` with a rotated refresh
  token every run -- this updated file MUST be re-uploaded to Drive in step 8
  or the next run's sync will fail (Withings invalidates the old token).
- If either script errors (bad credentials, Renpho backend change, etc.),
  log the error, note "sync failed, see logs" in the relevant report
  section, and continue with whatever history data already exists.

## 3. Pull Google Calendar data

Using the Calendar connector:

- Today's events, to compute meeting hours and open/busy status for the
  "Today" glance chip and the schedule callout.
- Any event this week titled or containing "Weigh-in target" -- its title/
  description carries the numeric target weight (lb) for this week's goal
  pace. If a longer-range plan is described in a linked doc/notes, summarize
  it in the "Goal pace" info-box the same way the reference template shows.
- Any upcoming event (next ~14 days) that looks like a school assignment/
  quiz/homework due date (OMSCS / Coursera courses) -- these drive the "Due
  Soon" section. Match on keywords like "due", "quiz", "homework",
  "assignment", "module", course codes, etc. If nothing matches, omit that
  section entirely rather than forcing it.

## 4. Pull Gmail highlights

Using the Gmail connector: list unread messages in the inbox, pick out the
ones that actually matter (billing/trial notices, deadlines, anything
actionable) -- not routine newsletters -- and summarize each in one sentence
for the email callout / email-item cards. If nothing stands out, omit the
email callout.

## 5. Pull financial data from Era Context

Using the Era Context connector:

- `get_financial_context_and_overview` for the account summary.
- `list_financial_accounts` grouped by type (checking/savings/investment/
  debt) for the Accounts table and glance chip.
- Transactions for the past 90 days (for the "recent large transactions"
  table) and specifically the past 7 days (for the daily transaction table
  and spend_trend chart data). Internal transfers are already excluded by
  automation rules configured in Era -- do not re-derive transfer exclusion
  yourself.

### Categorize every transaction

Read `data/merchant_categories.json`. For each transaction, match its
description case-insensitively against the `rules` list top-to-bottom
(first match wins, substring/contains logic). If nothing matches, classify
it yourself using the same category taxonomy visible in that file, then
**append** a new `{match, category}` entry to the file so it's recognized
automatically in future runs -- never re-decide a merchant already in the
file, and never delete or reclassify existing entries.

### Recompute the finance data files

- `data/category_totals.json`: update the current month's `categories`
  totals (sum by category through today), `days_elapsed`, `finalized: false`.
  Never modify a prior month once its `finalized` flag is `true`; when the
  calendar rolls to a new month, mark the just-finished month `finalized:
  true` with its final `days_in_month`/`days_elapsed` before adding a fresh
  entry for the new month.
- `data/top_merchants.json`: fully overwrite with the current month's
  top-10 real-spend merchants (excludes one-off cash movements/P2P payments
  already visible in the large-transactions table). This file is a snapshot,
  not an append-only log.
- `data/goals.json`: read-only here -- `monthly_budget_usd` and
  `savings_target_usd`/`savings_target_date`/`savings_target_label` drive
  the budget pacing text if non-null.

## 6. Pull nutrition data

Using the Drive connector, open this Google Doc/Sheet (the "Intake Ledger"):
https://drive.google.com/file/d/1UtQYqzqIhfMmEIo9L0IkIQs7et53BaYo/view

Find yesterday's logged food entries. Sum calories/protein/carbs/fat, list
each item with its source and calorie count, and compare the day's totals
to the running average across all logged days to date. If there's no entry
for yesterday, omit the Nutrition section.

## 7. Log today's snapshot and build charts

```
python scripts/log_daily_snapshot.py \
  --date <YYYY-MM-DD> \
  --weight-lb <latest Renpho weight, converted kg->lb> \
  --body-fat-pct <latest> --muscle-pct <latest> --visceral-fat <latest> \
  --day-spend <yesterday's real spend> --mtd-spend <month-to-date real spend> \
  --top-category <this week's #1 category> \
  --net-worth <today's net worth> \
  --meeting-hours <from Calendar> --open-hours <from Calendar> \
  --goal-weight-lb <from the Weigh-in target event, if any>
```
Omit any flag whose value isn't available -- never pass a fabricated number.

```
python scripts/pick_photos.py
python scripts/make_charts.py
```

## 8. Build the report and render the PDF

Read `scripts/report_template_reference.html` for the exact CSS and section
structure (every class name, gradient, and layout choice there is
intentional -- reuse it verbatim). Write a new HTML file with the
`{{placeholder}}` markers replaced by today's real, gathered data. Sections
whose data source came back empty (Nutrition, OMSCS due-soon, email
callout, goal-pace info-box, stale-data warning) should be omitted entirely,
matching the template's inline notes about when to skip them. Do not invent
numbers, names, or transactions anywhere in the report.

Save it as `reports/<date>-full.html`, then:

```
python scripts/render_pdf.py reports/<date>-full.html reports/<date>-full.pdf
```

## 9. Deliver the report

1. Upload `reports/<date>-full.pdf` to the `daily-briefing-cloud-data` Drive
   folder (or a `reports/` subfolder inside it, creating it on first run).
2. Share that file with **jotemkin1@gmail.com** as `writer` (it's already
   the account's own Drive, but sharing/keeping it in the connected account
   is what makes it show up in the Drive mobile app).
3. Send an email via Gmail to jotemkin1@gmail.com: short subject like
   "Daily briefing -- <date>", body pointing to the Drive file (include its
   link) rather than attaching the PDF directly. Mention 1-2 headline
   numbers (net worth, weight if fresh, steps) so the notification itself is
   useful even before opening the file.

## 10. Persist state back to Drive

1. Re-zip the entire `data/` directory (now containing this run's updated
   history CSVs, latest.json files, raw dumps, charts, and the
   possibly-updated `merchant_categories.json` / `category_totals.json` /
   `top_merchants.json`) as `daily-briefing-data.zip`.
2. Read the current `withings-sync/.env` (rotated refresh token from step 2).
3. In the `daily-briefing-cloud-data` Drive folder: trash the previous
   `daily-briefing-data.zip` and `withings.env`, then upload the new
   versions under the same names. (`renpho.env` doesn't change -- leave it
   alone.)

This step is not optional -- skipping it means tomorrow's run starts from
stale history and a dead Withings token.

## Notes

- Never fabricate a number, name, or transaction. Every figure in the report
  must trace back to something actually pulled this run or read from a
  persisted history file.
- If a whole data source is unavailable (a connector not attached, an API
  down), still produce the rest of the report -- this mirrors the local
  version's "a source being unavailable shouldn't block logging the rest"
  design.
- Keep the report's tone and structure consistent day to day so it reads as
  the same recurring report, not a freshly-designed one each time.
