"""Tests for applier.filters — title and description blacklist filtering."""

import pytest

from applier.filters import should_skip_title, should_skip_description


# ============================================================================
# Title blacklist: each blacklisted term should cause a skip
# ============================================================================


class TestTitleBlacklist:
    """Every blacklisted keyword in the title should return (True, reason)."""

    @pytest.mark.parametrize(
        "title",
        [
            "Senior Software Engineer",
            "Sr. Backend Developer",
            "Sr Developer",  # "sr " with trailing space
            "Staff Engineer",
            "Lead Data Scientist",
            "Team Leader Engineering",
            "Principal Engineer",
            "Engineering Manager",
            "Product Management Associate",
            "Director of Engineering",
            "Head of Data Science",
            "VP of Engineering",
            "Vice President of Technology",
        ],
    )
    def test_blacklisted_titles_are_blocked(self, title: str) -> None:
        skip, reason = should_skip_title(title)
        assert skip is True, f"Expected '{title}' to be blocked, but it passed"
        assert reason, "Reason should not be empty when blocked"

    @pytest.mark.parametrize(
        "title",
        [
            "senior developer",
            "SENIOR DEVELOPER",
            "Senior Developer",
            "sEnIoR Developer",
        ],
    )
    def test_case_insensitivity(self, title: str) -> None:
        skip, _ = should_skip_title(title)
        assert skip is True, f"'{title}' should be blocked regardless of case"

    def test_sr_dot_blocked(self) -> None:
        skip, reason = should_skip_title("Sr. Software Engineer")
        assert skip is True
        assert "sr." in reason

    def test_sr_space_blocked(self) -> None:
        skip, reason = should_skip_title("Sr Software Engineer")
        assert skip is True
        assert "sr " in reason


class TestArchitectSpecialCase:
    """'architect' is blocked unless preceded by 'junior' or 'associate'."""

    def test_bare_architect_is_blocked(self) -> None:
        skip, reason = should_skip_title("Software Architect")
        assert skip is True
        assert "architect" in reason.lower()

    def test_junior_architect_passes(self) -> None:
        skip, _ = should_skip_title("Junior Architect")
        assert skip is False

    def test_associate_architect_passes(self) -> None:
        skip, _ = should_skip_title("Associate Architect")
        assert skip is False

    def test_solutions_architect_is_blocked(self) -> None:
        skip, _ = should_skip_title("Solutions Architect")
        assert skip is True

    def test_cloud_architect_is_blocked(self) -> None:
        skip, _ = should_skip_title("Cloud Architect")
        assert skip is True


class TestCleanTitlesPass:
    """Titles that should NOT be filtered out."""

    @pytest.mark.parametrize(
        "title",
        [
            "Junior Software Engineer",
            "ML Engineer Intern",
            "Data Engineer I",
            "Associate Developer",
            "Software Developer",
            "Entry Level Data Scientist",
            "Backend Engineer Intern",
            "Full Stack Developer",
            "Python Developer",
        ],
    )
    def test_clean_titles_not_filtered(self, title: str) -> None:
        skip, reason = should_skip_title(title)
        assert skip is False, f"'{title}' should pass but was blocked: {reason}"


# ============================================================================
# Description blacklist: experience year patterns
# ============================================================================


class TestDescriptionYearPatterns:
    """Descriptions with high experience requirements should be blocked."""

    @pytest.mark.parametrize(
        "text",
        [
            "Requires 5+ years of experience in Python",
            "5-7 years of professional experience",
            "7+ years of software development experience",
            "10+ years in distributed systems",
            "Must have 8 years of relevant experience",
            "Minimum 9 years in the field",
            "At least 10 years of engineering experience",
        ],
    )
    def test_high_experience_blocked(self, text: str) -> None:
        skip, reason = should_skip_description(text)
        assert skip is True, f"Expected description to be blocked: '{text}'"
        assert "years" in reason.lower()

    @pytest.mark.parametrize(
        "text",
        [
            "Requires 2+ years of experience",
            "1-2 years experience preferred",
            "3+ years of relevant experience",
            "4 years of software development",
            "No experience required",
            "Entry level position, 0-2 years",
            "Great opportunity for new grads",
        ],
    )
    def test_acceptable_experience_passes(self, text: str) -> None:
        skip, reason = should_skip_description(text)
        assert skip is False, f"Expected description to pass but was blocked: {reason}"

    def test_case_insensitivity_description(self) -> None:
        skip, _ = should_skip_description("5+ YEARS of experience")
        assert skip is True

    def test_empty_description_passes(self) -> None:
        skip, _ = should_skip_description("")
        assert skip is False
