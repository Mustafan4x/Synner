"""LinkedIn search and Easy Apply automation for Synner."""

from __future__ import annotations

import logging
import random
import time
from urllib.parse import quote_plus

import undetected_chromedriver as uc
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
)
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from applier import config, filters, logger as app_logger
from applier.form_filler import FormFiller

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_LINKEDIN_JOBS_URL = "https://www.linkedin.com/jobs/search/"

# LinkedIn filter values for the search URL
_FILTER_EASY_APPLY = "f_AL=true"
_FILTER_PAST_WEEK = "f_TPR=r604800"
# Experience: 1=Internship, 2=Entry level, 3=Associate
_FILTER_EXPERIENCE = "f_E=1%2C2%2C3"
# Job type: F=Full-time
_FILTER_JOB_TYPE = "f_JT=F"

_RESULTS_PER_PAGE = 25

# Selectors — multiple fallbacks to handle LinkedIn DOM changes
_JOB_CARD_SELECTORS = [
    "div.job-card-container",
    "li.jobs-search-results__list-item",
    "div.jobs-search-results__list-item",
    "div[data-job-id]",
]

_JOB_TITLE_SELECTORS = [
    "a.job-card-list__title",
    "a.job-card-container__link",
    "a.job-card-list__title--link",
    "a[class*='job-card'] span",
    ".job-card-list__title",
]

_JOB_COMPANY_SELECTORS = [
    "span.job-card-container__primary-description",
    "a.job-card-container__company-name",
    ".job-card-container__company-name",
    "span.artdeco-entity-lockup__subtitle",
]

_JOB_LOCATION_SELECTORS = [
    "li.job-card-container__metadata-item",
    "span.job-card-container__metadata-item",
    ".artdeco-entity-lockup__caption",
]

_EASY_APPLY_BUTTON_SELECTORS = [
    "button.jobs-apply-button",
    "button[aria-label*='Easy Apply']",
    "button.jobs-apply-button--top-card",
    "div.jobs-apply-button--top-card button",
    "button[class*='jobs-apply-button']",
]

_NEXT_BUTTON_SELECTORS = [
    "button[aria-label='Continue to next step']",
    "button[aria-label='Next']",
    "button span:not([class])",  # fallback — text matching done in code
]

_REVIEW_BUTTON_SELECTORS = [
    "button[aria-label='Review your application']",
    "button[aria-label='Review']",
]

_SUBMIT_BUTTON_SELECTORS = [
    "button[aria-label='Submit application']",
    "button[aria-label='Submit']",
]

_DISMISS_BUTTON_SELECTORS = [
    "button[aria-label='Dismiss']",
    "button[aria-label='Done, application sent.']",
    "button.artdeco-modal__dismiss",
    "button[aria-label='Done']",
]

_MODAL_SELECTORS = [
    "div.jobs-easy-apply-modal",
    "div.jobs-easy-apply-content",
    "div[class*='jobs-easy-apply']",
]

_DESCRIPTION_SELECTORS = [
    "div.jobs-description-content__text",
    "div.jobs-description__content",
    "div#job-details",
    "article.jobs-description",
    "div[class*='jobs-description']",
]


# ---------------------------------------------------------------------------
# WEB-1: Browser setup
# ---------------------------------------------------------------------------


def create_driver(cfg: dict) -> uc.Chrome:
    """Launch undetected-chromedriver with a persistent Chrome profile.

    Args:
        cfg: Application configuration dictionary.  Expects keys
            ``linkedin_profile_dir`` and ``headless``.

    Returns:
        A configured ``uc.Chrome`` instance.
    """
    options = uc.ChromeOptions()

    profile_dir = cfg.get("linkedin_profile_dir", "./chrome_profile")
    options.add_argument(f"--user-data-dir={profile_dir}")

    if cfg.get("headless", False):
        options.add_argument("--headless=new")

    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    driver = uc.Chrome(options=options)
    driver.set_window_size(1920, 1080)
    driver.implicitly_wait(10)

    log.info("Browser started with profile: %s", profile_dir)
    return driver


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _find_first(driver: uc.Chrome, selectors: list[str], *, parent=None) -> object | None:
    """Try each CSS selector and return the first element found, or ``None``."""
    root = parent or driver
    for sel in selectors:
        try:
            elem = root.find_element(By.CSS_SELECTOR, sel)
            return elem
        except NoSuchElementException:
            continue
    return None


