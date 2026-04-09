"""GPT-4o-mini integration for screening question answers and cover letters."""

import logging
import re

import openai

logger = logging.getLogger(__name__)

MODEL = "gpt-4o-mini"

# Module-level token usage counters
_prompt_tokens: int = 0
_completion_tokens: int = 0

# Cost per token for gpt-4o-mini (as of 2024)
_PROMPT_COST_PER_TOKEN = 0.15 / 1_000_000      # $0.15 per 1M input tokens
_COMPLETION_COST_PER_TOKEN = 0.60 / 1_000_000   # $0.60 per 1M output tokens

# Module-level client reference
_client: openai.OpenAI | None = None


def create_client(api_key: str) -> openai.OpenAI:
    """Initialize and return an OpenAI client.

    Args:
        api_key: The OpenAI API key.

    Returns:
        A configured OpenAI client instance.
    """
    global _client
    _client = openai.OpenAI(api_key=api_key)
    return _client


def get_token_usage() -> dict[str, int | float]:
    """Return cumulative token usage and estimated cost.

    Returns:
        Dictionary with prompt_tokens, completion_tokens, and estimated_cost.
    """
    cost = (
        _prompt_tokens * _PROMPT_COST_PER_TOKEN
        + _completion_tokens * _COMPLETION_COST_PER_TOKEN
    )
    return {
        "prompt_tokens": _prompt_tokens,
        "completion_tokens": _completion_tokens,
        "estimated_cost": round(cost, 4),
    }


def _format_resume(resume: dict) -> str:
    """Format resume data into a readable string for LLM context.

    Args:
        resume: Parsed resume dictionary from plain_text_resume.yaml.

    Returns:
        Formatted string representation of the resume.
    """
    lines: list[str] = []

    personal = resume.get("personal", {})
    lines.append("=== PERSONAL INFO ===")
    for key, value in personal.items():
        lines.append(f"{key}: {value}")

    education = resume.get("education", {})
    lines.append("\n=== EDUCATION ===")
    lines.append(f"{education.get('degree', '')} — {education.get('school', '')}")
    lines.append(f"Expected graduation: {education.get('graduation', '')}")
    coursework = education.get("coursework", [])
    if coursework:
        lines.append(f"Coursework: {', '.join(coursework)}")

    lines.append("\n=== EXPERIENCE ===")
    for job in resume.get("experience", []):
        lines.append(f"{job.get('title', '')} at {job.get('company', '')} ({job.get('dates', '')})")
        for bullet in job.get("bullets", []):
            lines.append(f"  - {bullet}")

    lines.append("\n=== PROJECTS ===")
    for project in resume.get("projects", []):
        lines.append(f"{project.get('name', '')} [{project.get('tech', '')}]")
        for bullet in project.get("bullets", []):
            lines.append(f"  - {bullet}")

    skills = resume.get("skills", {})
    lines.append("\n=== SKILLS ===")
    for category, items in skills.items():
        if isinstance(items, list):
            lines.append(f"{category}: {', '.join(items)}")

    yoe = resume.get("years_of_experience", {})
    if yoe:
        lines.append("\n=== YEARS OF EXPERIENCE ===")
        for tech, years in yoe.items():
            lines.append(f"{tech}: {years} years")

    return "\n".join(lines)


def _call_llm(system_prompt: str, user_prompt: str) -> str:
    """Make a chat completion call to GPT-4o-mini.

    Args:
        system_prompt: The system message with context.
        user_prompt: The user message / question.

    Returns:
        The assistant's response text.

    Raises:
        openai.APIError: On non-recoverable API errors.
    """
    global _prompt_tokens, _completion_tokens

    if _client is None:
        raise RuntimeError("OpenAI client not initialized. Call create_client() first.")

    try:
        response = _client.chat.completions.create(
            model=MODEL,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.4,
            max_tokens=300,
        )
    except openai.RateLimitError as exc:
        logger.warning("Rate limited by OpenAI API: %s", exc)
        raise
    except openai.APITimeoutError as exc:
        logger.warning("OpenAI API request timed out: %s", exc)
        raise
    except openai.APIError as exc:
        logger.error("OpenAI API error: %s", exc)
        raise

    usage = response.usage
    if usage:
        _prompt_tokens += usage.prompt_tokens
        _completion_tokens += usage.completion_tokens

    return response.choices[0].message.content or ""


