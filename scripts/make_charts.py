"""
Builds the charts for the daily briefing PDF from the local history files
(data/renpho_history.csv for body composition, data/daily_log.csv for
spending / net worth / calendar load / goal pace), and saves them as PNG
files under data/charts/. The report HTML references these by relative file
path (<img src="../data/charts/weight_trend.png">) rather than embedding
base64 -- this keeps the report-writing step cheap and reliable, since
whoever composes that HTML never has to type out image bytes.

Any chart with fewer than 2 usable data points is skipped (removed from
data/charts/ if it exists from a previous run) rather than drawn empty.
"""

import calendar
import csv
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime, timedelta

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
CHARTS_DIR = DATA_DIR / "charts"
RENPHO_HISTORY = DATA_DIR / "renpho_history.csv"
DAILY_LOG = DATA_DIR / "daily_log.csv"
WITHINGS_HISTORY = DATA_DIR / "withings_history.csv"
CATEGORY_TOTALS = DATA_DIR / "category_totals.json"
TOP_MERCHANTS = DATA_DIR / "top_merchants.json"
MANIFEST = DATA_DIR / "charts_manifest.json"

INK = "#1d241f"
SOFT = "#5c6660"
HAIRLINE = "#dbe0d8"
BG = "#fafbf8"
SAGE = "#6b8f71"
SAGE_DARK = "#4f6f56"
CLAY = "#b3552f"
GOLD = "#c9a227"
SAND = "#c9bfa0"

# Categories excluded from the month-over-month comparison chart -- these are
# one-off or catch-all buckets (a single cash withdrawal, unclassified
# merchants, brokerage activity) rather than a comparable recurring spending
# pattern, so plotting them alongside real categories would be misleading.
COMPARISON_EXCLUDED_CATEGORIES = {"Cash, checks, and misc", "Uncategorized", "Stocks and investments"}

# One fixed color per category, shared by every chart AND the HTML report's
# category-dot markers (see reports/*.html's .cat-dot spans) -- keep these in
# sync so a category reads as the same color everywhere in the report.
CATEGORY_COLORS = {
    "Coffee and snacks": "#b3552f",
    "Dining out": "#c9a227",
    "Groceries": "#4f6f56",
    "Shopping and gear": "#6b8f71",
    "Education": "#7a8fae",
    "Vehicle expenses": "#a9738a",
    "Insurance": "#8a897f",
    "Health and fitness": "#c98f5f",
    "Utilities": "#5c6660",
    "Public transit": "#6b5b95",
    "Entertainment and subscriptions": "#d4a5a5",
    "Rent and housing": "#3d5a80",
    "Cash, checks, and misc": "#9a9a92",
    "Uncategorized": "#c9bfa0",
    "Stocks and investments": "#2f6f4f",
}
DEFAULT_CATEGORY_COLOR = "#8a897f"

SMALL_FIG = (4.3, 1.7)
DONUT_FIG = (2.6, 2.6)

plt.rcParams.update({
    "font.family": "sans-serif",
    "font.size": 9,
    "text.color": INK,
    "axes.edgecolor": HAIRLINE,
    "axes.labelcolor": SOFT,
    "xtick.color": SOFT,
    "ytick.color": SOFT,
    "xtick.labelsize": 8,
    "ytick.labelsize": 8,
    "axes.facecolor": BG,
    "figure.facecolor": BG,
    "savefig.facecolor": BG,
})


def _date_axis(ax):
    """Cap the number of date ticks -- these charts are narrow (SMALL_FIG),
    and matplotlib's default autofmt locator crowds/overlaps labels when a
    series (or a goal line extending further than it) spans many weeks."""
    ax.xaxis.set_major_locator(mdates.AutoDateLocator(maxticks=6))
    ax.xaxis.set_major_formatter(mdates.DateFormatter("%b %d"))


def _style_axes(ax):
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.grid(axis="y", color=HAIRLINE, linewidth=0.7)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)


def _save(fig, name: str) -> str:
    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    path = CHARTS_DIR / f"{name}.png"
    fig.savefig(path, format="png", dpi=170, bbox_inches="tight")
    plt.close(fig)
    return path.name