def _find_all(driver: uc.Chrome, selectors: list[str], *, parent=None) -> list:
    """Try each CSS selector and return elements from the first selector that matches."""
    root = parent or driver
    for sel in selectors:
        elems = root.find_elements(By.CSS_SELECTOR, sel)
        if elems:
            return elems
    return []


def _safe_text(element, default: str = "") -> str:
    """Get element text safely, returning *default* on error."""
    try:
        return (element.text or "").strip()
    except (StaleElementReferenceException, AttributeError):
        return default


def _build_search_url(keyword: str, location: str, start: int = 0) -> str:
    """Construct a LinkedIn job search URL with all required filters."""
    params = "&".join([
        f"keywords={quote_plus(keyword)}",
        f"location={quote_plus(location)}",
        _FILTER_EASY_APPLY,
        _FILTER_PAST_WEEK,
        _FILTER_EXPERIENCE,
        _FILTER_JOB_TYPE,
        f"start={start}",
    ])
    return f"{_LINKEDIN_JOBS_URL}?{params}"


def _extract_job_id(card) -> str:
    """Pull the LinkedIn job ID from a card element."""
    # data-job-id on the card itself
    job_id = card.get_attribute("data-job-id")
    if job_id:
        return job_id.strip()

    # data-job-id on an inner element
    try:
        inner = card.find_element(By.CSS_SELECTOR, "[data-job-id]")
        job_id = inner.get_attribute("data-job-id")
        if job_id:
            return job_id.strip()
    except NoSuchElementException:
        pass

    # Fallback: pull from an <a> href containing /jobs/view/<id>
    try:
        link = card.find_element(By.CSS_SELECTOR, "a[href*='/jobs/view/']")
        href = link.get_attribute("href") or ""
        parts = href.split("/jobs/view/")
        if len(parts) > 1:
            return parts[1].split("/")[0].split("?")[0]
    except NoSuchElementException:
        pass

    return ""


def _extract_job_url(card) -> str:
    """Build a canonical LinkedIn job URL from the card."""
    job_id = _extract_job_id(card)
    if job_id:
        return f"https://www.linkedin.com/jobs/view/{job_id}/"

    # Fallback: grab the href directly
    try:
        link = card.find_element(By.CSS_SELECTOR, "a[href*='/jobs/']")
        href = link.get_attribute("href") or ""
        return href.split("?")[0]
    except NoSuchElementException:
        return ""


# ---------------------------------------------------------------------------
# WEB-2: LinkedIn search logic
# ---------------------------------------------------------------------------


