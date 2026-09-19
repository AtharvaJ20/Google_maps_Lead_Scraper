"""
Google Maps scraper — Playwright headless automation.

Local dev: tries system Chrome first (channel="chrome"), falls back to
playwright-installed Chromium if Chrome is not found.
Render / CI: playwright installs Chromium via build command; channel arg is
skipped automatically by the fallback branch.

Selectors use aria-label and data-item-id attributes, which are significantly
more stable than Google Maps' obfuscated CSS class names.
"""
from __future__ import annotations

import os
import random
import re
import time
import urllib.parse

# On Render, the build cache (/opt/render/.cache) is not mounted at runtime.
# Point Playwright to a path inside the project source that IS deployed.
if os.environ.get("RENDER"):
    os.environ.setdefault(
        "PLAYWRIGHT_BROWSERS_PATH", "/opt/render/project/src"
    )

from playwright.sync_api import Browser, Page, sync_playwright
from playwright.sync_api import TimeoutError as PWTimeout


# ── Typed exceptions (caught by app.py) ───────────────────────────────────────

class ScraperError(Exception):
    """Base — all scraper errors that the API layer handles."""


class NoResultsError(ScraperError):
    pass


class BlockedError(ScraperError):
    pass


# ── Constants ──────────────────────────────────────────────────────────────────

COLUMNS = ["name", "address", "phone", "website", "rating", "reviews"]
MAX_RESULTS = 20
DELAY_MIN   = 0.5   # seconds between place visits
DELAY_MAX   = 1.2


# ── Public entry point ─────────────────────────────────────────────────────────

def scrape(category: str, location: str) -> list[dict]:
    """
    Scrape Google Maps and return up to MAX_RESULTS business records.

    Each record is a dict with keys: name, address, phone, website, rating, reviews.
    All values are strings; missing fields are empty strings.

    Raises:
        NoResultsError: zero results or page failed to load results panel.
        BlockedError:   Google served a CAPTCHA or blocking page.
    """
    query = f"{category} in {location}"

    with sync_playwright() as pw:
        browser = _launch_browser(pw)
        try:
            return _run(browser, query)
        finally:
            browser.close()


# ── Browser launch ─────────────────────────────────────────────────────────────

def _launch_browser(pw) -> Browser:
    common = {
        "headless": True,
        "args": [
            "--no-sandbox",
            "--disable-dev-shm-usage",
            "--disable-gpu",
            # Memory-reduction flags for Render free tier (512 MB RAM)
            "--disable-extensions",
            "--disable-background-networking",
            "--disable-sync",
            "--disable-translate",
            "--no-first-run",
            "--disable-default-apps",
            "--disable-client-side-phishing-detection",
            "--js-flags=--max-old-space-size=128",
        ],
    }
    try:
        return pw.chromium.launch(channel="chrome", **common)
    except Exception:
        # Render: playwright install chromium runs in the build step
        return pw.chromium.launch(**common)


# ── Core flow ──────────────────────────────────────────────────────────────────

def _run(browser: Browser, query: str) -> list[dict]:
    ctx = browser.new_context(
        viewport={"width": 1280, "height": 800},
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        locale="en-US",
    )
    page = ctx.new_page()

    # 1. Load search results
    encoded = urllib.parse.quote_plus(query)
    page.goto(
        f"https://www.google.com/maps/search/{encoded}",
        timeout=30_000,
        wait_until="domcontentloaded",
    )
    _dismiss_consent(page)

    if _is_blocked(page):
        raise BlockedError(
            "Google is temporarily blocking automated requests. "
            "Please wait a few minutes and try again."
        )

    # 2. Wait for results feed
    try:
        page.wait_for_selector('[role="feed"]', timeout=15_000)
    except PWTimeout:
        raise NoResultsError(f"No results found for \"{query}\".")

    # 3. Scroll the feed to load more results
    _scroll_feed(page, target=MAX_RESULTS)

    # 4. Collect unique place hrefs from the feed
    hrefs = _collect_hrefs(page)
    if not hrefs:
        raise NoResultsError(f"No results found for \"{query}\".")
    hrefs = hrefs[:MAX_RESULTS]

    # 5. Visit each place and extract data
    results: list[dict] = []
    for href in hrefs:
        try:
            row = _scrape_place(page, href)
            if row.get("name"):
                results.append(row)
        except Exception:
            pass
        finally:
            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

    if not results:
        raise NoResultsError(f"Could not extract data for \"{query}\".")

    return results


# ── Feed helpers ───────────────────────────────────────────────────────────────

