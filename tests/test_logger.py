"""Tests for applier.logger — console and CSV logging."""

import csv
from pathlib import Path
from unittest.mock import patch

import pytest

from applier import logger as logger_module
from applier.logger import (
    _CSV_COLUMNS,
    log_application,
    print_summary,
    setup_logger,
)


# ============================================================================
# CSV file creation and headers
# ============================================================================


class TestCSVCreation:
    """Test that the CSV file is created with correct headers."""

    def test_csv_created_with_headers_on_first_log(self, tmp_path) -> None:
        csv_file = tmp_path / "applications.csv"
        with patch.object(logger_module, "_CSV_PATH", csv_file):
            log_application(
                category="SWE",
                company="Google",
                title="Junior Software Engineer",
                location="Dallas, TX",
                status="APPLIED",
                reason="",
                url="https://linkedin.com/jobs/123",
            )

        assert csv_file.exists()
        with open(csv_file, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            header = next(reader)
            assert header == _CSV_COLUMNS

    def test_csv_columns_match_spec(self) -> None:
        expected = [
            "date",
            "category",
            "company",
            "title",
            "location",
            "status",
            "reason",
            "linkedin_url",
        ]
        assert _CSV_COLUMNS == expected


# ============================================================================
# CSV append behavior
# ============================================================================


class TestCSVAppend:
    """Test that multiple log calls append rows correctly."""

    def test_multiple_logs_append_rows(self, tmp_path) -> None:
        csv_file = tmp_path / "applications.csv"
        with patch.object(logger_module, "_CSV_PATH", csv_file):
            log_application(
                category="SWE",
                company="Google",
                title="Junior SWE",
                location="Dallas, TX",
                status="APPLIED",
                reason="",
                url="https://linkedin.com/jobs/1",
            )
            log_application(
                category="MLAI",
                company="Meta",
                title="ML Intern",
                location="Remote",
                status="SKIPPED",
                reason="title blacklist",
                url="https://linkedin.com/jobs/2",
            )
            log_application(
                category="DE",
                company="Amazon",
                title="Data Engineer I",
                location="Plano, TX",
                status="FAILED",
                reason="form error",
                url="https://linkedin.com/jobs/3",
            )

        with open(csv_file, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)

        # 1 header + 3 data rows
        assert len(rows) == 4

        # Verify data in second row (first data row)
        data_row = rows[1]
        assert data_row[1] == "SWE"
        assert data_row[2] == "Google"
        assert data_row[3] == "Junior SWE"
        assert data_row[5] == "APPLIED"

        # Third row
        assert rows[2][1] == "MLAI"
        assert rows[2][5] == "SKIPPED"
        assert rows[2][6] == "title blacklist"

    def test_csv_row_has_correct_column_count(self, tmp_path) -> None:
        csv_file = tmp_path / "applications.csv"
        with patch.object(logger_module, "_CSV_PATH", csv_file):
            log_application(
                category="FS",
                company="Netflix",
                title="Full Stack Dev",
                location="Irving, TX",
                status="APPLIED",
                reason="",
                url="https://linkedin.com/jobs/99",
            )

        with open(csv_file, newline="", encoding="utf-8") as f:
            reader = csv.reader(f)
            rows = list(reader)

        for row in rows:
            assert len(row) == len(_CSV_COLUMNS), (
                f"Row has {len(row)} columns, expected {len(_CSV_COLUMNS)}"
            )


# ============================================================================
# print_summary
# ============================================================================


class TestPrintSummary:
    """Test summary output format."""

    def test_print_summary_outputs_categories(self, capsys) -> None:
        # Ensure logger is set up to use stdout via capsys
        log = setup_logger()

        stats = {
            "SWE": {"applied": 23, "skipped": 4, "failed": 1},
            "FS": {"applied": 18, "skipped": 6, "failed": 0},
            "MLAI": {"applied": 12, "skipped": 3, "failed": 2},
            "DE": {"applied": 15, "skipped": 5, "failed": 1},
        }

        print_summary(stats)
        captured = capsys.readouterr()

        assert "Session complete:" in captured.err
        assert "SWE:" in captured.err
        assert "23 applied" in captured.err
        assert "Total:" in captured.err
        assert "68 applied" in captured.err
        assert "18 skipped" in captured.err
        assert "4 failed" in captured.err

    def test_print_summary_handles_empty_stats(self, capsys) -> None:
        setup_logger()
        print_summary({})
        captured = capsys.readouterr()
        assert "Session complete:" in captured.err
        assert "Total: 0 applied, 0 skipped, 0 failed" in captured.err

    def test_print_summary_handles_missing_keys(self, capsys) -> None:
        setup_logger()
        stats = {"SWE": {"applied": 5}}
        print_summary(stats)
        captured = capsys.readouterr()
        assert "5 applied" in captured.err
        assert "0 skipped" in captured.err