def search_jobs(driver: uc.Chrome, keyword: str, location: str) -> list[dict]:
    """Search LinkedIn for jobs matching *keyword* and *location*.

    Paginates through results (25 per page) and returns a list of job
    metadata dicts with keys: ``title``, ``company``, ``location``,
    ``url``, ``job_id``.

    Args:
        driver: The Selenium Chrome driver.
        keyword: Search keyword string.
        location: Location string (e.g. "Dallas, TX").

    Returns:
        List of job dicts.  Returns an empty list when no results are found.
    """
    jobs: list[dict] = []
    start = 0

    while True:
        url = _build_search_url(keyword, location, start)
        log.info("Searching: %s | %s (offset %d)", keyword, location, start)
        driver.get(url)

        try:
            WebDriverWait(driver, 15).until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "div.jobs-search-results-list"))
            )
        except TimeoutException:
            # Check for "No matching jobs found"
            try:
                driver.find_element(By.CSS_SELECTOR, "div.jobs-search-no-results-banner")
                log.info("No results for '%s' in '%s'", keyword, location)
                return jobs
            except NoSuchElementException:
                pass
            # Also try text-based detection
            if "no matching jobs" in (driver.page_source or "").lower():
                log.info("No results for '%s' in '%s'", keyword, location)
                return jobs
            log.warning("Timeout waiting for job results (keyword=%s, location=%s)", keyword, location)
            return jobs

        cards = _find_all(driver, _JOB_CARD_SELECTORS)
        if not cards:
            log.info("No job cards found for '%s' in '%s'", keyword, location)
            break

        for card in cards:
            try:
                title_elem = _find_first(driver, _JOB_TITLE_SELECTORS, parent=card)
                company_elem = _find_first(driver, _JOB_COMPANY_SELECTORS, parent=card)
                location_elem = _find_first(driver, _JOB_LOCATION_SELECTORS, parent=card)

                title = _safe_text(title_elem)
                company = _safe_text(company_elem)
                loc = _safe_text(location_elem)
                job_url = _extract_job_url(card)
                job_id = _extract_job_id(card)

                if not title or not job_url:
                    continue

                jobs.append({
                    "title": title,
                    "company": company,
                    "location": loc,
                    "url": job_url,
                    "job_id": job_id,
                })
            except StaleElementReferenceException:
                log.debug("Stale card element, skipping")
                continue

        # Check if there are more pages
        if len(cards) < _RESULTS_PER_PAGE:
            break

        start += _RESULTS_PER_PAGE

        # Safety cap: don't paginate beyond 10 pages (250 jobs per search)
        if start >= 250:
            log.info("Reached pagination cap for '%s' in '%s'", keyword, location)
            break

    log.info("Found %d jobs for '%s' in '%s'", len(jobs), keyword, location)
    return jobs


# ---------------------------------------------------------------------------
# WEB-3: Easy Apply flow
# ---------------------------------------------------------------------------


def _click_easy_apply(driver: uc.Chrome) -> bool:
    """Find and click the Easy Apply button.  Returns True on success."""
    for sel in _EASY_APPLY_BUTTON_SELECTORS:
        try:
            btn = WebDriverWait(driver, 5).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, sel))
            )
            btn.click()
            return True
        except (TimeoutException, ElementClickInterceptedException, NoSuchElementException):
            continue
    return False


def _is_already_applied(driver: uc.Chrome) -> bool:
    """Check whether the current job page shows 'Already applied'."""
    indicators = [
        "span.artdeco-inline-feedback__message",
        "span[class*='post-apply-timeline']",
        "div.post-apply-timeline",
    ]
    for sel in indicators:
        try:
            elem = driver.find_element(By.CSS_SELECTOR, sel)
            text = (elem.text or "").lower()
            if "applied" in text:
                return True
        except NoSuchElementException:
            continue

    # Also check button text
    for sel in _EASY_APPLY_BUTTON_SELECTORS:
        try:
            btn = driver.find_element(By.CSS_SELECTOR, sel)
            text = (btn.text or "").lower()
            if "applied" in text:
                return True
        except NoSuchElementException:
            continue

    return False


def _get_modal(driver: uc.Chrome) -> object | None:
    """Return the Easy Apply modal element if present."""
    return _find_first(driver, _MODAL_SELECTORS)


def _find_form_fields(modal) -> list:
    """Locate all fillable form fields inside the Easy Apply modal."""
    fields: list = []
    selectors = [
        "input:not([type='hidden']):not([type='submit']):not([type='button'])",
        "textarea",
        "select",
    ]
    for sel in selectors:
        try:
            found = modal.find_elements(By.CSS_SELECTOR, sel)
            fields.extend(found)
        except StaleElementReferenceException:
            continue
    return fields


