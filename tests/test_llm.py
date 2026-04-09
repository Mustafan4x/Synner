"""Tests for applier.llm — GPT-4o-mini integration and hardcoded Q&A."""

from unittest.mock import MagicMock, patch

import pytest

from applier import llm
from applier.llm import (
    _check_hardcoded,
    _pick_option,
    answer_question,
    create_client,
    generate_cover_letter,
    get_token_usage,
)


# ============================================================================
# Hardcoded Q&A pattern matching
# ============================================================================


class TestHardcodedAnswers:
    """Test that hardcoded patterns return the expected answers."""

    def test_authorized_to_work(self, sample_resume) -> None:
        answer = _check_hardcoded(
            "Are you authorized to work in the US?", None, sample_resume, "SWE"
        )
        assert answer == "Yes"

    def test_authorized_to_work_with_options(self, sample_resume) -> None:
        answer = _check_hardcoded(
            "Are you authorized to work in the US?",
            ["Yes", "No"],
            sample_resume,
            "SWE",
        )
        assert answer == "Yes"

    def test_visa_sponsorship(self, sample_resume) -> None:
        answer = _check_hardcoded(
            "Do you require visa sponsorship?", None, sample_resume, "SWE"
        )
        assert answer == "No"

    def test_require_sponsorship_variant(self, sample_resume) -> None:
        answer = _check_hardcoded(
            "Will you need sponsorship now or in the future?",
            None,
            sample_resume,
            "SWE",
        )
        # "need sponsorship" is in the pattern list
        assert answer == "No"

    def test_years_of_experience_python(self, sample_resume) -> None:
        answer = _check_hardcoded(
            "How many years of experience with Python?", None, sample_resume, "SWE"
        )
        assert answer == "2"

    def test_years_of_experience_unknown_tech(self, sample_resume) -> None:
        answer = _check_hardcoded(
            "How many years of experience with Rust?", None, sample_resume, "SWE"
        )
        assert answer == "0"

    def test_willing_to_relocate(self, sample_resume) -> None:
        answer = _check_hardcoded(
            "Are you willing to relocate?", None, sample_resume, "SWE"
        )
        assert answer == "Yes, within DFW"

    def test_desired_salary(self, sample_resume) -> None:
        answer = _check_hardcoded(
            "What is your desired salary?", None, sample_resume, "SWE"
        )
        assert answer is not None
        lower = answer.lower()
        assert "open" in lower or "competitive" in lower

    def test_how_did_you_hear(self, sample_resume) -> None:
        answer = _check_hardcoded(
            "How did you hear about this position?", None, sample_resume, "SWE"
        )
        assert answer == "LinkedIn"

    def test_education_level(self, sample_resume) -> None:
        answer = _check_hardcoded(
            "What is your education level?", None, sample_resume, "SWE"
        )
        assert answer == "Bachelor's (in progress)"

    def test_gpa(self, sample_resume) -> None:
        answer = _check_hardcoded(
            "What is your GPA?", None, sample_resume, "SWE"
        )
        assert answer == "3.7"

    def test_start_date(self, sample_resume) -> None:
        answer = _check_hardcoded(
            "What is your available start date?", None, sample_resume, "SWE"
        )
        assert answer is not None
        assert "flexible" in answer.lower() or "immediately" in answer.lower()


# ============================================================================
# Project question: category-dependent project selection
# ============================================================================


class TestProjectQuestion:
    """Test that the right project is returned based on category."""

    def test_mlai_category_returns_adrenalineai(self, sample_resume) -> None:
        answer = _check_hardcoded(
            "Describe a relevant project", None, sample_resume, "MLAI"
        )
        assert answer is not None
        assert "AdrenalineAI" in answer

    def test_de_category_returns_adrenalineai(self, sample_resume) -> None:
        answer = _check_hardcoded(
            "Describe a relevant project", None, sample_resume, "DE"
        )
        assert answer is not None
        assert "AdrenalineAI" in answer

    def test_swe_category_returns_spotme(self, sample_resume) -> None:
        answer = _check_hardcoded(
            "Describe a relevant project", None, sample_resume, "SWE"
        )
        assert answer is not None
        assert "SpotMe" in answer

    def test_fs_category_returns_spotme(self, sample_resume) -> None:
        answer = _check_hardcoded(
            "Tell us about a project you've worked on", None, sample_resume, "FS"
        )
        assert answer is not None
        assert "SpotMe" in answer


