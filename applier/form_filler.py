"""Form detection and field filling logic for LinkedIn Easy Apply forms."""

import logging

from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webelement import WebElement
from selenium.webdriver.support.ui import Select

from applier import llm

logger = logging.getLogger(__name__)

# Input types that map to "text" field type
_TEXT_INPUT_TYPES = frozenset({"text", "email", "tel", "number", "url"})


class FormFiller:
    """Wraps LLM-based question answering with Selenium form field interaction."""

    def __init__(self, resume: dict, category: str) -> None:
        """Initialize the FormFiller.

        Args:
            resume: Parsed resume dictionary from plain_text_resume.yaml.
            category: Job category — one of SWE, FS, MLAI, DE.
        """
        self.resume = resume
        self.category = category

    def detect_field_type(self, element: WebElement) -> str:
        """Inspect a form element and return its field type.

        Args:
            element: The Selenium WebElement to inspect.

        Returns:
            One of: "text", "textarea", "dropdown", "radio", "checkbox",
            "file", "unknown".
        """
        tag_name = element.tag_name.lower()

        if tag_name == "textarea":
            return "textarea"

        if tag_name == "select":
            return "dropdown"

        if tag_name == "input":
            input_type = (element.get_attribute("type") or "text").lower()
            if input_type in _TEXT_INPUT_TYPES:
                return "text"
            if input_type == "radio":
                return "radio"
            if input_type == "checkbox":
                return "checkbox"
            if input_type == "file":
                return "file"

        return "unknown"

    def extract_question_text(self, element: WebElement) -> str:
        """Get the label/question text associated with a form field.

        Tries multiple strategies in order:
        1. Find a label element via the field's id attribute.
        2. Find a parent or sibling label element.
        3. aria-label attribute.
        4. placeholder attribute.
        5. Preceding text node via parent element.

        Args:
            element: The Selenium WebElement to find the label for.

        Returns:
            The question/label text, or empty string if nothing found.
        """
        # Strategy 1: label linked by 'for' attribute matching element id
        element_id = element.get_attribute("id")
        if element_id:
            try:
                driver = element.parent
                label = driver.find_element(By.CSS_SELECTOR, f'label[for="{element_id}"]')
                text = label.text.strip()
                if text:
                    return text
            except Exception:
                pass

        # Strategy 2: parent or sibling label element
        try:
            parent = element.find_element(By.XPATH, "./..")
            labels = parent.find_elements(By.TAG_NAME, "label")
            for label in labels:
                text = label.text.strip()
                if text:
                    return text
        except Exception:
            pass

        # Strategy 3: aria-label attribute
        aria_label = element.get_attribute("aria-label")
        if aria_label and aria_label.strip():
            return aria_label.strip()

        # Strategy 4: placeholder attribute
        placeholder = element.get_attribute("placeholder")
        if placeholder and placeholder.strip():
            return placeholder.strip()

        # Strategy 5: preceding text from parent element
        try:
            parent = element.find_element(By.XPATH, "./..")
            parent_text = parent.text.strip()
            if parent_text:
                return parent_text
        except Exception:
            pass

        return ""

    def fill_field(
        self,
        driver: webdriver.Chrome,
        element: WebElement,
        question_text: str,
        field_type: str,
        options: list[str] | None,
        resume: dict,
        category: str,
    ) -> None:
        """Determine how to fill a form field and fill it.

        Calls llm.answer_question() to get the answer, then interacts with
        the Selenium element based on field_type.

        Args:
            driver: The Selenium Chrome webdriver instance.
            element: The WebElement to fill.
            question_text: The question/label text for this field.
            field_type: One of "text", "textarea", "dropdown", "radio",
                        "checkbox".
            options: Multiple-choice options if applicable, None for free-text.
            resume: Parsed resume dictionary.
            category: Job category (SWE, FS, MLAI, DE).

        Raises:
            ValueError: If field_type is not a supported fillable type.
        """
        answer = llm.answer_question(question_text, options, resume, category)
        logger.debug(
            "Filling %s field for '%s' with answer: %s",
            field_type,
            question_text[:60],
            answer[:80] if answer else "",
        )

        if field_type in ("text", "textarea"):
            self._fill_text(element, answer)
        elif field_type == "dropdown":
            self._fill_dropdown(element, answer)
        elif field_type == "radio":
            self._fill_radio(driver, element, answer)
        elif field_type == "checkbox":
            self._fill_checkbox(driver, element, answer)
        else:
            raise ValueError(f"Unsupported field_type for filling: {field_type!r}")

    @staticmethod
    def _fill_text(element: WebElement, answer: str) -> None:
        """Clear and type into a text or textarea field.

        Args:
            element: The input/textarea WebElement.
            answer: The text to type.
        """
        element.clear()
        element.send_keys(answer)

    @staticmethod
    def _fill_dropdown(element: WebElement, answer: str) -> None:
        """Select an option from a dropdown (select element).

        Tries visible text match first, then partial match, then falls back
        to selecting the first non-empty option.

        Args:
            element: The select WebElement.
            answer: The desired option text.
        """
        select = Select(element)

        # Try exact visible text match
        try:
            select.select_by_visible_text(answer)
            return
        except Exception:
            pass

        # Try partial/case-insensitive match
        answer_lower = answer.lower().strip()
        for option in select.options:
            option_text = option.text.strip()
            if not option_text:
                continue
            if answer_lower in option_text.lower() or option_text.lower() in answer_lower:
                select.select_by_visible_text(option_text)
                return

        # Fallback: select first non-empty, non-placeholder option
        for option in select.options:
            option_text = option.text.strip()
            if option_text and option_text.lower() not in ("select", "select...", "choose", "-- select --", ""):
                select.select_by_visible_text(option_text)
                logger.warning(
                    "Dropdown fallback: selected '%s' (wanted '%s')",
                    option_text,
                    answer,
                )
                return

    @staticmethod
    def _fill_radio(driver: webdriver.Chrome, element: WebElement, answer: str) -> None:
        """Find and click the radio button matching the answer.

        Searches for radio buttons in the same group (by name attribute) and
        clicks the one whose associated label best matches the answer.

        Args:
            driver: The Selenium Chrome webdriver instance.
            element: One of the radio button WebElements in the group.
            answer: The desired option text to select.
        """
        name = element.get_attribute("name")
        if not name:
            # Fall back to clicking the element itself via JS
            driver.execute_script("arguments[0].click();", element)
            return

        radio_buttons = driver.find_elements(By.CSS_SELECTOR, f'input[type="radio"][name="{name}"]')
        answer_lower = answer.lower().strip()

        best_match: WebElement | None = None
        for radio in radio_buttons:
            # Try to find associated label text
            label_text = ""
            radio_id = radio.get_attribute("id")
            if radio_id:
                try:
                    label = driver.find_element(By.CSS_SELECTOR, f'label[for="{radio_id}"]')
                    label_text = label.text.strip()
                except Exception:
                    pass

            if not label_text:
                try:
                    parent = radio.find_element(By.XPATH, "./..")
                    label_text = parent.text.strip()
                except Exception:
                    pass

            if label_text and (
                answer_lower in label_text.lower()
                or label_text.lower() in answer_lower
                or label_text.lower() == answer_lower
            ):
                best_match = radio
                break

        if best_match is not None:
            # Use JS click to bypass styled overlays (download buttons, etc.)
            driver.execute_script("arguments[0].click();", best_match)
        else:
            # Fallback: click the first radio button
            if radio_buttons:
                driver.execute_script("arguments[0].click();", radio_buttons[0])
                logger.warning(
                    "Radio fallback: clicked first option (wanted '%s')", answer
                )

    @staticmethod
    def _fill_checkbox(driver: webdriver.Chrome, element: WebElement, answer: str) -> None:
        """Check appropriate checkbox(es) based on the answer.

        For a single checkbox (e.g., "I agree"), checks it if the answer
        is affirmative. For a group of checkboxes, finds and checks those
        matching the answer text.

        Args:
            driver: The Selenium Chrome webdriver instance.
            element: One of the checkbox WebElements.
            answer: The desired answer text (may contain multiple values
                    separated by commas).
        """
        name = element.get_attribute("name") or ""
        answer_lower = answer.lower().strip()

        # Skip LinkedIn's "top choice" checkbox — it's not a screening question
        if "topchoice" in name.lower().replace(" ", "").replace("-", "").replace("_", ""):
            logger.debug("Skipping 'top choice' checkbox")
            return

        # Single checkbox case (e.g., agreement checkbox)
        if not name:
            if answer_lower in ("yes", "true", "i agree", "agree"):
                if not element.is_selected():
                    driver.execute_script("arguments[0].click();", element)
            return

        checkboxes = driver.find_elements(By.CSS_SELECTOR, f'input[type="checkbox"][name="{name}"]')

        # Single checkbox in group — treat as boolean
        if len(checkboxes) == 1:
            if answer_lower in ("yes", "true", "i agree", "agree"):
                if not element.is_selected():
                    driver.execute_script("arguments[0].click();", element)
            return

        # Multiple checkboxes — match answer parts against labels
        answer_parts = [part.strip().lower() for part in answer_lower.split(",")]

        for checkbox in checkboxes:
            label_text = ""
            cb_id = checkbox.get_attribute("id")
            if cb_id:
                try:
                    label = driver.find_element(By.CSS_SELECTOR, f'label[for="{cb_id}"]')
                    label_text = label.text.strip()
                except Exception:
                    pass

            if not label_text:
                try:
                    parent = checkbox.find_element(By.XPATH, "./..")
                    label_text = parent.text.strip()
                except Exception:
                    pass

            if label_text:
                label_lower = label_text.lower()
                for part in answer_parts:
                    if part in label_lower or label_lower in part:
                        if not checkbox.is_selected():
                            driver.execute_script("arguments[0].click();", checkbox)
                        break
