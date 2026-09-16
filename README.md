# Daily Briefing -- Cloud Copy

This is a cloud-runnable copy of the local `daily-briefing` project (the
original lives at `~/Desktop/daily-briefing` and runs through the Claude
desktop app's local scheduled task). This version runs as a **Claude cloud
scheduled routine** instead, so it fires every morning regardless of whether
any computer is on.

- **What it does, step by step:** see [CLOUD_RUNBOOK.md](CLOUD_RUNBOOK.md) --
  that file is the actual prompt/instructions the cloud routine follows each
  run.
- **Where state lives between runs:** a Google Drive folder named
  `daily-briefing-cloud-data`, containing the Renpho/Withings credentials
  (`renpho.env`, `withings.env`) and a zip of the `data/` history directory
  (`daily-briefing-data.zip`). Nothing in this repo is secret -- credentials
  and personal history data are deliberately kept out of git and live only
  in that Drive folder.
- **Scripts** (`renpho-sync/`, `withings-sync/`, `scripts/`) are unchanged
  copies of the local project's scripts -- they only know about relative
  paths under this repo root, so they work the same in the cloud sandbox as
  they did locally.
- **Report styling** lives in `scripts/report_template_reference.html`, a
  sanitized copy of a real generated report with all personal data replaced
  by `{{placeholders}}` -- the routine fills those in fresh each run.

## One-time setup checklist

1. Google Drive folder `daily-briefing-cloud-data` created and seeded with
   `renpho.env`, `withings.env`, and `daily-briefing-data.zip` (done as part
   of setting this up -- see the person who set this up if it's missing).
2. In the routine's settings on https://claude.ai/code/routines, attach the
   Gmail, Google Calendar, Era Context, and Google Drive connectors (these
   can't be attached via the API from a session without connector
   permissions, so this is a manual one-time step).
3. Run the routine once manually ("Run now") so it can prompt for tool
   permissions up front -- approvals are remembered for future runs.