# ============================================================================
# _pick_option helper
# ============================================================================


class TestPickOption:
    """Test the option matching helper."""

    def test_no_options_returns_preferred(self) -> None:
        assert _pick_option("Yes", None) == "Yes"

    def test_exact_match(self) -> None:
        assert _pick_option("Yes", ["Yes", "No"]) == "Yes"

    def test_case_insensitive_match(self) -> None:
        assert _pick_option("yes", ["Yes", "No"]) == "Yes"

    def test_substring_match(self) -> None:
        result = _pick_option("Yes", ["Yes, I am authorized", "No"])
        assert result == "Yes, I am authorized"

    def test_fallback_to_first_option(self) -> None:
        result = _pick_option("Something else", ["Option A", "Option B"])
        assert result == "Option A"


# ============================================================================
# Mocked OpenAI API calls
# ============================================================================


class TestAnswerQuestionWithLLM:
    """Test answer_question when it falls through to LLM."""

    def test_answer_question_hardcoded_does_not_call_llm(self, sample_resume) -> None:
        with patch.object(llm, "_call_llm") as mock_llm:
            answer = answer_question(
                "Are you authorized to work in the US?",
                None,
                sample_resume,
                "SWE",
            )
            mock_llm.assert_not_called()
            assert answer == "Yes"

    def test_answer_question_falls_through_to_llm(self, sample_resume) -> None:
        with patch.object(llm, "_call_llm", return_value="I am very interested in this role.") as mock_llm:
            answer = answer_question(
                "Why are you interested in this role?",
                None,
                sample_resume,
                "SWE",
            )
            mock_llm.assert_called_once()
            assert "interested" in answer.lower()


class TestGenerateCoverLetter:
    """Test cover letter generation with mocked API."""

    def test_generate_cover_letter_calls_llm(self, sample_resume) -> None:
        with patch.object(
            llm,
            "_call_llm",
            return_value="I am excited to apply for this position.",
        ) as mock_llm:
            result = generate_cover_letter(sample_resume, "Software Engineer", "Google")
            mock_llm.assert_called_once()
            assert "excited" in result.lower()

    def test_generate_cover_letter_includes_job_info_in_prompt(self, sample_resume) -> None:
        with patch.object(llm, "_call_llm", return_value="Cover letter text.") as mock_llm:
            generate_cover_letter(sample_resume, "ML Engineer", "OpenAI")
            call_args = mock_llm.call_args
            user_prompt = call_args[0][1]  # second positional arg
            assert "ML Engineer" in user_prompt
            assert "OpenAI" in user_prompt


# ============================================================================
# Token usage
# ============================================================================


class TestTokenUsage:
    """Test get_token_usage returns the expected structure."""

    def test_token_usage_structure(self) -> None:
        usage = get_token_usage()
        assert "prompt_tokens" in usage
        assert "completion_tokens" in usage
        assert "estimated_cost" in usage
        assert isinstance(usage["prompt_tokens"], int)
        assert isinstance(usage["completion_tokens"], int)
        assert isinstance(usage["estimated_cost"], float)

    def test_token_usage_cost_is_non_negative(self) -> None:
        usage = get_token_usage()
        assert usage["estimated_cost"] >= 0


# ============================================================================
# create_client
# ============================================================================


class TestCreateClient:
    """Test client creation."""

    def test_create_client_returns_client(self) -> None:
        with patch("applier.llm.openai.OpenAI") as mock_openai:
            mock_client = MagicMock()
            mock_openai.return_value = mock_client
            client = create_client("sk-test-key")
            mock_openai.assert_called_once_with(api_key="sk-test-key")
            assert client is mock_client