def _scroll_feed(page: Page, target: int) -> None:
    """Scroll the results sidebar until we have `target` place links or reach the end."""
    for _ in range(25):
        found = len(page.query_selector_all('[role="feed"] a[href*="/maps/place/"]'))
        if found >= target:
            break
        # Scroll the feed div, not the outer window
        page.evaluate(
            "const f = document.querySelector('[role=\"feed\"]');"
            "if (f) f.scrollTop += 600;"
        )
        time.sleep(0.6)
        # Some versions show an explicit "end of list" marker
        end_marker = page.query_selector(
            'span[aria-label*="end of list" i], [class*="HlvSq"]'
        )
        if end_marker:
            break


def _collect_hrefs(page: Page) -> list[str]:
    """Return deduplicated place hrefs from the loaded feed."""
    els = page.query_selector_all('[role="feed"] a[href*="/maps/place/"]')
    seen: set[str] = set()
    hrefs: list[str] = []
    for el in els:
        href = el.get_attribute("href") or ""
        if href and href not in seen:
            seen.add(href)
            hrefs.append(href)
    return hrefs


# ── Place detail extraction ────────────────────────────────────────────────────

def _scrape_place(page: Page, href: str) -> dict:
    """Navigate to a single place page and return its extracted fields."""
    page.goto(href, timeout=20_000, wait_until="domcontentloaded")

    # Ensure the place name has loaded
    try:
        page.wait_for_selector("h1", timeout=10_000)
    except PWTimeout:
        return {}

    row: dict = {k: "" for k in COLUMNS}

    # ── Name ──────────────────────────────────────────────────────────────────
    try:
        h1 = page.query_selector("h1")
        if h1:
            row["name"] = h1.inner_text().strip()
    except Exception:
        pass

    # ── Rating ────────────────────────────────────────────────────────────────
    # aria-label like "4.5 stars" is consistent across Google Maps versions
    try:
        el = page.query_selector('[aria-label*="stars"], [aria-label*="out of 5"]')
        if el:
            label = el.get_attribute("aria-label") or ""
            m = re.search(r"(\d+\.?\d*)\s*(?:stars?|out of)", label, re.I)
            if m:
                row["rating"] = m.group(1)
    except Exception:
        pass

    # ── Reviews ───────────────────────────────────────────────────────────────
    # aria-label like "1,234 reviews" on a button near the rating
    try:
        el = page.query_selector('[aria-label*="review" i]')
        if el:
            label = el.get_attribute("aria-label") or ""
            m = re.search(r"([\d,]+)\s+reviews?", label, re.I)
            if m:
                row["reviews"] = m.group(1).replace(",", "")
    except Exception:
        pass

    # ── Address ───────────────────────────────────────────────────────────────
    # data-item-id="address" is the most stable selector across Maps versions
    try:
        btn = page.query_selector('button[data-item-id="address"]')
        if btn:
            row["address"] = btn.inner_text().strip()
        else:
            el = page.query_selector('[aria-label^="Address:"]')
            if el:
                label = el.get_attribute("aria-label") or ""
                row["address"] = label.replace("Address:", "").strip()
    except Exception:
        pass

    # ── Phone ─────────────────────────────────────────────────────────────────
    # data-item-id starts with "phone:tel:" → value encoded in the ID
    try:
        btn = page.query_selector('button[data-item-id^="phone:tel:"]')
        if btn:
            label = btn.get_attribute("aria-label") or ""
            phone = re.sub(r"(?i)phone:?\s*", "", label).strip()
            row["phone"] = phone or btn.inner_text().strip()
        else:
            tel = page.query_selector('a[href^="tel:"]')
            if tel:
                row["phone"] = (tel.get_attribute("href") or "").replace("tel:", "").strip()
    except Exception:
        pass

    # ── Website ───────────────────────────────────────────────────────────────
    # data-item-id="authority" is Google's stable attribute for the website link
    try:
        el = page.query_selector('a[data-item-id="authority"]')
        if el:
            row["website"] = el.get_attribute("href") or ""
        else:
            el = page.query_selector('a[aria-label*="website" i][href^="http"]')
            if el:
                row["website"] = el.get_attribute("href") or ""
    except Exception:
        pass

    return row


# ── Anti-block / consent helpers ───────────────────────────────────────────────

def _dismiss_consent(page: Page) -> None:
    """Click through Google's cookie / consent banner if present."""
    for selector in (
        'button[aria-label="Accept all"]',
        'button:text("Accept all")',
        'button:text("I agree")',
        'button:text("Agree")',
        'form[action*="consent"] button[type="submit"]',
    ):
        try:
            btn = page.query_selector(selector)
            if btn and btn.is_visible():
                btn.click()
                page.wait_for_timeout(1_500)
                return
        except Exception:
            continue


def _is_blocked(page: Page) -> bool:
    """Return True if Google has served a CAPTCHA or blocking page."""
    url = page.url.lower()
    if any(s in url for s in ("sorry", "captcha", "challenge")):
        return True
    try:
        content = page.content().lower()
        return any(s in content for s in ("recaptcha", "unusual traffic", "detected unusual"))
    except Exception:
        return False
