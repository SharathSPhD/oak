#!/usr/bin/env python3
"""Verify completed problem in OAK Streamlit Hub. Run with: python scripts/verify_completed_problem.py"""
import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

BASE_URL = "http://spark-5208:8501"
OUTPUT_DIR = Path(__file__).parent.parent / "e2e_screenshots"
TARGET_UUID = "02525f82-8707-4554-81d5-935d3ca44f66"
TARGET_UUID_PREFIX = "02525f82"
TARGET_TITLE = "Iris Classification E2E"


async def main() -> dict:
    """Verify completed problem and return results dict."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    results: dict = {
        "gallery_shows_problem": False,
        "gallery_status_correct": False,
        "problem_detail_loaded": False,
        "files_tab_shows_outputs": False,
        "expected_files": ["ANALYSIS_REPORT.md", "PROBLEM.md", "solution.py"],
        "files_found": [],
        "logs_tab_shows_output": False,
        "errors": [],
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await context.new_page()

        try:
            # 1. Navigate to Gallery (Streamlit uses lowercase URLs)
            await page.goto(f"{BASE_URL}/gallery", wait_until="networkidle", timeout=15000)
            await page.wait_for_timeout(3000)
            await page.screenshot(path=OUTPUT_DIR / "verify_01_gallery.png")

            content = await page.locator("[data-testid='stAppViewContainer'], #root, body").first.text_content() or ""
            results["gallery_shows_problem"] = TARGET_TITLE in content and TARGET_UUID_PREFIX in content
            results["gallery_status_correct"] = "ACTIVE" in content and TARGET_TITLE in content

            # 3. Navigate directly to Problem Detail for target UUID
            await page.goto(f"{BASE_URL}/problem?id={TARGET_UUID}", wait_until="networkidle", timeout=15000)
            await page.wait_for_timeout(3000)
            await page.screenshot(path=OUTPUT_DIR / "verify_02_problem_detail.png")
            detail_content = await page.locator("[data-testid='stAppViewContainer'], #root, body").first.text_content() or ""
            results["problem_detail_loaded"] = TARGET_UUID_PREFIX in detail_content and TARGET_TITLE in detail_content

            # 4. Click Files tab
            files_tab = page.locator('button:has-text("Files"), [role="tab"]:has-text("Files")').first
            await files_tab.click(force=True)
            await page.wait_for_timeout(2000)

            await page.screenshot(path=OUTPUT_DIR / "verify_03_files_tab.png")
            files_content = await page.locator("[data-testid='stAppViewContainer'], #root, body").first.text_content() or ""
            for f in results["expected_files"]:
                if f in files_content:
                    results["files_found"].append(f)
            results["files_tab_shows_outputs"] = len(results["files_found"]) >= 3

            # 5. Click Logs tab
            logs_tab = page.locator('button:has-text("Logs"), [role="tab"]:has-text("Logs")').first
            await logs_tab.click(force=True)
            await page.wait_for_timeout(2000)

            await page.screenshot(path=OUTPUT_DIR / "verify_04_logs_tab.png")
            logs_content = await page.locator("[data-testid='stAppViewContainer'], #root, body").first.text_content() or ""
            results["logs_tab_shows_output"] = (
                "Container" in logs_content or "logs" in logs_content.lower() or "log" in logs_content.lower()
            ) and len(logs_content) > 200

        except Exception as e:
            results["errors"].append(str(e))
            try:
                await page.screenshot(path=OUTPUT_DIR / "verify_error.png")
            except Exception:
                pass
        finally:
            await browser.close()

    return results


if __name__ == "__main__":
    results = asyncio.run(main())

    print("\n=== Verification Results ===")
    print(f"Gallery shows problem with correct status: {results['gallery_shows_problem']} (ACTIVE: {results['gallery_status_correct']})")
    print(f"Problem Detail page loaded: {results['problem_detail_loaded']}")
    print(f"Files tab shows 3 output files: {results['files_tab_shows_outputs']} (found: {results['files_found']})")
    print(f"Logs tab shows container output: {results['logs_tab_shows_output']}")
    if results["errors"]:
        print(f"Errors: {results['errors']}")
    print(f"\nScreenshots saved to: {OUTPUT_DIR}")

    sys.exit(0 if not results["errors"] else 1)
