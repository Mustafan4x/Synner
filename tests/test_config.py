"""Tests for applier.config — configuration and resume loading."""

import pytest
import yaml

from applier.config import (
    ConfigError,
    RESUME_MAP,
    SEARCH_KEYWORDS,
    SEARCH_LOCATIONS,
    load_config,
    load_resume,
    get_resume_path,
    get_search_keywords,
    get_locations,
)


# ============================================================================
# load_config
# ============================================================================


class TestLoadConfig:
    """Tests for loading and validating config.yaml."""

    def test_load_valid_config(self, tmp_path, sample_config) -> None:
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump(sample_config))

        result = load_config(str(config_file))
        assert result["openai_api_key"] == "sk-test-key-1234567890"
        assert result["max_applications_per_session"] == 100
        assert result["headless"] is False

    def test_missing_config_file_raises(self, tmp_path) -> None:
        with pytest.raises(ConfigError, match="not found"):
            load_config(str(tmp_path / "nonexistent.yaml"))

    def test_missing_required_keys_raises(self, tmp_path) -> None:
        config_file = tmp_path / "config.yaml"
        config_file.write_text(yaml.dump({"openai_api_key": "sk-test"}))

        with pytest.raises(ConfigError, match="Missing required config keys"):
            load_config(str(config_file))

    def test_invalid_yaml_raises(self, tmp_path) -> None:
        config_file = tmp_path / "config.yaml"
        config_file.write_text("{{invalid yaml content:::")

        with pytest.raises(ConfigError):
            load_config(str(config_file))

    def test_non_dict_yaml_raises(self, tmp_path) -> None:
        config_file = tmp_path / "config.yaml"
        config_file.write_text("- just\n- a\n- list\n")

        with pytest.raises(ConfigError, match="Expected a YAML mapping"):
            load_config(str(config_file))


# ============================================================================
# load_resume
# ============================================================================


class TestLoadResume:
    """Tests for loading and validating plain_text_resume.yaml."""

    def test_load_valid_resume(self, tmp_path, sample_resume) -> None:
        resume_file = tmp_path / "resume.yaml"
        resume_file.write_text(yaml.dump(sample_resume))

        result = load_resume(str(resume_file))
        assert result["personal"]["name"] == "Test User"
        assert len(result["projects"]) == 2

    def test_missing_resume_file_raises(self, tmp_path) -> None:
        with pytest.raises(ConfigError, match="not found"):
            load_resume(str(tmp_path / "missing.yaml"))

    def test_missing_resume_sections_raises(self, tmp_path) -> None:
        resume_file = tmp_path / "resume.yaml"
        resume_file.write_text(yaml.dump({"personal": {"name": "Test"}}))

        with pytest.raises(ConfigError, match="Missing required resume sections"):
            load_resume(str(resume_file))


# ============================================================================
# get_resume_path
# ============================================================================


class TestGetResumePath:
    """Tests for resume path resolution per category."""

    @pytest.mark.parametrize(
        "category, expected_filename",
        [
            ("SWE", "Resume_SWE.pdf"),
            ("FS", "Resume_FS.pdf"),
            ("MLAI", "Resume_MLAI.pdf"),
            ("DE", "Resume_DE.pdf"),
        ],
    )
    def test_valid_category_returns_correct_path(self, category, expected_filename) -> None:
        path = get_resume_path(category)
        assert path.name == expected_filename
        assert "Documents/resumes/pdfs" in str(path)

    def test_invalid_category_raises(self) -> None:
        with pytest.raises(ConfigError, match="Unknown resume category"):
            get_resume_path("INVALID")


# ============================================================================
# get_search_keywords
# ============================================================================


class TestGetSearchKeywords:
    """Tests for keyword lists per category."""

    @pytest.mark.parametrize("category", ["SWE", "FS", "MLAI", "DE"])
    def test_valid_category_returns_list(self, category) -> None:
        keywords = get_search_keywords(category)
        assert isinstance(keywords, list)
        assert len(keywords) > 0
        assert all(isinstance(k, str) for k in keywords)

    def test_swe_keywords_content(self) -> None:
        keywords = get_search_keywords("SWE")
        assert "software engineer intern" in keywords
        assert "junior software engineer" in keywords
        assert len(keywords) == 6

    def test_mlai_keywords_content(self) -> None:
        keywords = get_search_keywords("MLAI")
        assert "machine learning intern" in keywords
        assert len(keywords) == 6

    def test_invalid_category_raises(self) -> None:
        with pytest.raises(ConfigError, match="Unknown search category"):
            get_search_keywords("INVALID")

    def test_returns_copy_not_original(self) -> None:
        keywords1 = get_search_keywords("SWE")
        keywords2 = get_search_keywords("SWE")
        assert keywords1 == keywords2
        assert keywords1 is not keywords2


# ============================================================================
# get_locations
# ============================================================================


class TestGetLocations:
    """Tests for the search locations list."""

    def test_returns_17_locations(self) -> None:
        locations = get_locations()
        assert len(locations) == 17

    def test_includes_key_cities(self) -> None:
        locations = get_locations()
        assert "Dallas, TX" in locations
        assert "Fort Worth, TX" in locations
        assert "Arlington, TX" in locations
        assert "Plano, TX" in locations

    def test_includes_addison(self) -> None:
        locations = get_locations()
        assert "Addison, TX" in locations

    def test_includes_remote(self) -> None:
        locations = get_locations()
        assert "Remote" in locations

    def test_returns_copy_not_original(self) -> None:
        loc1 = get_locations()
        loc2 = get_locations()
        assert loc1 == loc2
        assert loc1 is not loc2
