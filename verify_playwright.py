"""
Phase 0 verification script — confirms Playwright can launch a browser and reach Google Maps.
Uses system-installed Chrome (channel='chrome') for local dev.
Render deployment uses playwright install chromium + launch() with no channel arg.
"""
from playwright.sync_api import sync_playwright


def verify():
    with sync_playwright() as p:
        print("Launching browser...")
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page()
        print("Navigating to Google Maps...")
        page.goto("https://www.google.com/maps", timeout=30000)
        title = page.title()
        print(f"Page title: {title}")
        browser.close()
        assert "Google Maps" in title or "Google" in title, f"Unexpected title: {title}"
        print("PASS — Playwright launched system Chrome and reached Google Maps.")


if __name__ == "__main__":
    verify()
