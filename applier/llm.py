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

    # Sponsorship — never need it
    if any(p in q for p in (
        "require sponsorship", "visa sponsorship", "need sponsorship",
        "sponsorship", "require visa", "immigration sponsorship",
        "h-1b", "h1b", "h 1b",
    )):
        return _pick_option("No", options)

    # Background check / drug test / reference check — always willing
    if any(p in q for p in (
        "background check", "background investigation", "background screening",
        "criminal background", "drug test", "drug screen", "drug screening",
        "reference check", "consent to a background",
        "willing to undergo", "willing to submit",
    )):
        return _pick_option("Yes", options)

    # ── EEO / self-identification questions ──────────────────────────────
    # LinkedIn and company application portals commonly ask voluntary
    # self-identification questions. Answers below reflect the applicant's
    # actual self-identification.

    # Gender / sex
    if any(p in q for p in (
        "gender identity", "what is your gender", "your gender",
        "gender?", "sex?", "biological sex", "sex assigned at birth",
        "male or female", "identify as",
    )) and "transgender" not in q:
        return _pick_option("Male", options)

    # Transgender
    if "transgender" in q or "trans identity" in q:
        return _pick_option("No", options)

    # Sexual orientation
    if any(p in q for p in (
        "sexual orientation", "lgbt", "lgbtq", "lgbtqia",
        "gay", "lesbian", "bisexual", "queer",
    )):
        return _pick_option("Heterosexual", options)

    # Race / ethnicity. LinkedIn forms use varied wordings; look for the
    # common triggers and return a preferred option. _pick_option's
    # substring fallback will match "Asian" inside "Asian (not Hispanic or
    # Latino)" or "Asian / Pacific Islander".
    if any(p in q for p in (
        "race", "ethnicity", "ethnic", "racial", "hispanic or latino",
        "hispanic/latino",
    )):
        return _pick_option("Asian", options)

    # Veteran / military status
    if any(p in q for p in (
        "veteran", "military service", "armed forces", "protected veteran",
        "served in the military", "active duty",
    )):
        return _pick_option("No", options)

    # Disability status
    if any(p in q for p in (
        "disability", "disabled", "long-term condition",
        "chronic condition", "ada accommodation",
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

    # "Recruiter-friendly Yes" bucket — any question about willingness,
    # availability, or flexibility that a hiring manager would want to hear
    # "Yes" to. We default to Yes on all of these so the application keeps
    # moving. Ordered after relocation/sponsorship/auth so those more
    # specific rules still win.
    recruiter_yes_patterns = (
        # Work arrangement
        "work on-site", "work onsite", "work in office", "work in-office",
        "work in the office", "on-site work", "onsite work", "in-office work",
        "comfortable working on", "comfortable working in the office",
        "able to work on-site", "able to work onsite", "able to work in office",
        "willing to work on-site", "willing to work onsite",
        "willing to work in office", "willing to work in-office",
        "work hybrid", "hybrid schedule", "hybrid work", "willing to work hybrid",
        "work remote", "work remotely", "remote work", "willing to work remote",
        # Hours / schedule
        "willing to work overtime", "work overtime", "overtime if needed",
        "work weekends", "willing to work weekends",
        "work nights", "work night shift", "work evenings",
        "work holidays", "willing to work holidays",
        "shift work", "rotating shifts", "willing to work shifts",
        "flexible hours", "flexible schedule", "flexible with your schedule",
        "extended hours", "long hours",
        # Commute / travel
        "willing to commute", "able to commute", "reliable transportation",
        "own transportation", "own vehicle", "own a car",
        "willing to travel", "able to travel", "travel for work",
        "travel up to", "travel as needed",
        # Interview / onboarding
        "able to attend", "available for an interview", "come in for an interview",
        "in-person interview", "on-site interview",
        # General willingness / capability framing
        "are you able to", "are you willing to", "are you comfortable",
        "are you open to", "can you work", "can you perform",
        "physically able", "lift", "stand for",
    )
    if any(p in q for p in recruiter_yes_patterns):
        return _pick_option("Yes", options)

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

    # Yes/No answers must be matched by the option's first word, NOT by
    # substring. "no" is a substring of "now", "not", "none", etc., which
    # previously caused "No" preferences to match affirmative options like
    # "Yes, now" or "Yes, I do not need sponsorship".
    first_word = preferred_lower.split(",")[0].split("/")[0].split()[0] if preferred_lower else ""
    if first_word in ("yes", "no"):
        for opt in options:
            # Match on the option's first alphabetic word only.
            opt_first = opt.lower().strip().lstrip("-•* ").split(",")[0].split()[0] if opt.strip() else ""
            if opt_first == first_word:
                return opt
        # No match by first word — fall through to the last-resort fallback,
        # skipping substring matching entirely for yes/no answers.
        return options[0]

    # Substring / containment match — only for longer preferences where
    # accidental substring collisions are unlikely.
    if len(preferred_lower) >= 4:
        for opt in options:
            opt_lower = opt.lower().strip()
            if preferred_lower in opt_lower or opt_lower in preferred_lower:
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
        "- For work authorization: Yes. For sponsorship: No.\n\n"
        "APPLICANT SELF-IDENTIFICATION (use these for any EEO / demographic question):\n"
        "- Gender identity: Male\n"
        "- Sex: Male (assigned at birth)\n"
        "- Transgender: No\n"
        "- Sexual orientation: Heterosexual / Straight\n"
        "- Race / ethnicity: Asian (South Asian specifically; pick the closest option)\n"
        "- Hispanic / Latino: No\n"
        "- Protected veteran / military service: No\n"
        "- Disability: No\n"
        "- Work authorization in the US: Yes\n"
        "- Visa / sponsorship required: No\n\n"
        "THINK LIKE A DESPERATE APPLICANT WHO NEEDS THIS JOB:\n"
        "Before answering any yes/no question, ask yourself: 'What answer would the\n"
        "recruiter want to hear from an ideal candidate?' That is your answer.\n"
        "- Willing/able to work onsite, hybrid, remote, overtime, weekends, nights,\n"
        "  holidays, shifts, long hours, early mornings? → YES\n"
        "- Willing/able to commute, travel, relocate, drive, attend in-person? → YES\n"
        "- Comfortable with the pace, environment, team, tools, dress code? → YES\n"
        "- Have reliable transportation? → YES\n"
        "- Able to lift/stand/walk/physical requirement? → YES (unless resume explicitly says otherwise)\n"
        "- Willing to undergo background check, drug test, reference check? → YES\n"
        "- Can you start immediately? → YES\n"
        "- Only answer NO when saying Yes would be clearly dishonest (e.g. a\n"
        "  specific license/certification not on the resume, years of experience\n"
        "  with a tech not on the resume, work authorization you don't have).\n"
        "When genuinely in doubt, say Yes. A human reviewer will decide later.\n\n"
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