def _click_modal_button(driver: uc.Chrome, selectors: list[str], label_texts: list[str] | None = None) -> bool:
    """Click a button inside the Easy Apply modal by selectors or label text.

    Args:
        driver: The Selenium driver.
        selectors: CSS selectors to try.
        label_texts: Optional fallback — find buttons whose text contains one
            of these strings (case-insensitive).

    Returns:
        True if a button was successfully clicked.
    """
    for sel in selectors:
        try:
            btn = WebDriverWait(driver, 3).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, sel))
            )
            btn.click()
            return True
        except (TimeoutException, ElementClickInterceptedException, NoSuchElementException):
            continue

    # Text-based fallback
    if label_texts:
        try:
            buttons = driver.find_elements(By.CSS_SELECTOR, "button")
            for btn in buttons:
                btn_text = _safe_text(btn).lower()
                for label in label_texts:
                    if label.lower() in btn_text:
                        btn.click()
                        return True
        except (StaleElementReferenceException, ElementClickInterceptedException):
            pass

    return False


def _dismiss_modal(driver: uc.Chrome) -> None:
    """Close any post-submission confirmation or the Easy Apply modal."""
    _click_modal_button(driver, _DISMISS_BUTTON_SELECTORS, ["dismiss", "done"])

    # If the modal is still open, try the X (close) button
    try:
        close_btn = driver.find_element(
            By.CSS_SELECTOR, "button[aria-label='Dismiss']"
        )
        close_btn.click()
    except (NoSuchElementException, ElementClickInterceptedException):
        pass

    # Handle the "Discard application?" confirmation that appears when closing
    # mid-flow.
    try:
        discard_btn = driver.find_element(
            By.CSS_SELECTOR, "button[data-control-name='discard_application_confirm_btn']"
        )
        discard_btn.click()
    except NoSuchElementException:
        pass

    # Additional fallback: look for "Discard" button by text
    try:
        buttons = driver.find_elements(By.CSS_SELECTOR, "button")
        for btn in buttons:
            if _safe_text(btn).lower() == "discard":
                btn.click()
                break
    except (StaleElementReferenceException, ElementClickInterceptedException):
        pass


def _get_options_for_field(modal, element) -> list[str] | None:
    """Extract options for dropdown/radio fields, return None for free-text."""
    from selenium.webdriver.support.ui import Select as _Select

    tag = element.tag_name.lower()
    if tag == "select":
        try:
            sel = _Select(element)
            return [
                opt.text.strip()
                for opt in sel.options
                if opt.text.strip() and opt.text.strip().lower() not in (
                    "select", "select...", "choose", "-- select --", ""
                )
            ]
        except Exception:
            return None

    input_type = (element.get_attribute("type") or "").lower()
    if input_type == "radio":
        name = element.get_attribute("name")
        if name:
            try:
                radios = modal.find_elements(
                    By.CSS_SELECTOR, f'input[type="radio"][name="{name}"]'
                )
                opts: list[str] = []
                driver = element.parent
                for r in radios:
                    rid = r.get_attribute("id")
                    label_text = ""
                    if rid:
                        try:
                            lbl = driver.find_element(
                                By.CSS_SELECTOR, f'label[for="{rid}"]'
                            )
                            label_text = lbl.text.strip()
                        except NoSuchElementException:
                            pass
                    if not label_text:
                        try:
                            parent = r.find_element(By.XPATH, "./..")
                            label_text = parent.text.strip()
                        except Exception:
                            pass
                    if label_text:
                        opts.append(label_text)
                return opts if opts else None
            except Exception:
                return None

    return None


