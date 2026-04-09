"""Synner - Automated LinkedIn Job Application Bot."""

__all__ = [
    "load_config",
    "load_resume",
    "run_category",
    "print_summary",
    "should_skip_title",
    "should_skip_description",
    "answer_question",
    "FormFiller",
]


def __getattr__(name: str):
    """Lazy imports to avoid loading heavy dependencies on package import."""
    if name in ("load_config", "load_resume"):
        from applier.config import load_config, load_resume
        return load_config if name == "load_config" else load_resume
    if name == "run_category":
        from applier.linkedin import run_category
        return run_category
    if name == "print_summary":
        from applier.logger import print_summary
        return print_summary
    if name in ("should_skip_title", "should_skip_description"):
        from applier.filters import should_skip_title, should_skip_description
        return should_skip_title if name == "should_skip_title" else should_skip_description
    if name == "answer_question":
        from applier.llm import answer_question
        return answer_question
    if name == "FormFiller":
        from applier.form_filler import FormFiller
        return FormFiller
    raise AttributeError(f"module 'applier' has no attribute {name!r}")