def _check_hardcoded(question: str, options: list[str] | None, resume: dict, category: str) -> str | None:
    """Check if the question matches a hardcoded Q&A pattern.

    Args:
        question: The screening question text.
        options: Multiple-choice options, if any.
        resume: Parsed resume dictionary.
        category: Job category (SWE, FS, MLAI, DE).

    Returns:
        The hardcoded answer string, or None if no match.
    """
    q = question.lower().strip()

    # Authorized to work — many phrasings
    if any(p in q for p in (
        "authorized to work", "authorised to work",
        "legally authorized", "legally authorised",
        "work authorization", "work authorisation",
        "eligible to work", "right to work",
        "legally eligible", "permitted to work",
    )):
        return _pick_option("Yes", options)

    # Sponsorship
    if any(p in q for p in (
        "require sponsorship", "visa sponsorship", "need sponsorship",
        "sponsorship", "require visa", "immigration sponsorship",
    )):
        return _pick_option("No", options)

    # Certifications / licenses — if asked "do you have" a specific cert,
    # answer No unless it's something on the resume
    if any(p in q for p in ("license or certification", "certification", "certified")):
        # Check if any resume skill matches
        all_skills = []
        for skill_list in resume.get("skills", {}).values():
            if isinstance(skill_list, list):
                all_skills.extend(s.lower() for s in skill_list)
        # If the cert is mentioned in skills, say Yes
        for skill in all_skills:
            if skill in q:
                return _pick_option("Yes", options)
        return _pick_option("No", options)

    # Years of experience — multiple phrasings:
    # "years of experience with Python", "years of analyst experience",
    # "how many years of data engineering experience", etc.
    yoe_patterns = [
        r"(?:how many\s+)?years?\s+of\s+(?:professional\s+|work\s+)?experience\s+(?:with|in|using)\s+(.+?)[\?\.]?\s*$",
        r"(?:how many\s+)?years?\s+of\s+(.+?)\s+experience[\?\.]?\s*$",
        r"experience\s+(?:with|in|using)\s+(.+?)[\?\.\,]",
    ]
    for pattern in yoe_patterns:
        yoe_match = re.search(pattern, q)
        if yoe_match:
            tech_name = yoe_match.group(1).strip().rstrip("?.,:;")
            yoe = resume.get("years_of_experience", {})
            # Try exact match first, then case-insensitive, then substring
            years = yoe.get(tech_name)
            if years is None:
                for key, val in yoe.items():
                    if key.lower() == tech_name.lower():
                        years = val
                        break
            if years is None:
                for key, val in yoe.items():
                    if key.lower() in tech_name.lower() or tech_name.lower() in key.lower():
                        years = val
                        break
            if years is None:
                years = 0
            return _pick_option(str(years), options)

    # Willing to relocate
    if "willing to relocate" in q or "open to relocation" in q:
        return _pick_option("Yes, within DFW", options)

    # Available start date
    if "start date" in q or "available to start" in q or "earliest start" in q:
        return _pick_option("Flexible / Immediately", options)

    # Salary
    if "salary" in q or "compensation" in q or "desired pay" in q:
        return _pick_option("Open to discussion / competitive", options)

    # How did you hear
    if "how did you hear" in q or "where did you hear" in q or "how did you find" in q:
        return _pick_option("LinkedIn", options)

    # Education level
    if "education level" in q or "highest degree" in q or "highest level of education" in q:
        return _pick_option("Bachelor's (in progress)", options)

    # Specific degree questions — "do you have a master's", "do you have a PhD", etc.
    if any(p in q for p in ("master's", "masters", "master degree", "mba")):
        if "do you have" in q or "have you" in q or "completed" in q:
            return _pick_option("No", options)
    if any(p in q for p in ("phd", "ph.d", "doctorate", "doctoral")):
        if "do you have" in q or "have you" in q or "completed" in q:
            return _pick_option("No", options)
    if any(p in q for p in ("bachelor", "bachelor's", "bachelors", "bs ", "b.s.")):
        if "do you have" in q or "have you" in q or "completed" in q:
            # In progress, not completed
            return _pick_option("Yes", options)

    # GPA
    if "gpa" in q:
        return _pick_option("3.7", options)

    # "Why are you interested" — requires LLM call, return None to fall through
    if "why are you interested" in q or "why do you want" in q:
        return None

    # Describe a relevant project
    if "describe a relevant project" in q or "tell us about a project" in q or "relevant project" in q:
        projects = resume.get("projects", [])
        if category in ("MLAI", "DE"):
            target = "AdrenalineAI"
        else:
            target = "SpotMe"
        for project in projects:
            if project.get("name") == target:
                bullets = project.get("bullets", [])
                tech = project.get("tech", "")
                description = f"{target} ({tech}): " + " ".join(bullets)
                return description
        # Fallback: return first project
        if projects:
            p = projects[0]
            return f"{p.get('name', '')} ({p.get('tech', '')}): " + " ".join(p.get("bullets", []))
        return None

    return None


