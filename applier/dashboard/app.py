"""Flask application entry point for the Synner dashboard."""

from __future__ import annotations

import csv
import json
import os
import signal
import subprocess
import sys
import threading
import time
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Generator
import random

import yaml
from flask import (
    Flask,
    Response,
    jsonify,
    render_template,
    request,
)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_CSV_PATH = _PROJECT_ROOT / "applications.csv"
_CONFIG_PATH = _PROJECT_ROOT / "config.yaml"
_RUN_SCRIPT = _PROJECT_ROOT / "run.py"
_LOG_PATH = _PROJECT_ROOT / ".session_log"
_BOUNDS_PATH = _PROJECT_ROOT / ".session_boundaries.json"

# ---------------------------------------------------------------------------
# Subprocess management
# ---------------------------------------------------------------------------

_process_lock = threading.Lock()
_current_process: subprocess.Popen | None = None
_session_start_time: float | None = None
_log_file_handle = None


def _is_process_running() -> bool:
    """Check whether the managed subprocess is still alive."""
    with _process_lock:
        if _current_process is None:
            return False
        return _current_process.poll() is None


# ---------------------------------------------------------------------------
# Session boundary tracking
# ---------------------------------------------------------------------------
#
# Persists the start/end timestamps of the most recent two dashboard-launched
# sessions to .session_boundaries.json. Used to split CSV rows into
# "current session" / "previous session" / "alltime" buckets for the UI.
#
# Shape:
#   {
#     "current":  {"start": 1712789000.0, "end": null},  # null while running
#     "previous": {"start": 1712700000.0, "end": 1712710000.0}
#   }


