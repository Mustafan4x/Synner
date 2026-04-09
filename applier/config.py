"""Configuration and resume loading for Synner."""

from __future__ import annotations

import logging
import warnings
from pathlib import Path

import yaml

logger = logging.getLogger(__name__)


class ConfigError(Exception):
    """Raised when configuration is missing or invalid."""


# ---------------------------------------------------------------------------
# Resume mapping: category -> PDF filename
# ---------------------------------------------------------------------------

RESUME_MAP: dict[str, str] = {
    "SWE": "Resume_SWE.pdf",
    "FS": "Resume_FS.pdf",
    "MLAI": "Resume_MLAI.pdf",
    "DE": "Resume_DE.pdf",
}

# ---------------------------------------------------------------------------
# Search keywords per category
# ---------------------------------------------------------------------------

SEARCH_KEYWORDS: dict[str, list[str]] = {
    "SWE": [
        "software engineer intern",
        "junior software engineer",
        "software developer entry level",
        "associate software engineer",
        "software engineer I",
        "software engineer new grad",
    ],
    "FS": [
        "fullstack developer",
        "full stack engineer",
        "junior web developer",
        "fullstack engineer entry level",
        "full stack developer intern",
    ],
    "MLAI": [
        "machine learning intern",
        "AI engineer entry level",
        "data scientist junior",
        "ML engineer intern",
        "machine learning engineer new grad",
        "data science intern",
    ],
    "DE": [
        "data engineer entry level",
        "junior data engineer",
        "ETL developer",
        "data engineer intern",
        "data pipeline engineer",
        "data engineer I",
    ],
}

# ---------------------------------------------------------------------------
# Search locations (15 DFW-area cities + Remote)
# ---------------------------------------------------------------------------

SEARCH_LOCATIONS: list[str] = [
    "Dallas, TX",
    "Fort Worth, TX",
    "Arlington, TX",
    "Corsicana, TX",
    "Plano, TX",
    "Frisco, TX",
    "Irving, TX",
    "Richardson, TX",
    "Euless, TX",
    "Carrollton, TX",
    "McKinney, TX",
    "Denton, TX",
    "Garland, TX",
    "Grand Prairie, TX",
    "Allen, TX",
    "Addison, TX",
    "Remote",
]

# ---------------------------------------------------------------------------
# Required keys in config.yaml
# ---------------------------------------------------------------------------

_REQUIRED_CONFIG_KEYS: set[str] = {
    "openai_api_key",
    "linkedin_profile_dir",
    "resume_dir",
    "max_applications_per_session",
    "max_per_category",
    "delay_min_seconds",
    "delay_max_seconds",
    "search_delay_min_seconds",
    "search_delay_max_seconds",
    "headless",
}

# ---------------------------------------------------------------------------
# Required top-level keys in plain_text_resume.yaml
# ---------------------------------------------------------------------------

_REQUIRED_RESUME_KEYS: set[str] = {
    "personal",
    "education",
    "experience",
    "projects",
    "skills",
    "years_of_experience",
}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def load_config(path: str = "config.yaml") -> dict:
    """Load and validate *config.yaml*.

    Parameters
    ----------
    path:
        File-system path to the YAML configuration file.

    Returns
    -------
    dict
        Parsed configuration dictionary.

    Raises
    ------
    ConfigError
        If the file is missing, unreadable, or lacks required keys.
    """
    config_path = Path(path)
    if not config_path.exists():
        raise ConfigError(f"Configuration file not found: {config_path}")

    try:
        with config_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Failed to parse {config_path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError(f"Expected a YAML mapping in {config_path}, got {type(data).__name__}")

    missing = _REQUIRED_CONFIG_KEYS - data.keys()
    if missing:
        raise ConfigError(f"Missing required config keys: {', '.join(sorted(missing))}")

    return data


def load_resume(path: str = "plain_text_resume.yaml") -> dict:
    """Load and validate *plain_text_resume.yaml*.

    Parameters
    ----------
    path:
        File-system path to the resume YAML file.

    Returns
    -------
    dict
        Parsed resume dictionary.

    Raises
    ------
    ConfigError
        If the file is missing, unreadable, or lacks required sections.
    """
    resume_path = Path(path)
    if not resume_path.exists():
        raise ConfigError(f"Resume file not found: {resume_path}")

    try:
        with resume_path.open("r", encoding="utf-8") as fh:
            data = yaml.safe_load(fh)
    except yaml.YAMLError as exc:
        raise ConfigError(f"Failed to parse {resume_path}: {exc}") from exc

    if not isinstance(data, dict):
        raise ConfigError(f"Expected a YAML mapping in {resume_path}, got {type(data).__name__}")

    missing = _REQUIRED_RESUME_KEYS - data.keys()
    if missing:
        raise ConfigError(f"Missing required resume sections: {', '.join(sorted(missing))}")

    return data


def get_resume_path(category: str) -> Path:
    """Return the PDF path for a role *category*.

    The base directory is ``~/Documents/resumes/pdfs`` (expanded).

    Parameters
    ----------
    category:
        One of ``SWE``, ``FS``, ``MLAI``, or ``DE``.

    Returns
    -------
    Path
        Absolute path to the resume PDF.

    Raises
    ------
    ConfigError
        If *category* is not recognised.
    """
    filename = RESUME_MAP.get(category)
    if filename is None:
        raise ConfigError(
            f"Unknown resume category '{category}'. "
            f"Valid categories: {', '.join(sorted(RESUME_MAP))}"
        )

    pdf_path = Path("~/Documents/resumes/pdfs").expanduser() / filename

    if not pdf_path.exists():
        warnings.warn(
            f"Resume PDF not found on disk: {pdf_path}",
            stacklevel=2,
        )

    return pdf_path


def get_search_keywords(category: str) -> list[str]:
    """Return the LinkedIn search terms for a role *category*.

    Parameters
    ----------
    category:
        One of ``SWE``, ``FS``, ``MLAI``, or ``DE``.

    Returns
    -------
    list[str]
        Search keyword strings.

    Raises
    ------
    ConfigError
        If *category* is not recognised.
    """
    keywords = SEARCH_KEYWORDS.get(category)
    if keywords is None:
        raise ConfigError(
            f"Unknown search category '{category}'. "
            f"Valid categories: {', '.join(sorted(SEARCH_KEYWORDS))}"
        )
    return list(keywords)


def get_locations() -> list[str]:
    """Return all search locations (15 DFW-area cities + Remote).

    Returns
    -------
    list[str]
        Location strings, 17 entries total.
    """
    return list(SEARCH_LOCATIONS)
