#!/usr/bin/env python3
"""Entry point for the Synner automated LinkedIn job application bot."""

from __future__ import annotations

import argparse
import random
import signal
import sys
import time
from types import FrameType
from typing import Any

from applier.config import load_config, load_resume
from applier.linkedin import create_driver, run_category
from applier.llm import create_client
from applier.logger import print_summary

# ── Categories ──────────────────────────────────────────────────────────────

CATEGORIES: list[str] = ["SWE", "FS", "MLAI", "DE"]

# ── Graceful shutdown ───────────────────────────────────────────────────────

_shutdown_requested: bool = False


def _handle_sigint(sig: int, frame: FrameType | None) -> None:
    """Set shutdown flag on Ctrl+C so the main loop can exit cleanly."""
    global _shutdown_requested
    _shutdown_requested = True
    print("\n[!] Shutdown requested — finishing current application then exiting…")


# ── Argument parsing ───────────────────────────────────────────────────────


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Synner — automated LinkedIn Easy Apply bot",
    )
    parser.add_argument(
        "--category",
        choices=CATEGORIES,
        default=None,
        help="Run a single resume category instead of all four",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Search and match jobs but do not submit applications",
    )
    parser.add_argument(
        "--headless",
        action="store_true",
        help="Run Chrome in headless mode (overrides config.yaml)",
    )
    return parser.parse_args(argv)


# ── Delay helpers ───────────────────────────────────────────────────────────


def _sleep_between_apps(config: dict[str, Any]) -> None:
    """Sleep for a randomised delay between individual applications."""
    lo: int = config.get("delay_min_seconds", 30)
    hi: int = config.get("delay_max_seconds", 60)
    delay = random.uniform(lo, hi)
    print(f"    ⏳ Waiting {delay:.0f}s before next application…")
    time.sleep(delay)


def _sleep_between_searches(config: dict[str, Any]) -> None:
    """Sleep for a randomised delay between search-keyword rounds."""
    lo: int = config.get("search_delay_min_seconds", 120)
    hi: int = config.get("search_delay_max_seconds", 300)
    delay = random.uniform(lo, hi)
    print(f"    ⏳ Waiting {delay:.0f}s before next search…")
    time.sleep(delay)


# ── Main orchestrator ──────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> None:
    """Run the Synner session."""
    global _shutdown_requested

    args = parse_args(argv)

    # Load configuration and resume data
    config: dict[str, Any] = load_config()
    resume_data: dict[str, Any] = load_resume()

    # CLI overrides
    if args.headless:
        config["headless"] = True

    max_session: int = config.get("max_applications_per_session", 100)
    max_category: int = config.get("max_per_category", 30)

    categories = [args.category] if args.category else CATEGORIES

    # Install Ctrl+C handler
    signal.signal(signal.SIGINT, _handle_sigint)

    # Initialize the OpenAI client for screening questions
    create_client(config["openai_api_key"])

    # Launch browser
    driver = create_driver(config)

    total_applied: int = 0
    session_stats: dict[str, dict[str, int]] = {}

    print("=" * 60)
    print("Synner — LinkedIn Easy Apply Bot")
    if args.dry_run:
        print("  *** DRY-RUN MODE — no applications will be submitted ***")
    print(f"  Categories : {', '.join(categories)}")
    print(f"  Session cap: {max_session} | Per-category cap: {max_category}")
    print("=" * 60)

    try:
        for category in categories:
            if _shutdown_requested:
                print(f"\n[!] Skipping category {category} due to shutdown request.")
                break

            if total_applied >= max_session:
                print(f"\n[!] Session limit ({max_session}) reached — stopping.")
                break

            remaining_session = max_session - total_applied
            effective_cap = min(max_category, remaining_session)

            print(f"\n{'─' * 50}")
            print(f"  Starting category: {category}  (cap: {effective_cap})")
            print(f"{'─' * 50}")

            # Prepare a mutable stats dict for this category; override
            # the per-category cap so linkedin.run_category respects the
            # session-level remaining budget.
            stats: dict[str, int] = {"applied": 0, "skipped": 0, "failed": 0}
            cat_config = {**config, "max_per_category": effective_cap}

            try:
                run_category(
                    driver=driver,
                    category=category,
                    cfg=cat_config,
                    resume_data=resume_data,
                    stats=stats,
                    shutdown_check=lambda: _shutdown_requested,
                    dry_run=args.dry_run,
                )
            except KeyboardInterrupt:
                _shutdown_requested = True
                print(f"\n[!] Interrupted during category {category}.")

            session_stats[category] = stats
            total_applied += stats.get("applied", 0)

            # Pause between categories (unless shutting down or last category)
            if not _shutdown_requested and category != categories[-1]:
                _sleep_between_searches(config)
    finally:
        # ── End-of-session summary ──────────────────────────────────────
        print()
        print_summary(session_stats)
        driver.quit()


if __name__ == "__main__":
    main()
