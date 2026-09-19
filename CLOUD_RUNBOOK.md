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

This runbook calls out two kinds of parallelism explicitly, rather than
leaving it to be improvised mid-run:

- **Batched tool calls**: wherever a step involves several independent reads
  or writes against the same connector (e.g. the 12 Drive files in steps 1
  and 7), issue them together as one wave of parallel calls, not one after
  another.
- **Parallel subagents**: wherever a step's sub-parts are independent of
  each other and each involves real back-and-forth with a different data
  source, hand each sub-part to its own subagent and launch them together
  (step 3).

## 1. Pull down persisted state from Drive

Using the Google Drive connector, find the folder named
`daily-briefing-cloud-data` (search by title) and download each of these
flat files from inside it into the matching path in this checkout. These
12 downloads are independent of each other -- issue them as one parallel
batch of calls rather than one file at a time:

- `renpho.env` -> `renpho-sync/.env`
- `withings.env` -> `withings-sync/.env`
- `renpho_history.csv` -> `data/renpho_history.csv`
- `withings_history.csv` -> `data/withings_history.csv`
- `daily_log.csv` -> `data/daily_log.csv`
- `renpho_latest.json` -> `data/renpho_latest.json`
- `withings_latest.json` -> `data/withings_latest.json`
- `goals.json` -> `data/goals.json`
- `merchant_categories.json` -> `data/merchant_categories.json`
- `category_totals.json` -> `data/category_totals.json`
- `top_merchants.json` -> `data/top_merchants.json`
- `era_transactions_cache.json` -> `data/era_transactions_cache.json`

There is currently no seeded `data/photos/pool/` -- the photo header strip
will simply be omitted (`pick_photos.py` already handles an empty pool
gracefully). If the user later uploads photos to a `photos/` subfolder in
`daily-briefing-cloud-data`, download those into `data/photos/pool/` too
(as part of the same parallel batch).

If any file doesn't exist yet (first-ever run, or a fresh install), proceed
with empty/default state for that piece -- the scripts all handle missing
history gracefully.

## 2. Sync body-composition and activity data

```
pip install -r renpho-sync/requirements.txt -r withings-sync/requirements.txt -r scripts/requirements.txt
python renpho-sync/renpho_sync.py
python withings-sync/withings_sync.py
```

- `withings_sync.py` rewrites `withings-sync/.env` with a rotated refresh
  token every run -- Withings invalidates the old token as soon as the new
  one is issued, so **immediately after `withings_sync.py` completes
  successfully** (before moving on to step 3), find the existing
  `withings.env` in the `daily-briefing-cloud-data` Drive folder, trash it,
  and upload the new `withings-sync/.env` content under the same name. Do
  not defer this to step 7 -- if anything later in the run fails or the
  session ends early, a token re-upload batched at the end would never
  happen, and next run would start from an already-dead token. (Step 7's
  batch upload is still the home for the *other* changed files; this one
  file just jumps the queue because losing it breaks the next run's sync
  outright, where losing the others just means slightly stale history.)
- If either script errors (bad credentials, Renpho backend change, etc.),
  log the error, note "sync failed, see logs" in the relevant report
  section, and continue with whatever history data already exists. If
  `withings_sync.py` itself fails (including an invalid/expired refresh
  token), there is no new `.env` to upload -- leave the existing
  `withings.env` in Drive untouched and flag in the report that Withings
  needs manual re-authorization (see README.md's one-time setup notes for
  `authorize.py`).

## 3. Gather Calendar, Gmail, Era Context, and Nutrition data (in parallel)

Steps 3a-3d below are fully independent of each other -- none of them reads
output from another, and each is a self-contained round of connector calls.
Launch four subagents together in a single batch (not one after another),
one per sub-step, and let each work through its own instructions below;
wait for all four to report back before moving on to step 4. This mirrors
the same principle applied to transaction categorization inside 3c: give
each independent unit of work its own agent instead of doing it all
serially in one thread.

### 3a. Google Calendar

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