def _load_session_bounds() -> dict:
    """Load the persisted session boundary file, or return empty defaults."""
    if not _BOUNDS_PATH.exists():
        return {"current": None, "previous": None}
    try:
        with open(_BOUNDS_PATH, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return {"current": None, "previous": None}
        return {
            "current": data.get("current"),
            "previous": data.get("previous"),
        }
    except (OSError, json.JSONDecodeError):
        return {"current": None, "previous": None}


def _save_session_bounds(bounds: dict) -> None:
    """Persist the session boundary dict to disk."""
    try:
        with open(_BOUNDS_PATH, "w", encoding="utf-8") as fh:
            json.dump(bounds, fh)
    except OSError:
        pass


def _begin_session(start_ts: float) -> None:
    """Rotate current→previous and set a new current session window."""
    bounds = _load_session_bounds()
    old_current = bounds.get("current")
    if old_current is not None:
        # Close out a previously-running session that never got its end set
        # (e.g., dashboard crashed mid-run). Best-effort — use start_ts as
        # the end since that's the latest thing we know for sure.
        if old_current.get("end") is None:
            old_current["end"] = start_ts
        bounds["previous"] = old_current
    bounds["current"] = {"start": start_ts, "end": None}
    _save_session_bounds(bounds)


def _end_session(end_ts: float) -> None:
    """Close the current session window by setting its end timestamp."""
    bounds = _load_session_bounds()
    current = bounds.get("current")
    if current is not None and current.get("end") is None:
        current["end"] = end_ts
        bounds["current"] = current
        _save_session_bounds(bounds)


def _reconcile_session_bounds() -> dict:
    """Return session bounds, auto-closing current if the process has died.

    The subprocess can exit without triggering /api/stop (completed normally,
    crashed, Ctrl+C'd in terminal). On each read, check if we still think a
    session is running and verify the subprocess is actually alive.
    """
    bounds = _load_session_bounds()
    current = bounds.get("current")
    if current is not None and current.get("end") is None and not _is_process_running():
        current["end"] = time.time()
        bounds["current"] = current
        _save_session_bounds(bounds)
    return bounds


# ---------------------------------------------------------------------------
# CSV helpers
# ---------------------------------------------------------------------------

_CSV_COLUMNS = ["date", "category", "company", "title", "location", "status", "reason", "linkedin_url"]


def _read_csv() -> list[dict]:
    """Read applications.csv and return a list of row dicts."""
    if not _CSV_PATH.exists():
        return []
    rows: list[dict] = []
    with open(_CSV_PATH, "r", newline="", encoding="utf-8") as fh:
        reader = csv.DictReader(fh)
        for row in reader:
            rows.append(row)
    return rows


def _compute_stats(rows: list[dict]) -> dict:
    """Compute aggregate statistics from CSV rows."""
    total = len(rows)
    applied = sum(1 for r in rows if r.get("status", "").lower() in ("applied", "APPLIED"))
    success_rate = round(applied / total * 100) if total > 0 else 0

    companies = Counter(r.get("company", "") for r in rows if r.get("company"))
    locations = Counter(r.get("location", "") for r in rows if r.get("location"))

    return {
        "total": total,
        "applied": applied,
        "success_rate": success_rate,
        "top_companies": companies.most_common(10),
        "top_locations": locations.most_common(10),
    }


# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------


def _load_config() -> dict:
    """Load config.yaml, returning defaults if missing."""
    if not _CONFIG_PATH.exists():
        return {
            "openai_api_key": "sk-...",
            "linkedin_profile_dir": "./chrome_profile",
            "resume_dir": "~/Documents/resumes/pdfs",
            "max_applications_per_session": 100,
            "max_per_category": 30,
            "delay_min_seconds": 30,
            "delay_max_seconds": 60,
            "search_delay_min_seconds": 120,
            "search_delay_max_seconds": 300,
            "headless": False,
        }
    with open(_CONFIG_PATH, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def _mask_api_key(key: str) -> str:
    """Mask an API key for display, showing only the last 4 characters."""
    if not key or key == "sk-..." or len(key) < 8:
        return ""
    return "sk-..." + key[-4:]


def _save_config(data: dict) -> None:
    """Write configuration dict to config.yaml with comments."""
    lines = [
        "# Synner configuration file",
        "# Copy this file and fill in your actual values",
        "",
        "# OpenAI API key for GPT-4o-mini screening question answers",
        f'openai_api_key: "{data.get("openai_api_key", "sk-...")}"',
        "",
        "# Path to Chrome profile directory for persisted LinkedIn session",
        f'linkedin_profile_dir: "{data.get("linkedin_profile_dir", "./chrome_profile")}"',
        "",
        "# Directory containing resume PDF files",
        f'resume_dir: "{data.get("resume_dir", "~/Documents/resumes/pdfs")}"',
        "",
        "# Maximum total applications to submit in one session",
        f'max_applications_per_session: {data.get("max_applications_per_session", 100)}',
        "",
        "# Maximum applications per role category (SWE, FS, MLAI, DE) per session",
        f'max_per_category: {data.get("max_per_category", 30)}',
        "",
        "# Minimum delay (seconds) between individual applications",
        f'delay_min_seconds: {data.get("delay_min_seconds", 30)}',
        "",
        "# Maximum delay (seconds) between individual applications",
        f'delay_max_seconds: {data.get("delay_max_seconds", 60)}',
        "",
        "# Minimum delay (seconds) between search queries",
        f'search_delay_min_seconds: {data.get("search_delay_min_seconds", 120)}',
        "",
        "# Maximum delay (seconds) between search queries",
        f'search_delay_max_seconds: {data.get("search_delay_max_seconds", 300)}',
        "",
        "# Set true to run Chrome without a visible browser window",
        f'headless: {"true" if data.get("headless") else "false"}',
        "",
    ]
    with open(_CONFIG_PATH, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines))


# ---------------------------------------------------------------------------
# Resume map (from config module)
# ---------------------------------------------------------------------------

RESUME_MAP = {
    "SWE": "Resume_SWE.pdf",
    "FS": "Resume_FS.pdf",
    "MLAI": "Resume_MLAI.pdf",
    "DE": "Resume_DE.pdf",
}


# ---------------------------------------------------------------------------
# Mock data generator (kept for dashboard when no CSV exists)
# ---------------------------------------------------------------------------

_COMPANIES = [
    "Capital One", "Toyota", "AT&T", "Lockheed Martin", "Texas Instruments",
    "JPMorgan Chase", "Goldman Sachs", "Meta", "Google", "Amazon",
    "Microsoft", "Cisco", "Dell", "Oracle", "Salesforce",
    "Deloitte", "Accenture", "NVIDIA", "Apple", "IBM",
]

_TITLES = {
    "SWE": [
        "Junior Software Engineer", "Software Engineer Intern",
        "Software Developer I", "Associate Software Engineer",
        "Software Engineer New Grad",
    ],
    "FS": [
        "Fullstack Developer", "Full Stack Engineer Intern",
        "Junior Web Developer", "Fullstack Engineer",
    ],
    "MLAI": [
        "ML Engineer Intern", "Data Scientist Junior",
        "AI Engineer Entry Level", "Machine Learning Intern",
    ],
    "DE": [
        "Data Engineer Intern", "Junior Data Engineer",
        "ETL Developer", "Data Pipeline Engineer",
    ],
}

_LOCATIONS = [
    "Dallas, TX", "Fort Worth, TX", "Arlington, TX", "Plano, TX",
    "Frisco, TX", "Irving, TX", "Richardson, TX", "Remote",
]

_SKIP_REASONS = [
    "title blacklist: senior", "title blacklist: staff",
    "title blacklist: lead", "already applied",
    "description: 5+ years required",
]

_FAIL_REASONS = [
    "form error: required field missing",
    "form error: upload timeout",
    "modal blocked submission",
    "network timeout",
]


def _build_mock_data() -> dict:
    """Generate realistic placeholder data for the dashboard."""
    random.seed(42)

    session = {"applied": 68, "skipped": 18, "failed": 4, "total": 90}
    alltime = {"applied": 312, "skipped": 87, "failed": 19, "total": 418}
    trends = {"applied": 12.7, "skipped": -5.3, "failed": -34.5}

    categories = {
        "SWE": {"applied": 23, "skipped": 4, "failed": 1, "limit": 30},
        "FS":  {"applied": 18, "skipped": 6, "failed": 0, "limit": 30},
        "MLAI": {"applied": 12, "skipped": 3, "failed": 2, "limit": 30},
        "DE":  {"applied": 15, "skipped": 5, "failed": 1, "limit": 30},
    }

    feed = []
    base_time = datetime(2026, 4, 8, 14, 30, 0)
    statuses = ["applied"] * 12 + ["skipped"] * 4 + ["failed"] * 2
    random.shuffle(statuses)

    for i, status in enumerate(statuses):
        cat = random.choice(["SWE", "FS", "MLAI", "DE"])
        company = random.choice(_COMPANIES)
        title = random.choice(_TITLES[cat])
        location = random.choice(_LOCATIONS)
        ts = base_time + timedelta(seconds=i * random.randint(35, 70))

        reason = ""
        if status == "skipped":
            reason = random.choice(_SKIP_REASONS)
        elif status == "failed":
            reason = random.choice(_FAIL_REASONS)

        feed.append({
            "time": ts.strftime("%I:%M %p"),
            "timestamp": ts.strftime("%Y-%m-%d %H:%M:%S"),
            "category": cat,
            "company": company,
            "title": title,
            "location": location,
            "status": status,
            "reason": reason,
        })

    feed.reverse()

    success_rate = round(
        session["applied"] / session["total"] * 100
    ) if session["total"] > 0 else 0

    radar = {}
    for cat, vals in categories.items():
        radar[cat] = round(vals["applied"] / vals["limit"], 2)

    return {
        "session": session,
        "alltime": alltime,
        "trends": trends,
        "categories": categories,
        "feed": feed,
        "success_rate": success_rate,
        "radar": radar,
        "status": "running",
        "session_elapsed": "01:23:45",
        "user": "Synner User",
    }


def _parse_row_ts(row: dict) -> float | None:
    """Parse a CSV row's date field into a unix timestamp, or None on failure."""
    date_str = row.get("date", "")
    if not date_str:
        return None
    try:
        dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
        return dt.timestamp()
    except ValueError:
        return None


def _aggregate_bucket(rows: list[dict]) -> dict:
    """Compute stat totals, category breakdowns, and radar values for a bucket."""
    cat_stats: dict[str, dict[str, int]] = {}
    for cat in ("SWE", "FS", "MLAI", "DE"):
        cat_stats[cat] = {"applied": 0, "skipped": 0, "failed": 0, "limit": 30}

    applied = skipped = failed = 0
    for row in rows:
        status = (row.get("status") or "").upper()
        cat = row.get("category", "")
        if status == "APPLIED":
            applied += 1
        elif status == "SKIPPED":
            skipped += 1
        else:
            failed += 1
        if cat in cat_stats:
            if status == "APPLIED":
                cat_stats[cat]["applied"] += 1
            elif status == "SKIPPED":
                cat_stats[cat]["skipped"] += 1
            else:
                cat_stats[cat]["failed"] += 1

    total = applied + skipped + failed
    success_rate = round(applied / total * 100) if total > 0 else 0
    radar = {
        cat: round(vals["applied"] / vals["limit"], 2) if vals["limit"] > 0 else 0
        for cat, vals in cat_stats.items()
    }
    return {
        "applied": applied,
        "skipped": skipped,
        "failed": failed,
        "total": total,
        "categories": cat_stats,
        "radar": radar,
        "success_rate": success_rate,
    }


def _split_rows_by_bounds(rows: list[dict], bounds: dict) -> dict:
    """Return (current_rows, previous_rows, all_rows) split by session bounds."""
    current_rows: list[dict] = []
    previous_rows: list[dict] = []

    cur_bound = bounds.get("current")
    prev_bound = bounds.get("previous")

    cur_start = cur_bound["start"] if cur_bound else None
    cur_end = cur_bound.get("end") if cur_bound else None
    prev_start = prev_bound["start"] if prev_bound else None
    prev_end = prev_bound.get("end") if prev_bound else None

    for row in rows:
        ts = _parse_row_ts(row)
        if ts is None:
            continue
        if cur_start is not None and ts >= cur_start:
            if cur_end is None or ts <= cur_end:
                current_rows.append(row)
                continue
        if prev_start is not None and prev_end is not None:
            if prev_start <= ts <= prev_end:
                previous_rows.append(row)

    return {"current": current_rows, "previous": previous_rows, "alltime": rows}


def _build_real_data() -> dict:
    """Build dashboard data from the real applications.csv file.

    Returns three buckets — current session, previous session, all-time —
    each with its own totals, per-category breakdown, success rate, and
    radar values. The frontend switches between them via tabs.
    """
    rows = _read_csv()
    bounds = _reconcile_session_bounds()

    split = _split_rows_by_bounds(rows, bounds)
    current_bucket = _aggregate_bucket(split["current"])
    previous_bucket = _aggregate_bucket(split["previous"])
    alltime_bucket = _aggregate_bucket(split["alltime"])

    running = _is_process_running()

    # Build feed from last 50 rows (most recent first)
    feed = []
    for row in reversed(rows[-50:]):
        time_str = ""
        date_str = row.get("date", "")
        try:
            dt = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
            time_str = dt.strftime("%I:%M %p")
        except ValueError:
            time_str = date_str

        feed.append({
            "time": time_str,
            "timestamp": date_str,
            "category": row.get("category", ""),
            "company": row.get("company", ""),
            "title": row.get("title", ""),
            "location": row.get("location", ""),
            "status": (row.get("status") or "").lower(),
            "reason": row.get("reason", ""),
        })

    # The "active" bucket is what the default tab shows on load:
    # running session → current, idle → previous (fall back to alltime if
    # there's no previous session yet).
    if running:
        active_bucket = current_bucket
        active_label = "current"
    elif previous_bucket["total"] > 0:
        active_bucket = previous_bucket
        active_label = "previous"
    else:
        active_bucket = alltime_bucket
        active_label = "alltime"

    return {
        # Legacy keys kept for template compatibility — point at the active
        # bucket so unmodified server-side render shows sensible defaults.
        "session": {
            "applied": active_bucket["applied"],
            "skipped": active_bucket["skipped"],
            "failed": active_bucket["failed"],
            "total": active_bucket["total"],
        },
        "alltime": {
            "applied": alltime_bucket["applied"],
            "skipped": alltime_bucket["skipped"],
            "failed": alltime_bucket["failed"],
            "total": alltime_bucket["total"],
        },
        "trends": {"applied": 0, "skipped": 0, "failed": 0},
        "categories": active_bucket["categories"],
        "feed": feed,
        "success_rate": active_bucket["success_rate"],
        "radar": active_bucket["radar"],
        "status": "running" if running else "idle",
        "session_elapsed": "00:00:00",
        "user": "Synner User",

        # New: full bucket data consumed by the tab-switching JS.
        "buckets": {
            "current": current_bucket,
            "previous": previous_bucket,
            "alltime": alltime_bucket,
        },
        "active_bucket": active_label,
        "has_previous": previous_bucket["total"] > 0,
    }


# ---------------------------------------------------------------------------
# Flask app factory
# ---------------------------------------------------------------------------


def create_app() -> Flask:
    """Create and configure the Flask application."""
    app = Flask(
        __name__,
        static_folder="static",
        template_folder="templates",
    )
    app.secret_key = os.urandom(24)

    # ── Dashboard ─────────────────────────────────────────────────────────

    @app.route("/")
    def dashboard() -> str:
        """Serve the main dashboard page with real CSV data."""
        return render_template(
            "dashboard.html",
            data=_build_real_data(),
            active_page="dashboard",
        )

    @app.route("/api/feed")
    def api_feed() -> tuple:
        """Return the live feed entries as JSON."""
        data = _build_real_data()
        return jsonify(data["feed"])

    @app.route("/api/stats")
    def api_stats() -> tuple:
        """Return current stats as JSON, including all three buckets."""
        data = _build_real_data()
        return jsonify({
            "status": data["status"],
            "active_bucket": data["active_bucket"],
            "has_previous": data["has_previous"],
            "buckets": data["buckets"],
        })

    # ── History ───────────────────────────────────────────────────────────

    @app.route("/history")
    def history() -> str:
        """Serve the session history page."""
        rows = _read_csv()
        stats = _compute_stats(rows)
        return render_template(
            "history.html",
            rows=rows,
            stats=stats,
            active_page="history",
        )

    # ── Settings ──────────────────────────────────────────────────────────

    @app.route("/settings", methods=["GET", "POST"])
    def settings():
        """Display or save configuration."""
        if request.method == "POST":
            try:
                config = _load_config()
                # Only update API key if user provided a new one (not the masked placeholder)
                new_key = request.form.get("openai_api_key", "").strip()
                if new_key and not new_key.startswith("sk-..."):
                    config["openai_api_key"] = new_key
                config["delay_min_seconds"] = int(
                    request.form.get("delay_min_seconds", 30)
                )
                config["delay_max_seconds"] = int(
                    request.form.get("delay_max_seconds", 60)
                )
                config["search_delay_min_seconds"] = int(
                    request.form.get("search_delay_min_seconds", 120)
                )
                config["search_delay_max_seconds"] = int(
                    request.form.get("search_delay_max_seconds", 300)
                )
                config["max_applications_per_session"] = int(
                    request.form.get("max_applications_per_session", 100)
                )
                config["max_per_category"] = int(
                    request.form.get("max_per_category", 30)
                )
                config["headless"] = "headless" in request.form

                _save_config(config)
                return jsonify({"success": True})
            except Exception as exc:
                return jsonify({"success": False, "error": str(exc)})

        config = _load_config()
        config["openai_api_key_masked"] = _mask_api_key(config.get("openai_api_key", ""))
        return render_template(
            "settings.html",
            config=config,
            resume_map=RESUME_MAP,
            flash_msg=None,
            flash_type=None,
            active_page="settings",
        )

    # ── Controls ──────────────────────────────────────────────────────────

    @app.route("/controls")
    def controls() -> str:
        """Serve the run controls page."""
        config = _load_config()
        return render_template(
            "controls.html",
            config=config,
            active_page="controls",
        )

    @app.route("/api/start", methods=["POST"])
    def api_start():
        """Start run.py as a subprocess."""
        global _current_process, _session_start_time, _log_file_handle
        with _process_lock:
            if _current_process is not None and _current_process.poll() is None:
                return jsonify({"success": False, "error": "Session already running"})

            body = request.get_json(silent=True) or {}
            categories = body.get("categories", [])
            dry_run = body.get("dry_run", False)
            headless = body.get("headless", False)

            cmd = [sys.executable, "-u", str(_RUN_SCRIPT)]
            # Forward the full selected-category list. If the user unchecks
            # everything we refuse the start rather than silently running all
            # four via run.py's default.
            if categories:
                cmd.append("--category")
                cmd.extend(categories)
            else:
                return jsonify({
                    "success": False,
                    "error": "Select at least one category before starting a session.",
                })
            if dry_run:
                cmd.append("--dry-run")
            if headless:
                cmd.append("--headless")

            try:
                # Close previous log handle if any
                if _log_file_handle and not _log_file_handle.closed:
                    _log_file_handle.close()

                # Clear previous log
                if _LOG_PATH.exists():
                    _LOG_PATH.unlink()

                _log_file_handle = open(_LOG_PATH, "w", encoding="utf-8", buffering=1)
                _current_process = subprocess.Popen(
                    cmd,
                    cwd=str(_PROJECT_ROOT),
                    stdout=_log_file_handle,
                    stderr=subprocess.STDOUT,
                )
                _session_start_time = time.time()
                # Rotate current→previous in the persisted boundary file so
                # the dashboard can split CSV rows into the correct buckets.
                _begin_session(_session_start_time)
                return jsonify({"success": True, "pid": _current_process.pid, "start_time": _session_start_time})
            except Exception as exc:
                return jsonify({"success": False, "error": str(exc)})

    @app.route("/api/stop", methods=["POST"])
    def api_stop():
        """Stop the running subprocess."""
        global _current_process, _session_start_time, _log_file_handle
        with _process_lock:
            if _current_process is None or _current_process.poll() is not None:
                _current_process = None
                _session_start_time = None
                if _log_file_handle and not _log_file_handle.closed:
                    _log_file_handle.close()
                    _log_file_handle = None
                _end_session(time.time())
                return jsonify({"success": True, "message": "No session running"})

            try:
                _current_process.send_signal(signal.SIGINT)
                try:
                    _current_process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    _current_process.kill()
                    _current_process.wait(timeout=5)
                _current_process = None
                _session_start_time = None
                if _log_file_handle and not _log_file_handle.closed:
                    _log_file_handle.close()
                    _log_file_handle = None
                _end_session(time.time())
                return jsonify({"success": True})
            except Exception as exc:
                return jsonify({"success": False, "error": str(exc)})

    @app.route("/api/status")
    def api_status():
        """Return current process status and session start time."""
        running = _is_process_running()
        return jsonify({
            "running": running,
            "start_time": _session_start_time if running else None,
        })

    # ── Terminal Log Stream ─────────────────────────────────────────────

    @app.route("/api/logs")
    def api_logs():
        """Server-Sent Events endpoint that tails the session log file."""

        def generate_logs() -> Generator[str, None, None]:
            yield "event: connected\ndata: {}\n\n"

            # Use binary mode to avoid byte/character offset mismatch
            last_pos = 0
            if _LOG_PATH.exists():
                try:
                    with open(_LOG_PATH, "rb") as fh:
                        content = fh.read().decode("utf-8", errors="replace")
                    if content:
                        yield "event: log\ndata: " + json.dumps({"text": content}) + "\n\n"
                    last_pos = _LOG_PATH.stat().st_size
                except Exception:
                    pass

            while True:
                time.sleep(0.5)

                if not _LOG_PATH.exists():
                    yield ": keepalive\n\n"
                    continue

                try:
                    current_size = _LOG_PATH.stat().st_size
                except OSError:
                    yield ": keepalive\n\n"
                    continue

                if current_size <= last_pos:
                    yield ": keepalive\n\n"
                    continue

                try:
                    with open(_LOG_PATH, "rb") as fh:
                        fh.seek(last_pos)
                        new_data = fh.read().decode("utf-8", errors="replace")
                    last_pos = current_size

                    if new_data.strip():
                        yield "event: log\ndata: " + json.dumps({"text": new_data}) + "\n\n"
                except Exception:
                    pass

        return Response(
            generate_logs(),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    # ── SSE Stream ────────────────────────────────────────────────────────

    @app.route("/api/stream")
    def api_stream():
        """Server-Sent Events endpoint that tails applications.csv."""

        def generate() -> Generator[str, None, None]:
            # Send initial keepalive
            yield "event: connected\ndata: {}\n\n"

            last_size = 0
            if _CSV_PATH.exists():
                last_size = _CSV_PATH.stat().st_size

            while True:
                time.sleep(1)

                if not _CSV_PATH.exists():
                    # Send keepalive
                    yield ": keepalive\n\n"
                    continue

                current_size = _CSV_PATH.stat().st_size
                if current_size <= last_size:
                    # Send keepalive every ~15 seconds
                    yield ": keepalive\n\n"
                    continue

                # Read new lines
                try:
                    with open(_CSV_PATH, "r", newline="", encoding="utf-8") as fh:
                        fh.seek(last_size)
                        new_data = fh.read()

                    last_size = current_size

                    for line in new_data.strip().split("\n"):
                        if not line.strip():
                            continue
                        parts = list(csv.reader([line]))[0]
                        if len(parts) >= 7 and parts[0] != "date":
                            entry = {
                                "date": parts[0],
                                "category": parts[1],
                                "company": parts[2],
                                "title": parts[3],
                                "location": parts[4],
                                "status": parts[5].lower(),
                                "reason": parts[6] if len(parts) > 6 else "",
                                "time": "",
                            }
                            # Parse time for display
                            try:
                                dt = datetime.strptime(parts[0], "%Y-%m-%d %H:%M:%S")
                                entry["time"] = dt.strftime("%I:%M %p")
                            except ValueError:
                                entry["time"] = parts[0]

                            yield "event: activity\ndata: " + json.dumps(entry) + "\n\n"
                except Exception:
                    pass

        return Response(
            generate(),
            mimetype="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
                "Connection": "keep-alive",
            },
        )

    return app


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------


def main() -> None:
    """Run the dashboard server."""
    app = create_app()
    print("\n  Synner Dashboard running at http://127.0.0.1:5050\n")
    app.run(host="127.0.0.1", port=5050, debug=True, threaded=True)


if __name__ == "__main__":
    main()