def _pick_option(preferred: str, options: list[str] | None) -> str:
    """Select the best matching option from a list, or return preferred value for free-text.

    Args:
        preferred: The preferred/ideal answer.
        options: Available multiple-choice options, or None for free-text.

    Returns:
        The best matching option string, or preferred if no options.
    """
    if not options:
        return preferred

    preferred_lower = preferred.lower().strip()

    # Exact match
    for opt in options:
        if opt.lower().strip() == preferred_lower:
            return opt

    # Substring / containment match
    for opt in options:
        opt_lower = opt.lower().strip()
        if preferred_lower in opt_lower or opt_lower in preferred_lower:
            return opt

    # For yes/no answers, match on the first word
    first_word = preferred_lower.split(",")[0].split("/")[0].split()[0] if preferred_lower else ""
    if first_word in ("yes", "no"):
        for opt in options:
            if opt.lower().strip().startswith(first_word):
                return opt

    # Fallback: return the first option
    return options[0]


def answer_question(
    question: str,
    options: list[str] | None,
    resume: dict,
    category: str,
) -> str:
    """Answer a screening question using hardcoded defaults or GPT-4o-mini.

    Args:
        question: The screening question text.
        options: Multiple-choice options (None for free-text).
        resume: Parsed resume dictionary from plain_text_resume.yaml.
        category: Job category — one of SWE, FS, MLAI, DE.

    Returns:
        The answer string (option text for MC, free-text otherwise).
    """
    # Try hardcoded answers first
    hardcoded = _check_hardcoded(question, options, resume, category)
    if hardcoded is not None:
        logger.debug("Hardcoded answer for '%s': %s", question[:60], hardcoded)
        return hardcoded

    # Build system prompt with resume context
    resume_text = _format_resume(resume)
    system_prompt = (
        "You are an AI assistant filling out a job application form on behalf of an applicant.\n"
        "You MUST answer every question from the applicant's perspective as if you ARE the applicant.\n"
        "Never say 'I don't have experience' or 'I cannot answer'. Always provide a concrete answer.\n\n"
        "CRITICAL RULES:\n"
        "- If asked 'how many years of experience' with something not on the resume, answer '0'\n"
        "- If a field expects a NUMBER, respond with ONLY a number (e.g., '0', '2', '5'). No words.\n"
        "- If yes/no, answer with just 'Yes' or 'No'\n"
        "- If asked for a city or location, answer 'Arlington, TX'\n"
        "- Keep free-text answers to 1-2 sentences, professional and confident\n"
        "- Always be positive about the applicant's qualifications\n"
        "- For work authorization: Yes. For sponsorship: No.\n"
        "- When in doubt, give the answer most likely to get the applicant hired\n\n"
        f"APPLICANT RESUME:\n{resume_text}"
    )

    user_prompt = f"Screening question: {question}"
    if options:
        options_text = "\n".join(f"  - {opt}" for opt in options)
        user_prompt += (
            f"\n\nThis is a multiple-choice question. Choose the BEST option from:\n{options_text}\n"
            "Respond with the exact text of the chosen option, nothing else."
        )
    else:
        user_prompt += (
            "\n\nRespond with ONLY the answer value. No explanation, no extra words. "
            "If the field expects a number, respond with just the number."
        )

    answer = _call_llm(system_prompt, user_prompt).strip()

    # For multiple-choice, ensure we return a valid option
    if options:
        answer_lower = answer.lower().strip()
        for opt in options:
            if opt.lower().strip() == answer_lower:
                return opt
        # Containment fallback
        for opt in options:
            if opt.lower().strip() in answer_lower or answer_lower in opt.lower().strip():
                return opt
        # Last resort: return the raw answer (best effort)
        logger.warning(
            "LLM answer '%s' didn't match any option for question '%s'",
            answer,
            question[:60],
        )

    return answer


def generate_cover_letter(resume: dict, job_title: str, company: str) -> str:
    """Generate a 3-4 sentence cover letter using GPT-4o-mini.

    Args:
        resume: Parsed resume dictionary from plain_text_resume.yaml.
        job_title: The title of the job being applied to.
        company: The company name.

    Returns:
        A short cover letter string.
    """
    resume_text = _format_resume(resume)
    system_prompt = (
        "You are an AI assistant writing a brief cover letter for a job applicant.\n"
        "Write exactly 3-4 sentences. Be professional, concise, and enthusiastic.\n"
        "Mention the applicant's relevant skills and experience.\n"
        "Do NOT include a greeting or sign-off — just the body paragraph.\n\n"
        f"APPLICANT RESUME:\n{resume_text}"
    )

    user_prompt = f"Write a 3-4 sentence cover letter body for the position of {job_title} at {company}."

    return _call_llm(system_prompt, user_prompt).strip()