### 3b. Gmail highlights

Using the Gmail connector: list unread messages in the inbox, pick out the
ones that actually matter (billing/trial notices, deadlines, anything
actionable) -- not routine newsletters -- and summarize each in one sentence
for the email callout / email-item cards. If nothing stands out, omit the
email callout.

### 3c. Financial data from Era Context

Using the Era Context connector:

- `get_financial_context_and_overview` for the account summary (this is a
  live snapshot, not history -- always fetch it fresh).
- `list_financial_accounts` grouped by type (checking/savings/investment/
  debt) for the Accounts table and glance chip (also a live snapshot --
  always fetch it fresh).
- Transactions -- but see "Use the transaction cache" below before pulling
  a fresh 90-day window. Past transactions don't change once they've
  settled, so a full re-pull every run is wasted work; only the last few
  days need to come from Era each time.

#### Use the transaction cache instead of re-pulling history

Read `data/era_transactions_cache.json` (structure: `{"_readme": ..., 
"last_synced_date": "YYYY-MM-DD", "transactions": {"<transaction_id>": 
{"date", "description", "amount", "category", ...}, ...}}`). If it doesn't
exist yet (first-ever run), treat it as empty with no `last_synced_date`.

- Fetch only the incremental window from Era: `from_date` = 3 days before
  `last_synced_date` (this overlap re-covers the last couple of days so
  pending transactions that have since settled/changed amount get
  refreshed, not just brand-new ones) through today. On a first-ever run
  with no cache, fetch the full past 90 days once to seed it -- expect this
  to be large (in practice, ~1,000 raw transactions over 90 days for this
  account) and paginated across many calls, almost all of it internal-
  transfer noise per the filter below; that one-time cost is exactly what
  the cache exists to avoid paying again on every subsequent run.
- Before caching, drop anything that isn't real spend: skip any transaction
  where `is_cash_outflow` is false, and skip any transaction whose
  `applied_rules` names a transfer-pattern rule (sweeps, minimum-balance
  transfers, card autopay, redemptions, brokerage ACH funding -- anything
  matching the transfer-detection behavior already described under
  "Categorize every transaction" below). These are account-to-account
  movements, not spend, and they're most of the raw volume (a 7-day sample
  had 53 raw transactions but only ~48 were real spend; the 90-day pull is
  proportionally worse). Only real-spend transactions belong in the cache.
- Merge the remaining (real-spend) fetched transactions into the cache by
  `transaction_id` (a fetched transaction always overwrites any existing
  entry with the same id, since it may have gone from pending to settled).
  Leave every other cached entry untouched.
- Update `last_synced_date` to today.
- Prune any cached transaction older than 100 days (a bit more headroom
  than the 90-day reporting window needs) so the cache doesn't grow
  unbounded.
- Build the "recent large transactions" (past 90 days) and "past 7 days"
  tables/chart data by reading straight out of the cache after the merge,
  filtered to the relevant date range -- not from a fresh Era pull.

#### Categorize every transaction

A cached transaction that already carries a `category` from a prior run
keeps it as-is -- never re-decide a merchant you've already classified,
whether that decision lives in `merchant_categories.json` or is just
sitting on the cached transaction from last time. Categorization work is
therefore incremental too: only the transactions that are new this run (not
previously in the cache, or freshly settled from pending) need a category
decision before being written back into the cache.

Read `data/merchant_categories.json`. For each of those new/changed
transactions, match its description case-insensitively against the `rules`
list top-to-bottom (first match wins, substring/contains logic). If nothing
matches, classify it yourself using the same category taxonomy visible in
that file, then **append** a new `{match, category}` entry to the file so
it's recognized automatically in future runs -- never delete or reclassify
existing entries. If the number of uncategorized/large-transaction lookups
is large enough to be its own unit of work, delegate that categorization
pass to a further subagent rather than doing it inline -- the same
parallel-work principle this step is built around.

#### Recompute the finance data files

