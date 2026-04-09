"""Console and CSV logging for job applications."""

import csv
import logging
import os
from datetime import datetime
from pathlib import Path

_CSV_PATH = Path("applications.csv")
_CSV_COLUMNS: list[str] = [
    "date",
    "category",
    "company",
    "title",
    "location",
    "status",
    "reason",
    "linkedin_url",
]

_logger: logging.Logger | None = None


def setup_logger() -> logging.Logger:
    """Configure and return the application logger.

    Format: [YYYY-MM-DD HH:MM:SS] [CATEGORY] STATUS  message

    Returns:
        A configured logging.Logger instance.
    """
    global _logger

    logger = logging.getLogger("applier")
    logger.setLevel(logging.INFO)

    # Avoid adding duplicate handlers if called multiple times
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setLevel(logging.INFO)
        formatter = logging.Formatter("%(message)s")
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    _logger = logger
    return logger


def _get_logger() -> logging.Logger:
    """Return the existing logger or set one up."""
    global _logger
    if _logger is None:
        _logger = setup_logger()
    return _logger


def _ensure_csv() -> None:
    """Create the CSV file with headers if it does not exist."""
    if not _CSV_PATH.exists():
        with open(_CSV_PATH, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(_CSV_COLUMNS)


def log_application(
    category: str,
    company: str,
    title: str,
    location: str,
    status: str,
    reason: str,
    url: str,
) -> None:
    """Log an application to both the console and applications.csv.

    Args:
        category: Role category (e.g. "SWE", "MLAI", "FS", "DE").
        company: Company name.
        title: Job title.
        location: Job location.
        status: Application status (e.g. "APPLIED", "SKIPPED", "FAILED").
        reason: Reason for skip/failure, or empty string on success.
        url: LinkedIn job URL.
    """
    logger = _get_logger()
    now = datetime.now()
    timestamp = now.strftime("%Y-%m-%d %H:%M:%S")

    # Format: [2026-04-08 14:32:01] [SWE]  APPLIED  Junior Software Engineer @ Capital One (Dallas, TX)
    cat_field = f"[{category}]"
    detail = f"{title} @ {company}"
    if location:
        detail += f" ({location})"
    if reason:
        detail += f" ({reason})"

    log_line = f"[{timestamp}] {cat_field:<6} {status:<8} {detail}"
    logger.info(log_line)

    # Append to CSV
    _ensure_csv()
    with open(_CSV_PATH, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow([
            now.strftime("%Y-%m-%d %H:%M:%S"),
            category,
            company,
            title,
            location,
            status,
            reason,
            url,
        ])


def print_summary(stats: dict[str, dict[str, int]]) -> None:
    """Print an end-of-session summary table.

    Args:
        stats: A dict mapping category names to dicts with counts, e.g.
            {"SWE": {"applied": 23, "skipped": 4, "failed": 1}, ...}
    """
    logger = _get_logger()

    total_applied = 0
    total_skipped = 0
    total_failed = 0

    logger.info("Session complete:")

    for category, counts in stats.items():
        applied = counts.get("applied", 0)
        skipped = counts.get("skipped", 0)
        failed = counts.get("failed", 0)
        total_applied += applied
        total_skipped += skipped
        total_failed += failed
        logger.info(
            f"  {category + ':':<6} {applied} applied, {skipped} skipped, {failed} failed"
        )

    logger.info(
        f"  Total: {total_applied} applied, {total_skipped} skipped, {total_failed} failed"
    )
