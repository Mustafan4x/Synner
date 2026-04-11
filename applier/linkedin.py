"""LinkedIn search and Easy Apply automation for Synner."""

from __future__ import annotations

import logging
import random
import time
from pathlib import Path
from urllib.parse import quote_plus

import undetected_chromedriver as uc
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    ElementNotInteractableException,
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
    "li.scaffold-layout__list-item",
    "li.jobs-search-results__list-item",
    "div.job-card-container",
    "li.ember-view.occludable-update",
    "div.jobs-search-results__list-item",
    "div[data-job-id]",
    "li[data-occludable-job-id]",
]

_JOB_TITLE_SELECTORS = [
    "a.job-card-list__title",
    "a.job-card-container__link",
    "a.job-card-list__title--link",
    "a[class*='job-card'] span",
    ".job-card-list__title",
    "a[href*='/jobs/view/'] strong",
    "a[href*='/jobs/view/'] span",
    "a[href*='/jobs/view/']",
]

_JOB_COMPANY_SELECTORS = [
    "span.job-card-container__primary-description",
    "a.job-card-container__company-name",
    ".job-card-container__company-name",
    "span.artdeco-entity-lockup__subtitle",
    ".artdeco-entity-lockup__subtitle span",
    "div.artdeco-entity-lockup__subtitle",
]

_JOB_LOCATION_SELECTORS = [
    "li.job-card-container__metadata-item",
    "span.job-card-container__metadata-item",
    ".artdeco-entity-lockup__caption",
    ".artdeco-entity-lockup__caption span",
    "div.artdeco-entity-lockup__caption",
]