def read_renpho_history():
    if not RENPHO_HISTORY.exists():
        return []
    with open(RENPHO_HISTORY, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["_dt"] = datetime.fromisoformat(r["measured_at"])
    rows.sort(key=lambda r: r["_dt"])
    return rows


def read_withings_history():
    if not WITHINGS_HISTORY.exists():
        return []
    with open(WITHINGS_HISTORY, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["_dt"] = datetime.strptime(r["date"], "%Y-%m-%d")
    rows.sort(key=lambda r: r["_dt"])
    return rows


def read_daily_log():
    if not DAILY_LOG.exists():
        return []
    with open(DAILY_LOG, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))
    for r in rows:
        r["_dt"] = datetime.strptime(r["date"], "%Y-%m-%d")
    rows.sort(key=lambda r: r["_dt"])
    return rows


def weight_trend_chart(renpho_rows, log_rows):
    pts = [(r["_dt"], float(r["weight_kg"]) * 2.20462) for r in renpho_rows if r.get("weight_kg")]
    if len(pts) < 2:
        return None
    pts = pts[-60:]
    dates, weights = zip(*pts)

    fig, ax = plt.subplots(figsize=SMALL_FIG)
    ax.plot(dates, weights, color=INK, linewidth=1.8, marker="o", markersize=3, label="Weight", zorder=3)

    # Draw the most recently-set goal as a threshold line across the whole
    # chart (not just the handful of days it happens to be logged for) --
    # that's what makes it useful as a visual "above/below goal" reference.
    goal_rows = [(r["_dt"], float(r["goal_weight_lb"])) for r in log_rows if r.get("goal_weight_lb")]
    if goal_rows:
        goal_value = goal_rows[-1][1]
        ax.axhline(goal_value, color=GOLD, linewidth=1.5, linestyle="--", label=f"Goal {goal_value:g} lb", zorder=2)
        ax.legend(frameon=False, fontsize=7, loc="best")

    ax.set_ylabel("lb", fontsize=8)
    _date_axis(ax)
    fig.autofmt_xdate(rotation=0, ha="center")
    _style_axes(ax)
    return _save(fig, "weight_trend")


def body_comp_chart(renpho_rows):
    pts = [(r["_dt"], r.get("body_fat_pct"), r.get("muscle_pct")) for r in renpho_rows if r.get("body_fat_pct") and r.get("muscle_pct")]
    if len(pts) < 2:
        return None
    pts = pts[-60:]
    dates = [p[0] for p in pts]
    fat = [float(p[1]) for p in pts]
    muscle = [float(p[2]) for p in pts]

    fig, ax = plt.subplots(figsize=SMALL_FIG)
    ax.plot(dates, fat, color=CLAY, linewidth=1.8, marker="o", markersize=3, label="Body fat %")
    ax.plot(dates, muscle, color=SAGE, linewidth=1.8, marker="o", markersize=3, label="Muscle %")
    ax.set_ylabel("%", fontsize=8)
    _date_axis(ax)
    fig.autofmt_xdate(rotation=0, ha="center")
    ax.legend(frameon=False, fontsize=7, loc="center right")
    _style_axes(ax)
    return _save(fig, "body_comp_trend")


def composition_donut(renpho_rows):
    if not renpho_rows:
        return None
    latest = renpho_rows[-1]
    if not latest.get("weight_kg") or not latest.get("body_fat_pct"):
        return None
    weight_lb = float(latest["weight_kg"]) * 2.20462
    fat_pct = float(latest["body_fat_pct"])
    fat_lb = weight_lb * fat_pct / 100
    lean_lb = weight_lb - fat_lb

    fig, ax = plt.subplots(figsize=DONUT_FIG)
    wedges, _ = ax.pie(
        [fat_lb, lean_lb],
        colors=[CLAY, SAGE],
        startangle=90,
        wedgeprops={"width": 0.38, "edgecolor": BG, "linewidth": 2},
    )
    ax.text(0, 0.12, f"{weight_lb:.1f} lb", ha="center", va="center", fontsize=13, color=INK, fontweight="bold")
    ax.text(0, -0.14, "total", ha="center", va="center", fontsize=8, color=SOFT)
    ax.legend(
        wedges,
        [f"Fat mass — {fat_lb:.1f} lb", f"Fat-free mass — {lean_lb:.1f} lb"],
        frameon=False, fontsize=7.5, loc="upper center", bbox_to_anchor=(0.5, -0.02),
    )
    ax.set_aspect("equal")
    return _save(fig, "composition_donut")


def weekly_change_bar(renpho_rows):
    pts = [(r["_dt"], float(r["weight_kg"]) * 2.20462) for r in renpho_rows if r.get("weight_kg")]
    if len(pts) < 3:
        return None
    pts = pts[-11:]
    deltas = []
    labels = []
    for i in range(1, len(pts)):
        deltas.append(pts[i][1] - pts[i - 1][1])
        labels.append(pts[i][0].strftime("%b %d"))
    if len(deltas) < 2:
        return None

    fig, ax = plt.subplots(figsize=SMALL_FIG)
    colors = [SAGE if d <= 0 else CLAY for d in deltas]
    ax.bar(labels, deltas, color=colors, width=0.6)
    ax.axhline(0, color=HAIRLINE, linewidth=1)
    ax.set_ylabel("lb change", fontsize=8)
    plt.setp(ax.get_xticklabels(), rotation=0, ha="center", fontsize=7)
    _style_axes(ax)
    return _save(fig, "weekly_change_bar")


def steps_trend_chart(withings_rows):
    pts = [(r["_dt"], float(r["steps"])) for r in withings_rows if r.get("steps")]
    if len(pts) < 2:
        return None
    pts = pts[-30:]
    dates, steps = zip(*pts)

    fig, ax = plt.subplots(figsize=SMALL_FIG)
    ax.bar(dates, steps, color=SAGE, width=0.7)
    # Exclude today's (still in-progress) bar from the average line -- a partial day's
    # step count would otherwise drag the average down and misrepresent daily pace.
    today = datetime.now().date()
    full_days = [s for d, s in zip(dates, steps) if d.date() != today]
    avg_steps = full_days if full_days else steps
    avg = sum(avg_steps) / len(avg_steps)
    ax.axhline(avg, color=INK, linewidth=1.1, linestyle="--", label=f"avg {avg:,.0f}")
    ax.set_ylabel("steps", fontsize=8)
    _date_axis(ax)
    fig.autofmt_xdate(rotation=0, ha="center")
    ax.legend(frameon=False, fontsize=7, loc="upper right")
    _style_axes(ax)
    return _save(fig, "steps_trend")


def sleep_trend_chart(withings_rows):
    pts = [
        (r["_dt"], float(r["sleep_total_min"]) / 60)
        for r in withings_rows if r.get("sleep_total_min")
    ]
    if len(pts) < 2:
        return None
    pts = pts[-30:]
    dates, hours = zip(*pts)

    fig, ax = plt.subplots(figsize=SMALL_FIG)
    ax.bar(dates, hours, color=CLAY, width=0.7, alpha=0.85)
    ax.axhline(8, color=SOFT, linewidth=1, linestyle=":", label="8h reference")
    ax.set_ylabel("hours", fontsize=8)
    _date_axis(ax)
    fig.autofmt_xdate(rotation=0, ha="center")
    ax.legend(frameon=False, fontsize=7, loc="upper right")
    _style_axes(ax)
    return _save(fig, "sleep_trend")


def resting_hr_trend_chart(withings_rows):
    pts = [
        (r["_dt"], float(r["resting_heart_rate"]))
        for r in withings_rows if r.get("resting_heart_rate")
    ]
    if len(pts) < 2:
        return None
    pts = pts[-30:]
    dates, hr = zip(*pts)

    fig, ax = plt.subplots(figsize=SMALL_FIG)
    ax.plot(dates, hr, color=INK, linewidth=1.8, marker="o", markersize=3)
    ax.set_ylabel("bpm", fontsize=8)
    _date_axis(ax)
    fig.autofmt_xdate(rotation=0, ha="center")
    _style_axes(ax)
    return _save(fig, "resting_hr_trend")


def spend_trend_chart(log_rows):
    pts = [(r["_dt"], float(r["day_spend"])) for r in log_rows if r.get("day_spend")]
    if len(pts) < 2:
        return None
    pts = pts[-30:]
    dates, spend = zip(*pts)

    fig, ax = plt.subplots(figsize=SMALL_FIG)
    ax.bar(dates, spend, color=INK, width=0.7)
    # Exclude today's (still in-progress) bar from the average line, same reasoning as
    # steps_trend_chart -- a partial day understates real spend and would skew the average.
    today = datetime.now().date()
    full_days = [s for d, s in zip(dates, spend) if d.date() != today]
    avg_spend = full_days if full_days else spend
    avg = sum(avg_spend) / len(avg_spend)
    ax.axhline(avg, color=CLAY, linewidth=1.1, linestyle="--", label=f"avg ${avg:,.0f}/day")
    ax.set_ylabel("$ spent", fontsize=8)
    _date_axis(ax)
    fig.autofmt_xdate(rotation=0, ha="center")
    ax.legend(frameon=False, fontsize=7, loc="upper right")
    _style_axes(ax)
    return _save(fig, "spend_trend")


def net_worth_chart(log_rows):
    pts = [(r["_dt"], float(r["net_worth"])) for r in log_rows if r.get("net_worth")]
    if len(pts) < 3:
        # matplotlib's automatic date-tick locator produces garbled/repeated
        # labels with only 1-2 points -- not enough data yet for a useful trend line.
        return None
    pts = pts[-90:]
    dates, worth = zip(*pts)

    fig, ax = plt.subplots(figsize=SMALL_FIG)
    ax.plot(dates, worth, color=INK, linewidth=1.8, marker="o", markersize=3)
    ax.fill_between(dates, worth, min(worth), color=SAGE, alpha=0.15)
    ax.set_ylabel("$", fontsize=8)
    _date_axis(ax)
    fig.autofmt_xdate(rotation=0, ha="center")
    _style_axes(ax)
    return _save(fig, "net_worth_trend")


def read_category_totals():
    if not CATEGORY_TOTALS.exists():
        return {}
    with open(CATEGORY_TOTALS, encoding="utf-8") as f:
        return json.load(f).get("months", {})


def category_comparison_chart(months: dict):
    """Horizontal grouped bar chart: prior full month vs current month-to-date,
    per spending category. Reads data/category_totals.json -- see that file's
    _readme for how the totals are maintained. Returns None (skips the chart)
    if either month is missing or there's nothing to compare, rather than
    drawing a broken/empty chart."""
    today = datetime.now().date()
    current_key = today.strftime("%Y-%m")
    prior_key = (today.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")

    current = months.get(current_key)
    prior = months.get(prior_key)
    if not current or not prior:
        return None

    cur_cats = current.get("categories", {})
    pri_cats = prior.get("categories", {})
    cur_days = current.get("days_elapsed") or 1
    pri_days = prior.get("days_in_month") or 30

    categories = [
        c for c in cur_cats
        if c in pri_cats and c not in COMPARISON_EXCLUDED_CATEGORIES
    ]
    if not categories:
        return None
    # Sort by current-month spend descending so the most relevant rows read top-to-bottom.
    categories.sort(key=lambda c: cur_cats[c], reverse=True)

    prior_month_label = datetime.strptime(prior_key, "%Y-%m").strftime("%B")
    current_month_label = datetime.strptime(current_key, "%Y-%m").strftime("%B")

    n = len(categories)
    fig_h = max(2.6, 0.52 * n + 0.6)
    fig, ax = plt.subplots(figsize=(7.4, fig_h))

    y = list(range(n))
    bar_h = 0.34
    prior_vals = [pri_cats[c] for c in categories]
    current_vals = [cur_cats[c] for c in categories]

    ax.barh(
        [i + bar_h / 2 + 0.02 for i in y], prior_vals, height=bar_h,
        color=SAND, label=f"{prior_month_label} (full month)", zorder=3,
    )
    ax.barh(
        [i - bar_h / 2 - 0.02 for i in y], current_vals, height=bar_h,
        color=SAGE, label=f"{current_month_label} (month-to-date)", zorder=3,
    )

    max_val = max(prior_vals + current_vals) or 1
    pad = max_val * 0.02
    for i, cat in enumerate(categories):
        p_val, c_val = pri_cats[cat], cur_cats[cat]
        p_rate, c_rate = p_val / pri_days, c_val / cur_days
        ax.text(p_val + pad, i + bar_h / 2 + 0.02, f"${p_val:,.0f}", va="center", ha="left",
                fontsize=7.3, color=INK)
        ax.text(c_val + pad, i - bar_h / 2 - 0.02, f"${c_val:,.0f}", va="center", ha="left",
                fontsize=7.3, color=SAGE_DARK, fontweight="bold")

    ax.set_yticks(y)
    ax.set_yticklabels(categories, fontsize=8.5, color=INK)
    ax.invert_yaxis()
    ax.set_xlim(0, max_val * 1.22)
    ax.set_xlabel("$ spent", fontsize=8)
    ax.legend(frameon=False, fontsize=8.5, loc="lower right")
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.grid(axis="x", color=HAIRLINE, linewidth=0.7, zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)
    return _save(fig, "category_comparison")


def cumulative_spend_chart(log_rows):
    """Running cumulative real spend for the current month, plus a dashed
    projection from today's pace out to month-end. Excludes today from the
    daily-rate calculation for the same reason every other chart here does --
    a partial day understates the true daily rate."""
    today = datetime.now().date()
    month_rows = [
        r for r in log_rows
        if r["_dt"].date().year == today.year and r["_dt"].date().month == today.month and r.get("day_spend")
    ]
    if len(month_rows) < 3:
        return None

    dates = [r["_dt"] for r in month_rows]
    spends = [float(r["day_spend"]) for r in month_rows]
    cum = []
    running = 0.0
    for s in spends:
        running += s
        cum.append(running)

    full_day_idxs = [i for i, d in enumerate(dates) if d.date() != today]
    if full_day_idxs:
        last_full = full_day_idxs[-1]
        rate = cum[last_full] / (last_full + 1)
    else:
        rate = cum[-1] / len(cum)

    days_in_month = calendar.monthrange(today.year, today.month)[1]
    projected_total = rate * days_in_month
    month_end = datetime(today.year, today.month, days_in_month)

    fig, ax = plt.subplots(figsize=SMALL_FIG)
    ax.plot(dates, cum, color=INK, linewidth=1.8, marker="o", markersize=3, label="Actual", zorder=3)
    ax.plot(
        [dates[-1], month_end], [cum[-1], projected_total],
        color=CLAY, linewidth=1.5, linestyle="--", zorder=2,
        label=f"Projected month-end (${projected_total:,.0f})",
    )
    ax.set_ylabel("$ cumulative", fontsize=8)
    _date_axis(ax)
    fig.autofmt_xdate(rotation=0, ha="center")
    ax.legend(frameon=False, fontsize=7, loc="upper left")
    _style_axes(ax)
    return _save(fig, "cumulative_spend")


def category_share_donut(months: dict):
    """Donut of the CURRENT month's spend by category (share of the month so
    far), using the same excluded one-off/catch-all buckets as the
    month-over-month comparison chart so the two visuals agree with each other."""
    today = datetime.now().date()
    current = months.get(today.strftime("%Y-%m"))
    if not current:
        return None
    cats = {
        c: v for c, v in current.get("categories", {}).items()
        if c not in COMPARISON_EXCLUDED_CATEGORIES and v > 0
    }
    if not cats:
        return None
    items = sorted(cats.items(), key=lambda kv: kv[1], reverse=True)
    labels = [c for c, _ in items]
    values = [v for _, v in items]
    total = sum(values)

    colors = [CATEGORY_COLORS.get(c, DEFAULT_CATEGORY_COLOR) for c in labels]

    fig, ax = plt.subplots(figsize=(4.6, 3.2))
    wedges, _ = ax.pie(
        values, colors=colors, startangle=90,
        wedgeprops={"width": 0.4, "edgecolor": BG, "linewidth": 1.5},
    )
    ax.text(0, 0.10, f"${total:,.0f}", ha="center", va="center", fontsize=13, color=INK, fontweight="bold")
    ax.text(0, -0.14, "this month", ha="center", va="center", fontsize=7.5, color=SOFT)
    ax.legend(
        wedges, [f"{c} — ${v:,.0f} ({v/total*100:.0f}%)" for c, v in items],
        frameon=False, fontsize=7, loc="center left", bbox_to_anchor=(1.0, 0.5),
    )
    ax.set_aspect("equal")
    return _save(fig, "category_share_donut")


def read_top_merchants():
    if not TOP_MERCHANTS.exists():
        return {}
    with open(TOP_MERCHANTS, encoding="utf-8") as f:
        return json.load(f)


def top_merchants_chart():
    """Horizontal bar of the current month's top real-spend merchants. Reads
    data/top_merchants.json -- see that file's _readme for how it's maintained
    (it requires per-transaction merchant aggregation, which only happens
    during the interactive Finance step, not in this script)."""
    data = read_top_merchants()
    today = datetime.now().date()
    if data.get("month") != today.strftime("%Y-%m"):
        return None
    merchants = data.get("merchants", {})
    if not merchants:
        return None

    items = sorted(merchants.items(), key=lambda kv: kv[1], reverse=True)[:10]
    items.reverse()  # so the largest ends up at the top of the horizontal bar chart
    labels = [m for m, _ in items]
    values = [v for _, v in items]

    fig, ax = plt.subplots(figsize=(6.4, max(2.4, 0.34 * len(items) + 0.5)))
    ax.barh(labels, values, color=SAGE, zorder=3)
    max_val = max(values) or 1
    for i, v in enumerate(values):
        ax.text(v + max_val * 0.015, i, f"${v:,.0f}", va="center", fontsize=8, color=INK)
    ax.set_xlim(0, max_val * 1.18)
    ax.set_xlabel("$ spent this month", fontsize=8)
    ax.spines["top"].set_visible(False)
    ax.spines["right"].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.grid(axis="x", color=HAIRLINE, linewidth=0.7, zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(length=0)
    return _save(fig, "top_merchants")


def main():
    renpho_rows = read_renpho_history()
    log_rows = read_daily_log()
    withings_rows = read_withings_history()
    category_months = read_category_totals()

    CHARTS_DIR.mkdir(parents=True, exist_ok=True)
    for f in CHARTS_DIR.glob("*.png"):
        f.unlink()

    manifest = {
        "weight_trend": weight_trend_chart(renpho_rows, log_rows),
        "body_comp_trend": body_comp_chart(renpho_rows),
        "composition_donut": composition_donut(renpho_rows),
        "weekly_change_bar": weekly_change_bar(renpho_rows),
        "steps_trend": steps_trend_chart(withings_rows),
        "sleep_trend": sleep_trend_chart(withings_rows),
        "resting_hr_trend": resting_hr_trend_chart(withings_rows),
        "spend_trend": spend_trend_chart(log_rows),
        "net_worth_trend": net_worth_chart(log_rows),
        "category_comparison": category_comparison_chart(category_months),
        "cumulative_spend": cumulative_spend_chart(log_rows),
        "category_share_donut": category_share_donut(category_months),
        "top_merchants": top_merchants_chart(),
    }

    with open(MANIFEST, "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2)

    available = {k: v for k, v in manifest.items() if v}
    print(f"Wrote {len(available)} chart(s) to {CHARTS_DIR}: {list(available.keys())}")
    skipped = [k for k, v in manifest.items() if not v]
    if skipped:
        print(f"Skipped (not enough history yet): {skipped}")


if __name__ == "__main__":
    main()