- `data/era_transactions_cache.json`: the merged, categorized cache from
  above -- this is the new/updated file this run, and it's what steps 3c's
  own tables and the totals below are computed from.
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

### 3d. Nutrition data

Using the Drive connector, open this Google Doc/Sheet (the "Intake Ledger"):
https://drive.google.com/file/d/1UtQYqzqIhfMmEIo9L0IkIQs7et53BaYo/view

Find yesterday's logged food entries. Sum calories/protein/carbs/fat, list
each item with its source and calorie count, and compare the day's totals
to the running average across all logged days to date. If there's no entry
for yesterday, omit the Nutrition section.

## 4. Log today's snapshot and build charts

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

## 5. Build the report

Read `scripts/report_template_reference.html` for the exact CSS and section
structure (every class name, gradient, and layout choice there is
intentional -- reuse it verbatim). Write a new HTML file with the
`{{placeholder}}` markers replaced by today's real, gathered data. Sections
whose data source came back empty (Nutrition, OMSCS due-soon, email
callout, goal-pace info-box, stale-data warning) should be omitted entirely,
matching the template's inline notes about when to skip them. Do not invent
numbers, names, or transactions anywhere in the report.

Save it as `reports/<date>-full.html`. **This HTML file is the deliverable
-- do not also render it to PDF.** A Chromium PDF render of this template
(box-shadows/gradients rasterize into large soft-mask images) lands well
over 1MB, and every tool available for delivering it (Drive upload, Gmail
attachment) requires the entire file inlined as base64 in a single tool
call -- there is no streaming/file-path upload option. A file that size
either fails outright or burns enormous effort on chunked-read-and-
reassemble workarounds that still may not fit in one call. The HTML file
carries the identical visual design (same CSS, same charts as `<img>` tags)
and opens cleanly in any desktop or mobile browser -- including Gmail's own
in-app browser when opened from a Drive link -- so there's no real loss in
switching to it as the sole format.

## 6. Deliver the report

1. Upload `reports/<date>-full.html` to the `reports` subfolder inside the
   `daily-briefing-cloud-data` Drive folder (search for a subfolder titled
   `reports` there; create it on first run if it doesn't exist yet). Always
   use this exact location -- don't drop reports directly in the parent
   folder or vary the location run to run. This file is small (tens of KB),
   so it uploads in one ordinary call -- no chunking needed.
2. Share that file with **jotemkin1@gmail.com** as `writer` (it's already
   the account's own Drive, but sharing/keeping it in the connected account
   is what makes it show up in the Drive mobile app).
3. Send an email via Gmail to jotemkin1@gmail.com: short subject like
   "Daily briefing -- <date>", body pointing to the Drive file (include its
   link). Lead the email body with a summary table of yesterday's logged
   food items (from step 3d, if present) and yesterday's individual
   purchases (from step 3c's cache), each with a totals row, before the
   rest of the summary -- these two tables are what the person wants to see
   first thing. After the tables, include 1-2 more headline numbers (net
   worth, weight if fresh, steps) so the email itself is useful even before
   opening the linked report.

## 7. Persist state back to Drive

For each of these files that changed this run --
`data/renpho_history.csv`, `data/withings_history.csv`,
`data/daily_log.csv`, `data/renpho_latest.json`, `data/withings_latest.json`,
`data/merchant_categories.json` (if any new merchant rules were appended),
`data/category_totals.json`, `data/top_merchants.json`, and
`data/era_transactions_cache.json` (it changes essentially every run, since
each run merges in at least the last few days) -- find the
existing file of that name in the `daily-briefing-cloud-data` Drive folder,
trash it, and upload the new content under the same name. As with step 1,
issue these lookups and uploads as one parallel batch of calls rather than
one file at a time. (`renpho.env` and `goals.json` don't change during a
normal run -- leave them alone. `withings-sync/.env` is deliberately not in
this batch -- it was already re-uploaded right after step 2, so that a
later failure in this run can't cost the next run its Withings token.)

This step is not optional -- skipping it means tomorrow's run starts from
stale history.

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