def apply_to_job(
    driver: uc.Chrome,
    job: dict,
    resume_path: str,
    form_filler: FormFiller,
    dry_run: bool = False,
) -> tuple[str, str]:
    """Apply to a single job via Easy Apply.

    Args:
        driver: The Selenium Chrome driver.
        job: Job metadata dict (``title``, ``company``, ``url``, etc.).
        resume_path: Absolute path to the resume PDF to upload.
        form_filler: A :class:`FormFiller` instance for filling form fields.
        dry_run: If True, navigate to Review but do not click Submit.

    Returns:
        ``(status, reason)`` where *status* is ``"applied"``, ``"skipped"``,
        or ``"failed"``.
    """
    job_url = job.get("url", "")
    if not job_url:
        return ("failed", "no job URL")

    try:
        driver.get(job_url)
        WebDriverWait(driver, 10).until(
            EC.presence_of_element_located((By.CSS_SELECTOR, "div.jobs-unified-top-card"))
        )
    except TimeoutException:
        # Page may have loaded with a different structure — continue
        pass

    # Check "Already applied"
    if _is_already_applied(driver):
        return ("skipped", "already applied")

    # Click Easy Apply
    if not _click_easy_apply(driver):
        return ("failed", "Easy Apply button not found")

    # Wait for modal to appear
    try:
        WebDriverWait(driver, 8).until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, ", ".join(_MODAL_SELECTORS))
            )
        )
    except TimeoutException:
        return ("failed", "Easy Apply modal did not open")

    # Step through modal pages
    max_pages = 10  # safety cap
    for page_num in range(max_pages):
        time.sleep(0.5)  # brief pause for page transition

        modal = _get_modal(driver)
        if modal is None:
            # Modal closed — might mean submission happened
            break

        # Find all form fields on current page
        fields = _find_form_fields(modal)

        for field in fields:
            try:
                field_type = form_filler.detect_field_type(field)

                if field_type == "file":
                    # Upload resume
                    try:
                        field.send_keys(resume_path)
                        log.debug("Uploaded resume: %s", resume_path)
                    except Exception as exc:
                        log.warning("Resume upload failed: %s", exc)
                    continue

                if field_type == "unknown":
                    continue

                # Skip fields that already have a value
                if field_type in ("text", "textarea"):
                    current_val = field.get_attribute("value") or ""
                    if current_val.strip():
                        continue

                if field_type in ("radio", "checkbox"):
                    if field.is_selected():
                        continue

                question_text = form_filler.extract_question_text(field)
                if not question_text:
                    continue

                options = _get_options_for_field(modal, field)

                form_filler.fill_field(
                    driver, field, question_text, field_type,
                    options, form_filler.resume, form_filler.category,
                )
            except StaleElementReferenceException:
                log.debug("Stale element on page %d, skipping field", page_num)
                continue
            except Exception as exc:
                log.warning("Error filling field on page %d: %s", page_num, exc)
                continue

        # Determine which button to click: Submit > Review > Next
        if _click_modal_button(driver, _SUBMIT_BUTTON_SELECTORS, ["submit"]):
            if dry_run:
                # In dry_run we shouldn't have reached submit — but if we
                # do, we already clicked.  Log a warning.
                log.warning("Dry-run: Submit button was clicked unexpectedly")
            # Wait briefly for confirmation
            time.sleep(1)
            _dismiss_modal(driver)
            return ("applied", "")

        if _click_modal_button(driver, _REVIEW_BUTTON_SELECTORS, ["review"]):
            if dry_run:
                log.info("Dry-run: reached Review, closing modal")
                _dismiss_modal(driver)
                return ("skipped", "dry run")
            # After Review, the next page should have Submit
            continue

        if _click_modal_button(
            driver, _NEXT_BUTTON_SELECTORS, ["next", "continue"]
        ):
            continue

        # No actionable button found — try to dismiss and fail
        log.warning("No Next/Review/Submit button found on page %d", page_num)
        _dismiss_modal(driver)
        return ("failed", "navigation button not found")

    # Exhausted max pages
    _dismiss_modal(driver)
    return ("failed", "exceeded max modal pages")


# ---------------------------------------------------------------------------
# WEB-4: Main search-and-apply loop
# ---------------------------------------------------------------------------


def get_job_description(driver: uc.Chrome) -> str:
    """Extract the job description text from the current page."""
    elem = _find_first(driver, _DESCRIPTION_SELECTORS)
    if elem:
        return _safe_text(elem)
    return ""


