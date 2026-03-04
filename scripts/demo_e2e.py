"""E2E browser demo of OAK React Hub UI using Playwright."""

import time
import json
from pathlib import Path
from playwright.sync_api import sync_playwright, Page

BASE = "http://spark-5208:8501"
OUT = Path("/home/sharaths/projects/oak/demo_screenshots")
OUT.mkdir(parents=True, exist_ok=True)

results: list[dict] = []


def step(page: Page, name: str, url: str, filename: str, wait_ms: int = 3000):
    """Navigate to a URL, wait, screenshot, and record the result."""
    print(f"\n{'='*60}")
    print(f"STEP: {name}")
    print(f"  URL: {url}")
    page.goto(url, wait_until="networkidle", timeout=30000)
    page.wait_for_timeout(wait_ms)
    path = OUT / filename
    page.screenshot(path=str(path), full_page=True)
    title = page.title()
    print(f"  Title: {title}")
    print(f"  Screenshot: {path}")
    results.append({"step": name, "url": url, "title": title, "screenshot": str(path), "ok": True})
    return path


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()

        # 1) Dashboard
        step(page, "Dashboard", f"{BASE}/", "01_dashboard.png")
        health_el = page.query_selector("text=healthy")
        if health_el:
            print("  Health: healthy indicator found")
        else:
            print("  Health: checking indicator state...")
            page.wait_for_timeout(5000)
            page.screenshot(path=str(OUT / "01_dashboard_retry.png"), full_page=True)

        # 2) Submit Problem - empty form
        step(page, "Submit (empty)", f"{BASE}/submit", "02_submit_empty.png")

        # Fill in the form
        title_input = page.query_selector("input[type='text'], input[name='title']")
        if title_input:
            title_input.fill("Wine Quality Prediction")
        else:
            inputs = page.query_selector_all("input")
            if inputs:
                inputs[0].fill("Wine Quality Prediction")
            else:
                print("  WARNING: No title input found")

        desc_input = page.query_selector("textarea")
        if desc_input:
            desc_input.fill(
                "Load the wine quality dataset (red wine) from UCI ML Repository. "
                "Perform EDA including correlation analysis and feature distributions. "
                "Train a gradient boosting classifier to predict wine quality ratings. "
                "Evaluate with accuracy, F1-score, and confusion matrix. "
                "Generate ANALYSIS_REPORT.md with findings and MODEL_REPORT.md with model details."
            )

        page.wait_for_timeout(500)
        page.screenshot(path=str(OUT / "03_submit_filled.png"), full_page=True)
        print(f"  Screenshot: {OUT}/03_submit_filled.png")

        # Click submit button
        submit_btn = page.query_selector("button[type='submit']")
        if not submit_btn:
            submit_btn = page.query_selector("button:has-text('Create'), button:has-text('Submit')")
        if submit_btn:
            submit_btn.click()
            page.wait_for_timeout(3000)
            page.screenshot(path=str(OUT / "04_submit_result.png"), full_page=True)
            print(f"  Screenshot: {OUT}/04_submit_result.png")
            results.append({"step": "Submit (filled)", "screenshot": str(OUT / "03_submit_filled.png"), "ok": True})
            results.append({"step": "Submit (result)", "screenshot": str(OUT / "04_submit_result.png"), "ok": True})
        else:
            print("  WARNING: Submit button not found")

        # 3) Gallery
        step(page, "Gallery", f"{BASE}/gallery", "05_gallery.png")

        # Try cleanup button
        cleanup_btn = page.query_selector("button:has-text('Clean'), button:has-text('Cleanup')")
        if cleanup_btn:
            cleanup_btn.click()
            page.wait_for_timeout(2000)
            page.screenshot(path=str(OUT / "06_gallery_cleanup.png"), full_page=True)
            print(f"  Screenshot: {OUT}/06_gallery_cleanup.png")

        # Click first problem link
        problem_link = page.query_selector("a[href*='/problems/']")
        if problem_link:
            problem_link.click()
            page.wait_for_timeout(3000)
            page.screenshot(path=str(OUT / "07_problem_detail.png"), full_page=True)
            results.append({"step": "Problem Detail", "screenshot": str(OUT / "07_problem_detail.png"), "ok": True})
            print(f"  Screenshot: {OUT}/07_problem_detail.png")

            # Click tabs if available
            for tab_name in ["Tasks", "Files", "Logs"]:
                tab = page.query_selector(f"button:has-text('{tab_name}')")
                if tab:
                    tab.click()
                    page.wait_for_timeout(1500)
                    fname = f"07_{tab_name.lower()}_tab.png"
                    page.screenshot(path=str(OUT / fname), full_page=True)
                    print(f"  Tab {tab_name}: {OUT}/{fname}")

        # 5) Skills
        step(page, "Skills", f"{BASE}/skills", "08_skills.png")

        # 6) Telemetry
        step(page, "Telemetry", f"{BASE}/telemetry", "09_telemetry.png")

        # 7) Settings
        step(page, "Settings", f"{BASE}/settings", "10_settings.png")

        browser.close()

    # Summary
    print(f"\n{'='*60}")
    print("DEMO SUMMARY")
    print(f"{'='*60}")
    for r in results:
        status = "OK" if r.get("ok") else "FAIL"
        print(f"  [{status}] {r['step']}: {r.get('screenshot', 'N/A')}")

    screenshots = list(OUT.glob("*.png"))
    print(f"\nTotal screenshots: {len(screenshots)}")
    for s in sorted(screenshots):
        print(f"  {s.name} ({s.stat().st_size / 1024:.1f} KB)")

    print("\nDEMO COMPLETE")


if __name__ == "__main__":
    main()
