"""Browser automation for job application forms using Playwright."""

import logging
import os
import random
import time

logger = logging.getLogger(__name__)

try:
    from playwright.sync_api import sync_playwright

    PLAYWRIGHT_AVAILABLE = True
except ImportError:
    PLAYWRIGHT_AVAILABLE = False


def detect_platform(page):
    """Return the ATS platform name based on URL and page content.

    Returns one of: "greenhouse", "lever", "workday", "custom".
    """
    url = page.url.lower()
    html = page.content().lower()

    if "greenhouse" in url or "application-form" in html:
        return "greenhouse"
    if "lever.co" in url or "data-apply" in html:
        return "lever"
    if "workday" in url or "workday" in html:
        return "workday"
    return "custom"


def parse_form_fields(page):
    """Find all visible form inputs and return their metadata.

    Returns a list of dicts with keys: selector, type, label, name, placeholder.
    """
    selectors = [
        "input[type=text]",
        "input[type=email]",
        "input[type=tel]",
        "input[type=url]",
        "input[type=file]",
        "textarea",
        "select",
    ]
    fields = []

    for sel in selectors:
        elements = page.query_selector_all(sel)
        for el in elements:
            if not el.is_visible():
                continue

            field_type = el.get_attribute("type") or el.evaluate("e => e.tagName.toLowerCase()")
            field_name = el.get_attribute("name") or ""
            field_id = el.get_attribute("id") or ""
            placeholder = el.get_attribute("placeholder") or ""

            label = _find_label(page, el, field_id)

            # Build a unique CSS selector for this element
            if field_id:
                css = "#" + field_id
            elif field_name:
                tag = el.evaluate("e => e.tagName.toLowerCase()")
                css = f'{tag}[name="{field_name}"]'
            else:
                css = sel

            fields.append({
                "selector": css,
                "type": field_type,
                "label": label,
                "name": field_name,
                "placeholder": placeholder,
            })

    return fields


def _find_label(page, element, field_id):
    """Try several heuristics to locate the label text for a form element."""
    # a. label[for=<id>]
    if field_id:
        label_el = page.query_selector(f'label[for="{field_id}"]')
        if label_el:
            text = label_el.inner_text().strip()
            if text:
                return text

    # b. Closest ancestor label
    ancestor_text = element.evaluate(
        "e => { let p = e.closest('label'); return p ? p.innerText.trim() : ''; }"
    )
    if ancestor_text:
        return ancestor_text

    # c. Preceding text/label element
    prev_text = element.evaluate(
        "e => { let p = e.previousElementSibling; return p ? p.innerText.trim() : ''; }"
    )
    if prev_text:
        return prev_text

    # d. Placeholder attribute
    return element.get_attribute("placeholder") or ""


_FIELD_RULES = [
    (["first name"], lambda p: p.get("name", "").split()[0] if p.get("name") else ""),
    (["last name", "surname"], lambda p: p.get("name", "").split()[-1] if p.get("name") and " " in p.get("name", "") else ""),
    (["name", "full name"], lambda p: p.get("name", "")),
    (["email", "e-mail"], lambda p: p.get("email", "")),
    (["phone", "mobile", "telephone"], lambda p: p.get("phone", "")),
    (["linkedin"], lambda p: p.get("linkedin", "")),
    (["location", "city", "address"], lambda p: p.get("location", "")),
    (["graduation", "grad date"], lambda p: p.get("graduation_date", "")),
    (["university", "school", "college"], lambda p: p.get("degree", "")),
    (["gpa", "cgpa"], lambda p: p.get("cgpa", "")),
]


def map_fields_to_profile(fields, profile):
    """Map form field selectors to profile values using label/name/placeholder matching.

    Returns a dict of {selector: value}.
    """
    mapping = {}

    for field in fields:
        if field["type"] == "file":
            continue

        combined = " ".join([
            field["label"],
            field["name"],
            field["placeholder"],
        ]).lower()

        for keywords, extractor in _FIELD_RULES:
            if any(kw in combined for kw in keywords):
                value = extractor(profile)
                if value:
                    mapping[field["selector"]] = str(value)
                break

    return mapping