def run_category(
    driver: uc.Chrome,
    category: str,
    cfg: dict,
    resume_data: dict,
    stats: dict,
    shutdown_check: callable | None = None,
    dry_run: bool = False,
) -> None:
    """Run the full search-and-apply loop for one job category.

    Iterates over all keywords and locations, filters jobs, and applies
    to qualifying ones.

    Args:
        driver: The Selenium Chrome driver.
        category: Role category (``SWE``, ``FS``, ``MLAI``, ``DE``).
        cfg: Application configuration dictionary.
        resume_data: Parsed resume from ``plain_text_resume.yaml``.
        stats: Mutable dict tracking ``applied``/``skipped``/``failed`` counts
            for the current category. Updated in-place.
        shutdown_check: Optional callable returning ``True`` to abort.
        dry_run: If True, don't actually submit applications.
    """
    max_per_cat = cfg.get("max_per_category", 30)
    delay_min = cfg.get("delay_min_seconds", 30)
    delay_max = cfg.get("delay_max_seconds", 60)
    search_delay_min = cfg.get("search_delay_min_seconds", 120)
    search_delay_max = cfg.get("search_delay_max_seconds", 300)

    keywords = config.get_search_keywords(category)
    locations = config.get_locations()
    resume_path = str(config.get_resume_path(category))

    stats.setdefault("applied", 0)
    stats.setdefault("skipped", 0)
    stats.setdefault("failed", 0)

    for keyword in keywords:
        for loc_idx, location in enumerate(locations):
            if shutdown_check and shutdown_check():
                log.info("Shutdown requested, stopping category %s", category)
                return

            if stats["applied"] >= max_per_cat:
                log.info(
                    "Reached max applications (%d) for category %s",
                    max_per_cat,
                    category,
                )
                return

            jobs = search_jobs(driver, keyword, location)

            for job in jobs:
                if shutdown_check and shutdown_check():
                    log.info("Shutdown requested, stopping category %s", category)
                    return

                if stats["applied"] >= max_per_cat:
                    log.info(
                        "Reached max applications (%d) for category %s",
                        max_per_cat,
                        category,
                    )
                    return

                # --- Title filter ---
                skip, reason = filters.should_skip_title(job.get("title", ""))
                if skip:
                    app_logger.log_application(
                        category=category,
                        company=job.get("company", ""),
                        title=job.get("title", ""),
                        location=job.get("location", ""),
                        status="SKIPPED",
                        reason=reason,
                        url=job.get("url", ""),
                    )
                    stats["skipped"] += 1
                    continue

                # --- Navigate and check description ---
                try:
                    driver.get(job.get("url", ""))
                    WebDriverWait(driver, 10).until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, ", ".join(_DESCRIPTION_SELECTORS))
                        )
                    )
                except TimeoutException:
                    pass

                description = get_job_description(driver)
                skip, reason = filters.should_skip_description(description)
                if skip:
                    app_logger.log_application(
                        category=category,
                        company=job.get("company", ""),
                        title=job.get("title", ""),
                        location=job.get("location", ""),
                        status="SKIPPED",
                        reason=reason,
                        url=job.get("url", ""),
                    )
                    stats["skipped"] += 1
                    continue

                # --- Apply ---
                filler = FormFiller(resume_data, category)

                status, apply_reason = apply_to_job(
                    driver, job, resume_path, filler, dry_run=dry_run,
                )

                status_upper = status.upper()
                app_logger.log_application(
                    category=category,
                    company=job.get("company", ""),
                    title=job.get("title", ""),
                    location=job.get("location", ""),
                    status=status_upper,
                    reason=apply_reason,
                    url=job.get("url", ""),
                )

                if status == "applied":
                    stats["applied"] += 1
                elif status == "skipped":
                    stats["skipped"] += 1
                else:
                    stats["failed"] += 1

                # Rate-limiting delay between applications
                delay = random.uniform(delay_min, delay_max)
                log.debug("Sleeping %.1f seconds between applications", delay)
                time.sleep(delay)

            # Delay between location searches (skip after last location)
            if loc_idx < len(locations) - 1:
                search_delay = random.uniform(search_delay_min, search_delay_max)
                log.debug("Sleeping %.1f seconds between searches", search_delay)
                time.sleep(search_delay)