_EASY_APPLY_BUTTON_SELECTORS = [
    "button.jobs-apply-button",
    "button[aria-label*='Easy Apply']",
    "button.jobs-apply-button--top-card",
    "div.jobs-apply-button--top-card button",
    "button[class*='jobs-apply-button']",
    # Newer LinkedIn DOM patterns (2025-2026)
    "div.jobs-unified-top-card button[class*='apply']",
    "div[class*='top-card'] button[class*='apply']",
    "div.job-details-jobs-unified-top-card__container--two-pane button",
    "button.jobs-apply-button.artdeco-button--primary",
    "div[class*='jobs-unified-top-card'] button.artdeco-button--primary",
    "div[class*='job-details'] button[aria-label*='Apply']",
    "button[aria-label*='apply' i]",
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


def _clean_profile_crash_flag(profile_dir: str) -> None:
    """Clear Chrome's crash flag, stale lock files, and session-restore state."""
    profile = Path(profile_dir)

    # Remove stale lock files left by crashed Chrome processes.
    # These are symlinks (e.g. SingletonLock -> HOSTNAME-PID), and when the
    # target disappears they become dangling symlinks. Path.exists() follows
    # symlinks so it returns False for dangling ones, hiding them from any
    # existence check — we must unlink blindly and catch FileNotFoundError.
    for lock_file in ("SingletonLock", "SingletonCookie", "SingletonSocket"):
        lock_path = profile / lock_file
        try:
            lock_path.unlink()
            log.debug("Removed stale lock: %s", lock_file)
        except FileNotFoundError:
            pass
        except OSError:
            pass

    # Clear Chrome's session-restore state. Without this, Chrome reopens
    # whatever tabs were visible last time (e.g. a Google new-tab), which
    # sits on top of the automation's LinkedIn tab and makes it look like
    # the bot never navigated to LinkedIn. The automation always starts
    # fresh, so there's nothing worth restoring.
    sessions_dir = profile / "Default" / "Sessions"
    if sessions_dir.exists():
        for entry in sessions_dir.iterdir():
            try:
                entry.unlink()
            except (FileNotFoundError, OSError):
                pass

    # Fix the exited_cleanly flag in Preferences.
    # Only attempt if the file is reasonably sized (< 50 MB).
    # Corrupted/bloated profiles should be deleted and recreated.
    prefs_path = profile / "Default" / "Preferences"
    if not prefs_path.exists():
        return
    try:
        size = prefs_path.stat().st_size
        if size > 50_000_000:  # > 50 MB = corrupted
            log.warning("Preferences file is %.0f MB — deleting corrupted profile", size / 1_000_000)
            import shutil
            default_dir = profile / "Default"
            shutil.rmtree(default_dir, ignore_errors=True)
            return

        import json as _json
        data = _json.loads(prefs_path.read_text(encoding="utf-8"))
        if "profile" in data:
            data["profile"]["exit_type"] = "Normal"
            data["profile"]["exited_cleanly"] = True
        prefs_path.write_text(_json.dumps(data), encoding="utf-8")
        log.debug("Cleaned Chrome profile crash flag")
    except Exception:
        pass


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

    # Clean crash flag before launching to prevent restore dialogs
    _clean_profile_crash_flag(profile_dir)
    options.add_argument(f"--user-data-dir={profile_dir}")

    if cfg.get("headless", False):
        options.add_argument("--headless=new")

    options.add_argument("--window-size=1920,1080")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")

    # Suppress crash recovery dialogs and restore prompts that appear
    # after unclean shutdowns (e.g. Ctrl+C during testing)
    options.add_argument("--disable-session-crashed-bubble")
    options.add_argument("--disable-infobars")
    options.add_argument("--disable-popup-blocking")
    options.add_argument("--hide-crash-restore-bubble")
    options.add_argument("--noerrdialogs")
    options.add_argument("--disable-features=InfiniteSessionRestore")

    driver = uc.Chrome(options=options)
    # Note: do NOT call driver.maximize_window() here. Chrome 140+ with
    # undetected-chromedriver raises "Browser window not found" because the
    # DevTools target isn't ready yet. The --window-size arg above already
    # sizes the window, so maximize is unnecessary.
    # Keep implicit wait short — we use explicit WebDriverWait where
    # longer timeouts are needed.  A long implicit wait causes massive
    # delays in helper functions that try multiple selectors.
    driver.implicitly_wait(0)

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

        # Wait for actual job links to appear in the DOM. This is the most
        # reliable signal that results have loaded, regardless of what
        # container class names LinkedIn uses.
        try:
            WebDriverWait(driver, 15).until(
                lambda d: d.execute_script(
                    "return document.querySelectorAll('a[href*=\"/jobs/view/\"]').length > 0"
                )
            )
        except TimeoutException:
            # Check for "No matching jobs found"
            page_text = (driver.page_source or "").lower()
            if "no matching jobs" in page_text or "no results" in page_text:
                log.info("No results for '%s' in '%s'", keyword, location)
                return jobs
            log.warning("Timeout waiting for job links (keyword=%s, location=%s)", keyword, location)
            return jobs

        # Small pause to let any remaining lazy-loaded cards render
        time.sleep(1)

        # Extract jobs via JavaScript — this is fully resilient to
        # LinkedIn DOM class name changes since it only relies on the
        # stable /jobs/view/<id> URL pattern in <a> hrefs.
        page_jobs: list[dict] = []
        try:
            page_jobs = driver.execute_script("""
                var results = [];
                var links = document.querySelectorAll('a[href*="/jobs/view/"]');
                var seen = new Set();

                for (var i = 0; i < links.length; i++) {
                    var link = links[i];
                    var href = link.href || '';
                    var match = href.match(/\\/jobs\\/view\\/(\\d+)/);
                    if (!match) continue;
                    var jobId = match[1];
                    if (seen.has(jobId)) continue;
                    seen.add(jobId);

                    // Get title from the link text.
                    // Use the first line only — badge text like "with verification"
                    // sometimes appears on subsequent lines inside the same <a>.
                    var rawTitle = (link.innerText || '').trim();
                    var title = rawTitle.split('\\n')[0].trim();
                    if (title.length < 3) continue;

                    // Walk up to the card container (the <li> in the results list)
                    var card = link.closest('li') || link.closest('div[data-job-id]');
                    if (!card) continue;

                    var company = '';
                    var location = '';

                    // Strategy 1: Look for sibling/descendant elements by
                    // common LinkedIn patterns. The company is usually in a
                    // separate element below the title link.
                    var companyEl = card.querySelector(
                        'span.job-card-container__primary-description, ' +
                        'a.job-card-container__company-name, ' +
                        '.artdeco-entity-lockup__subtitle, ' +
                        'div.artdeco-entity-lockup__subtitle'
                    );
                    if (companyEl) company = companyEl.innerText.trim();

                    var locationEl = card.querySelector(
                        'li.job-card-container__metadata-item, ' +
                        'span.job-card-container__metadata-item, ' +
                        '.artdeco-entity-lockup__caption, ' +
                        'div.artdeco-entity-lockup__caption'
                    );
                    if (locationEl) location = locationEl.innerText.trim();

                    // Strategy 2: If selectors didn't work, parse text lines.
                    // Get all text from elements that are NOT the title link.
                    if (!company) {
                        var allText = [];
                        var children = card.querySelectorAll('*');
                        for (var c = 0; c < children.length; c++) {
                            var el = children[c];
                            // Skip the title link and its children
                            if (el === link || link.contains(el)) continue;
                            // Only leaf text nodes
                            if (el.children.length === 0 && el.innerText) {
                                var t = el.innerText.trim();
                                if (t.length > 1 && t !== title && t.indexOf(title) === -1) {
                                    allText.push(t);
                                }
                            }
                        }
                        // Remove noise like "Easy Apply", "Promoted", timestamps
                        var noise = ['easy apply', 'promoted', 'viewed', 'applied',
                                     'actively recruiting', 'be an early applicant',
                                     'new', 'ago', 'reposted'];
                        allText = allText.filter(function(t) {
                            var lower = t.toLowerCase();
                            for (var n = 0; n < noise.length; n++) {
                                if (lower === noise[n] || lower.indexOf(' ago') !== -1) return false;
                            }
                            return true;
                        });
                        if (allText.length >= 1) company = allText[0];
                        if (allText.length >= 2) location = allText[1];
                    }

                    results.push({
                        title: title,
                        company: company,
                        location: location,
                        url: 'https://www.linkedin.com/jobs/view/' + jobId + '/',
                        job_id: jobId
                    });
                }
                return results;
            """) or []
        except Exception as exc:
            log.warning("JS job extraction failed: %s", exc)

        if page_jobs:
            log.info("Found %d job links on page for '%s' in '%s'", len(page_jobs), keyword, location)
            jobs.extend(page_jobs)
        else:
            log.info("No job cards extracted for '%s' in '%s'", keyword, location)
            break

        # Check if there are more pages
        if len(page_jobs) < _RESULTS_PER_PAGE:
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
    # Try CSS selectors first (fast path)
    for sel in _EASY_APPLY_BUTTON_SELECTORS:
        try:
            btn = WebDriverWait(driver, 2).until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, sel))
            )
            # Verify this is actually an Easy Apply / Apply button
            btn_text = _safe_text(btn).lower()
            if "apply" in btn_text or "easy" in btn_text:
                btn.click()
                log.info("Clicked Easy Apply via selector: %s", sel)
                return True
            # If no text check, click anyway for aria-label matches
            if "aria-label" in sel or "apply" in sel.lower():
                btn.click()
                log.info("Clicked Easy Apply via selector: %s", sel)
                return True
        except (TimeoutException, ElementClickInterceptedException, NoSuchElementException):
            continue

    # Text-based fallback: find ANY button containing "Easy Apply" or "Apply"
    log.debug("CSS selectors failed, trying text-based button search")
    try:
        buttons = driver.find_elements(By.CSS_SELECTOR, "button")
        for btn in buttons:
            btn_text = _safe_text(btn).lower()
            if "easy apply" in btn_text:
                driver.execute_script("arguments[0].scrollIntoView(true);", btn)
                time.sleep(0.3)
                btn.click()
                log.info("Clicked Easy Apply via text match: '%s'", btn_text.strip())
                return True
    except (StaleElementReferenceException, ElementClickInterceptedException):
        pass

    # XPath fallback: match by text content
    try:
        btn = driver.find_element(
            By.XPATH, "//button[contains(translate(., 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'easy apply')]"
        )
        driver.execute_script("arguments[0].scrollIntoView(true);", btn)
        time.sleep(0.3)
        driver.execute_script("arguments[0].click();", btn)
        log.info("Clicked Easy Apply via XPath text match")
        return True
    except NoSuchElementException:
        pass

    # JavaScript fallback: search shadow DOM and iframes
    try:
        clicked = driver.execute_script("""
            const buttons = document.querySelectorAll('button, [role="button"]');
            for (const btn of buttons) {
                const text = (btn.textContent || '').toLowerCase();
                const label = (btn.getAttribute('aria-label') || '').toLowerCase();
                if (text.includes('easy apply') || label.includes('easy apply')) {
                    btn.scrollIntoView(true);
                    btn.click();
                    return true;
                }
            }
            return false;
        """)
        if clicked:
            log.info("Clicked Easy Apply via JavaScript fallback")
            return True
    except Exception:
        pass

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
    seen_ids: set[int] = set()
    selectors = [
        "input:not([type='hidden']):not([type='submit']):not([type='button'])",
        "textarea",
        "select",
        # Custom ARIA comboboxes — LinkedIn uses these for some dropdowns
        # instead of native <select>. Handled by the custom-combobox branch
        # in form_filler._fill_dropdown.
        "[role='combobox']",
        "button[aria-haspopup='listbox']",
        "div[aria-haspopup='listbox']",
    ]
    for sel in selectors:
        try:
            found = modal.find_elements(By.CSS_SELECTOR, sel)
            for elem in found:
                # Dedupe in case the same element matches multiple selectors
                # (e.g. an input that also has role="combobox").
                key = id(elem._id) if hasattr(elem, "_id") else id(elem)
                if key in seen_ids:
                    continue
                seen_ids.add(key)
                fields.append(elem)
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
    # Direct find — no per-selector WebDriverWait. The modal DOM is already
    # settled by the caller's page-transition sleep, so waiting 3s per missing
    # button just burns time (LinkedIn shows only one of Submit/Review/Next
    # at a time, so two of the three probes always miss).
    for sel in selectors:
        try:
            btn = driver.find_element(By.CSS_SELECTOR, sel)
            if not btn.is_displayed() or not btn.is_enabled():
                continue
            btn.click()
            return True
        except (NoSuchElementException, ElementClickInterceptedException, ElementNotInteractableException, StaleElementReferenceException):
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
        except (StaleElementReferenceException, ElementClickInterceptedException, ElementNotInteractableException):
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
    except (NoSuchElementException, ElementClickInterceptedException, ElementNotInteractableException):
        pass

    # Handle the "Discard application?" confirmation that appears when closing
    # mid-flow.
    try:
        discard_btn = driver.find_element(
            By.CSS_SELECTOR, "button[data-control-name='discard_application_confirm_btn']"
        )
        discard_btn.click()
    except (NoSuchElementException, ElementClickInterceptedException, ElementNotInteractableException):
        pass

    # Additional fallback: look for "Discard" button by text
    try:
        buttons = driver.find_elements(By.CSS_SELECTOR, "button")
        for btn in buttons:
            if _safe_text(btn).lower() == "discard":
                btn.click()
                break
    except (StaleElementReferenceException, ElementClickInterceptedException, ElementNotInteractableException):
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

    # Custom ARIA combobox: open the widget, read its listbox, leave it
    # open so _fill_dropdown can click the chosen option without having to
    # re-open. If the widget is already open (some LinkedIn variants mount
    # the listbox eagerly), we read without clicking again.
    role = (element.get_attribute("role") or "").lower()
    haspopup = (element.get_attribute("aria-haspopup") or "").lower()
    if role == "combobox" or haspopup == "listbox":
        try:
            driver = element.parent
            expanded = (element.get_attribute("aria-expanded") or "").lower()
            if expanded != "true":
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
                except Exception:
                    pass
                try:
                    element.click()
                except (ElementClickInterceptedException, ElementNotInteractableException):
                    driver.execute_script("arguments[0].click();", element)
                time.sleep(0.3)  # allow listbox to render

            listbox = None
            controls_id = element.get_attribute("aria-controls")
            if controls_id:
                try:
                    listbox = driver.find_element(By.ID, controls_id)
                except NoSuchElementException:
                    listbox = None
            if listbox is None:
                # Find the first visible listbox anywhere in the document
                try:
                    candidates = driver.find_elements(By.CSS_SELECTOR, "[role='listbox'], ul[role='listbox']")
                    for cand in candidates:
                        if cand.is_displayed():
                            listbox = cand
                            break
                except Exception:
                    pass

            if listbox is None:
                return None

            opts: list[str] = []
            try:
                option_elems = listbox.find_elements(
                    By.CSS_SELECTOR, "[role='option'], li[role='option']"
                )
                if not option_elems:
                    # Fallback: any direct children with visible text
                    option_elems = listbox.find_elements(By.CSS_SELECTOR, "li, [role='menuitem']")
                for opt in option_elems:
                    try:
                        text = (opt.text or "").strip()
                    except Exception:
                        continue
                    if text and text.lower() not in (
                        "select", "select an option", "select...", "choose", "-- select --"
                    ):
                        opts.append(text)
            except Exception:
                return None
            return opts if opts else None
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
    resume_state: dict | None = None,
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

    # run_category already loaded this job's detail panel (either by clicking
    # the card in search results or by navigating).  Only navigate if we
    # somehow ended up on a different page.
    current_url = driver.current_url or ""
    job_id = job.get("job_id", "")
    needs_nav = job_url and "/jobs/search/" not in current_url and job_id not in current_url

    if needs_nav:
        driver.get(job_url)
        try:
            WebDriverWait(driver, 15).until(
                lambda d: d.execute_script("""
                    var buttons = document.querySelectorAll('button, [role="button"]');
                    for (var i = 0; i < buttons.length; i++) {
                        var text = (buttons[i].textContent || '').toLowerCase();
                        var label = (buttons[i].getAttribute('aria-label') || '').toLowerCase();
                        if (text.includes('easy apply') || label.includes('easy apply') ||
                            text.includes('applied')) {
                            return true;
                        }
                    }
                    return false;
                """)
            )
        except TimeoutException:
            return ("failed", "job page did not load Easy Apply button")

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
        time.sleep(1)  # pause for page transition and DOM to settle

        modal = _get_modal(driver)
        if modal is None:
            # Modal closed — might mean submission happened
            break

        # Find all form fields on current page.
        # Re-find modal and fields to avoid stale references after DOM changes.
        modal = _get_modal(driver)
        if modal is None:
            break

        # Detect the "Top choice" page (LinkedIn Premium feature, only 3 uses
        # per month) — we never want to spend one, so skip field processing
        # entirely and just click Next.
        try:
            modal_text = (modal.text or "").lower()
        except StaleElementReferenceException:
            modal_text = ""
        if "top choice" in modal_text:
            log.debug("Top choice page detected, skipping straight to Next")
            if _click_modal_button(driver, _NEXT_BUTTON_SELECTORS, ["next", "continue"]):
                continue
            # Fall through to normal button handling if Next click failed

        # Detect the "Contact info" page — LinkedIn's first Easy Apply page,
        # always pre-filled from profile. No reason to inspect fields; jump
        # straight to Next.
        if "contact info" in modal_text:
            log.debug("Contact info page detected, skipping straight to Next")
            if _click_modal_button(driver, _NEXT_BUTTON_SELECTORS, ["next", "continue"]):
                continue

        fields = _find_form_fields(modal)

        for field in fields:
            try:
                field_type = form_filler.detect_field_type(field)

                if field_type == "file":
                    # Skip re-upload if LinkedIn already has this resume from
                    # an earlier application in the same run — it auto-selects
                    # the most recent upload, so touching the file input again
                    # just triggers a slow re-parse.
                    already_uploaded = (
                        resume_state is not None
                        and resume_state.get("last_uploaded") == resume_path
                    )
                    if already_uploaded:
                        log.debug("Resume already uploaded this run, reusing: %s", resume_path)
                        continue
                    try:
                        field.send_keys(resume_path)
                        log.debug("Uploaded resume: %s", resume_path)
                        if resume_state is not None:
                            resume_state["last_uploaded"] = resume_path
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
                    # Skip resume selection radios — the correct resume is
                    # already uploaded/selected. Also skip "top choice".
                    field_id = field.get_attribute("id") or ""
                    field_name = field.get_attribute("name") or ""
                    skip_patterns = ["document", "resume", "topchoice", "topChoice"]
                    if any(p.lower() in (field_id + field_name).lower() for p in skip_patterns):
                        log.debug("Skipping non-question field: %s", field_id or field_name)
                        continue

                question_text = form_filler.extract_question_text(field)
                if not question_text:
                    continue

                options = _get_options_for_field(modal, field)

                form_filler.fill_field(
                    driver, field, question_text, field_type,
                    options, form_filler.resume, form_filler.category,
                )
            except (StaleElementReferenceException, ElementNotInteractableException):
                log.debug("Element issue on page %d, skipping field", page_num)
                continue
            except Exception as exc:
                log.warning("Error filling field on page %d: %s", page_num, exc)
                continue

        # Determine which button to click: Submit > Review > Next
        # In dry-run mode, treat Submit like Review — don't click it.
        if dry_run:
            # Check if Submit is present without clicking it
            submit_present = _find_first(driver, _SUBMIT_BUTTON_SELECTORS)
            if submit_present:
                log.info("Dry-run: Submit button found, closing without submitting")
                _dismiss_modal(driver)
                return ("skipped", "dry run")

        if _click_modal_button(driver, _SUBMIT_BUTTON_SELECTORS, ["submit"]):
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
    resume_state: dict | None = None,
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

    seen_job_ids: set[str] = set()

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

                # --- Dedup: skip jobs we've already seen ---
                jid = job.get("job_id", "")
                if jid and jid in seen_job_ids:
                    continue
                if jid:
                    seen_job_ids.add(jid)

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

                # --- Click job card in search results to load details ---
                log.info("Checking: %s @ %s", job.get("title", "?"), job.get("company", "?"))

                # Click the job card in the search results sidebar instead of
                # doing a full driver.get(). This loads the detail in the right
                # panel via AJAX which is much faster.
                job_clicked = False
                jid = job.get("job_id", "")
                if jid:
                    try:
                        job_clicked = driver.execute_script("""
                            var jobId = arguments[0];
                            // Try clicking a link to this job in the results list
                            var links = document.querySelectorAll('a[href*="/jobs/view/' + jobId + '"]');
                            for (var i = 0; i < links.length; i++) {
                                var link = links[i];
                                // Make sure it's in the results list, not the detail panel
                                var card = link.closest('li');
                                if (card) {
                                    link.click();
                                    return true;
                                }
                            }
                            return false;
                        """, jid)
                    except Exception:
                        job_clicked = False

                if not job_clicked:
                    # Fallback: full page navigation
                    driver.get(job.get("url", ""))

                # Wait for the Easy Apply button to appear in the detail panel
                try:
                    WebDriverWait(driver, 10).until(
                        lambda d: d.execute_script("""
                            var buttons = document.querySelectorAll('button, [role="button"]');
                            for (var i = 0; i < buttons.length; i++) {
                                var text = (buttons[i].textContent || '').toLowerCase();
                                var label = (buttons[i].getAttribute('aria-label') || '').toLowerCase();
                                if (text.includes('easy apply') || label.includes('easy apply'))
                                    return true;
                            }
                            return false;
                        """)
                    )
                except TimeoutException:
                    log.info("No Easy Apply button on page, skipping")
                    app_logger.log_application(
                        category=category,
                        company=job.get("company", ""),
                        title=job.get("title", ""),
                        location=job.get("location", ""),
                        status="SKIPPED",
                        reason="no Easy Apply on page",
                        url=job.get("url", ""),
                    )
                    stats["skipped"] += 1
                    continue

                # Enrich company/location from the detail panel if missing
                if not job.get("company"):
                    try:
                        detail = driver.execute_script("""
                            var co = document.querySelector(
                                'a[href*="/company/"]'
                            );
                            var loc = document.querySelector(
                                'span.jobs-unified-top-card__bullet, ' +
                                'span.job-details-jobs-unified-top-card__bullet'
                            );
                            return {
                                company: co ? co.innerText.trim() : '',
                                location: loc ? loc.innerText.trim() : ''
                            };
                        """)
                        if detail:
                            if detail.get("company"):
                                job["company"] = detail["company"]
                            if detail.get("location") and not job.get("location"):
                                job["location"] = detail["location"]
                    except Exception:
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

                try:
                    status, apply_reason = apply_to_job(
                        driver, job, resume_path, filler, dry_run=dry_run,
                        resume_state=resume_state,
                    )
                except Exception as exc:
                    log.warning("Exception during apply: %s", exc)
                    status, apply_reason = "failed", f"exception: {type(exc).__name__}"
                    # Try to clean up any open modal
                    try:
                        _dismiss_modal(driver)
                    except Exception:
                        pass

                # "Already applied" isn't a real skip — the bot made no
                # decision about whether the job was a good fit, LinkedIn
                # just told us we'd already submitted. Don't log it to CSV
                # and don't count it in the session stats; it would pollute
                # the success-rate numbers and inflate the skipped bucket.
                if status == "skipped" and apply_reason == "already applied":
                    log.info("Already applied, silently skipping")
                    continue

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
                # TODO: Re-enable delays for production use
                # delay = random.uniform(delay_min, delay_max)
                # log.debug("Sleeping %.1f seconds between applications", delay)
                # time.sleep(delay)

            # Delay between location searches (skip after last location)
            # TODO: Re-enable delays for production use
            # if loc_idx < len(locations) - 1:
            #     search_delay = random.uniform(search_delay_min, search_delay_max)
            #     log.debug("Sleeping %.1f seconds between searches", search_delay)
            #     time.sleep(search_delay)
