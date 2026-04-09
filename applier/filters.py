"""Title and description blacklist filtering for job applications."""

import re


# Title blacklist: words/phrases that indicate a senior-level position
_TITLE_BLACKLIST: list[str] = [
    "senior",
    "sr.",
    "sr ",
    "staff",
    "lead",
    "leader",
    "principal",
    "manager",
    "management",
    "director",
    "head of",
    "vp",
    "vice president",
]

# Regex for experience requirements that exceed junior/entry level
_EXPERIENCE_PATTERN: re.Pattern[str] = re.compile(
    r"\b(?:"
    r"[5-9]\+?\s*(?:-\s*\d+\s*)?years"
    r"|10\+?\s*years"
    r")",
    re.IGNORECASE,
)


def should_skip_title(title: str) -> tuple[bool, str]:
    """Check whether a job title should be skipped based on the blacklist.

    Args:
        title: The job title to check.

    Returns:
        A tuple of (should_skip, reason). Returns (False, "") if the title
        passes all checks.
    """
    title_lower = title.lower()

    for term in _TITLE_BLACKLIST:
        if term in title_lower:
            return (True, f"title contains '{term}'")

    # Special case: "architect" is blocked unless preceded by "junior" or "associate"
    architect_pattern = re.compile(
        r"(?<!junior\s)(?<!associate\s)architect",
        re.IGNORECASE,
    )
    if architect_pattern.search(title):
        return (True, "title contains 'architect' without junior/associate prefix")

    return (False, "")


def should_skip_description(description: str) -> tuple[bool, str]:
    """Check whether a job description should be skipped based on experience requirements.

    Args:
        description: The job description text to check.

    Returns:
        A tuple of (should_skip, reason). Returns (False, "") if the description
        passes all checks.
    """
    match = _EXPERIENCE_PATTERN.search(description)
    if match:
        return (True, f"description requires '{match.group()}'")

    return (False, "")