def fill_form(page, field_mapping, random_delay_min_ms=200, random_delay_max_ms=1200):
    """Fill form fields from the selector→value mapping with random delays.

    Returns a list of result dicts with keys: selector, status, error.
    """
    results = []

    for selector, value in field_mapping.items():
        delay_s = random.randint(random_delay_min_ms, random_delay_max_ms) / 1000.0
        time.sleep(delay_s)

        try:
            page.fill(selector, value)
            logger.info("Filled %s", selector)
            results.append({"selector": selector, "status": "filled", "error": None})
        except Exception as exc:
            logger.error("Failed to fill %s: %s", selector, exc)
            results.append({"selector": selector, "status": "failed", "error": str(exc)})

    return results


def upload_resume(page, resume_path):
    """Upload a resume file via the first visible file input.

    Returns True on success, False on failure.
    """
    try:
        file_input = page.query_selector('input[type="file"]')
        if not file_input:
            logger.warning("No file input found on page")
            return False
        file_input.set_input_files(resume_path)
        logger.info("Uploaded resume: %s", resume_path)
        return True
    except Exception as exc:
        logger.error("Resume upload failed: %s", exc)
        return False


def fill_cover_text(page, cover_text):
    """Fill a cover-letter / additional-info textarea with the given text.

    Returns True on success, False on failure.
    """
    keywords = ["cover", "letter", "why", "additional", "message"]

    try:
        for ta in page.query_selector_all("textarea"):
            if not ta.is_visible():
                continue

            ta_id = ta.get_attribute("id") or ""
            ta_name = ta.get_attribute("name") or ""
            ta_placeholder = ta.get_attribute("placeholder") or ""

            label_text = _find_label(page, ta, ta_id)

            combined = " ".join([label_text, ta_name, ta_placeholder]).lower()

            if any(kw in combined for kw in keywords):
                ta.fill(cover_text)
                logger.info("Filled cover text in textarea (id=%s, name=%s)", ta_id, ta_name)
                return True

        logger.warning("No matching cover-letter textarea found")
        return False
    except Exception as exc:
        logger.error("Failed to fill cover text: %s", exc)
        return False


def take_screenshot(page, screenshot_dir="/tmp/screenshots"):
    """Take a full-page screenshot and return the file path."""
    os.makedirs(screenshot_dir, exist_ok=True)
    timestamp = int(time.time() * 1000)
    path = os.path.join(screenshot_dir, f"screenshot_{timestamp}.png")
    page.screenshot(path=path, full_page=True)
    logger.info("Screenshot saved: %s", path)
    return path


def prepare_application(apply_link, resume_path, cover_text, profile, config):
    """Orchestrate a single job application via Playwright.

    Launches a browser, navigates to the apply link, detects the platform,
    parses and fills the form, uploads the resume, fills cover text, and
    takes a screenshot.  The browser is left open for manual review/submit.

    Returns a result dict with keys: platform, fields_filled, screenshot_path, status.
    """
    if not PLAYWRIGHT_AVAILABLE:
        raise ImportError(
            "Playwright is not installed. Install it with: pip install playwright && python -m playwright install"
        )

    delay_min = config.get("random_delay_min_ms", 200)
    delay_max = config.get("random_delay_max_ms", 1200)
    screenshot_dir = config.get("screenshot_dir", "/tmp/screenshots")
    browser_profile_dir = config.get("browser_profile_dir", "")

    pw = sync_playwright().start()
    context = None
    try:
        context = pw.chromium.launch_persistent_context(
            browser_profile_dir,
            headless=False,
        )
        page = context.new_page()
        page.goto(apply_link, wait_until="domcontentloaded")

        platform = detect_platform(page)
        logger.info("Detected platform: %s", platform)

        fields = parse_form_fields(page)
        logger.info("Found %d form fields", len(fields))

        field_mapping = map_fields_to_profile(fields, profile)
        filled = fill_form(page, field_mapping, delay_min, delay_max)

        upload_resume(page, resume_path)
        fill_cover_text(page, cover_text)

        screenshot_path = take_screenshot(page, screenshot_dir)

        # Browser left open intentionally for manual review/submit.
        return {
            "platform": platform,
            "fields_filled": filled,
            "screenshot_path": screenshot_path,
            "status": "ready_for_submit",
        }
    except Exception as exc:
        logger.error("prepare_application failed: %s", exc)
        if context:
            context.close()
        pw.stop()
        return {
            "platform": "unknown",
            "fields_filled": [],
            "screenshot_path": "",
            "status": "failed",
            "error": str(exc),
        }
