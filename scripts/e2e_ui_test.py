#!/usr/bin/env python3
"""E2E test script for OAK Streamlit Hub UI. Run with: python scripts/e2e_ui_test.py"""
import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

BASE_URL = "http://spark-5208:8501"
OUTPUT_DIR = Path(__file__).parent.parent / "e2e_screenshots"


async def main() -> dict:
    """Run E2E test and return results dict."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    results: dict = {
        "home_loaded": False,
        "problem_uuid": None,
        "pipeline_started": False,
        "container_name": None,
        "gallery_shows": None,
        "problem_detail_shows": None,
        "errors": [],
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await context.new_page()

        try:
            # 1. Navigate to home
            await page.goto(BASE_URL, wait_until="networkidle", timeout=15000)
            await page.screenshot(path=OUTPUT_DIR / "01_home.png")
            results["home_loaded"] = True

            # 2. Navigate to Submit page via sidebar click (avoids URL routing issues)
            submit_link = page.get_by_role("link", name="Submit")
            await submit_link.wait_for(state="visible", timeout=5000)
            await submit_link.click()
            await page.wait_for_timeout(3000)  # Let Streamlit load page
            await page.screenshot(path=OUTPUT_DIR / "02_submit_before.png")

            # 3. Fill form - Streamlit: first text input = title, first textarea = description
            title_input = page.locator('input[type="text"]').first
            await title_input.wait_for(state="visible", timeout=5000)
            await title_input.fill("Iris Classification Pipeline")

            desc_input = page.locator("textarea").first
            await desc_input.fill(
                "Load the Iris dataset from sklearn, perform exploratory data analysis, "
                "train a Random Forest classifier, evaluate accuracy and create a confusion matrix, "
                "then generate a summary report as ANALYSIS_REPORT.md"
            )

            # Checkbox "Start pipeline automatically" - default is True, leave as-is
            await page.wait_for_timeout(500)  # Let form settle

            await page.screenshot(path=OUTPUT_DIR / "03_submit_filled.png")

            # 4. Click Submit Problem (JS click bypasses overlay)
            await page.evaluate(
                """() => {
                    const btn = document.querySelector('[data-testid="stBaseButton-secondaryFormSubmit"]')
                        || Array.from(document.querySelectorAll('button')).find(b => b.textContent.includes('Submit Problem'));
                    if (btn) btn.click();
                }"""
            )

            # 5. Wait for response and screenshot
            await page.wait_for_timeout(5000)  # Allow API call + pipeline start
            await page.screenshot(path=OUTPUT_DIR / "04_submit_result.png")

            # Extract success/error from page
            import re

            main_content = await page.locator("[data-testid='stAppViewContainer'], #root, body").first.text_content() or ""
            uuid_match = re.search(r"`([a-f0-9-]{8}-[a-f0-9-]{4}-[a-f0-9-]{4}-[a-f0-9-]{4}-[a-f0-9-]{12})`", main_content)
            if uuid_match:
                results["problem_uuid"] = uuid_match.group(1)
            # Fallback: extract from container name oak-harness-{uuid}
            if not results["problem_uuid"]:
                container_match = re.search(r"oak-harness-([a-f0-9-]{36})", main_content)
                if container_match:
                    results["problem_uuid"] = container_match.group(1)

            if "Problem created:" in main_content or "Pipeline started:" in main_content:
                results["pipeline_started"] = "Pipeline started:" in main_content
            container_match = re.search(r"(oak-harness-[a-f0-9-]{36})", main_content)
            if container_match:
                results["container_name"] = container_match.group(1)
                if not results["problem_uuid"]:
                    results["problem_uuid"] = container_match.group(1).replace("oak-harness-", "")

            if "error" in main_content.lower() or "failed" in main_content.lower():
                # Capture error-ish content
                for line in main_content.split("\n"):
                    if "error" in line.lower() or "failed" in line.lower() or "cannot connect" in line.lower():
                        results["errors"].append(line.strip())

            # 6. Wait 3 seconds, then navigate to Gallery
            await page.wait_for_timeout(3000)
            await page.get_by_role("link", name="Gallery").click()
            await page.wait_for_timeout(2000)
            await page.screenshot(path=OUTPUT_DIR / "05_gallery.png")

            gallery_text = await page.locator("[data-testid='stAppViewContainer'], #root").first.text_content()
            results["gallery_shows"] = (gallery_text or "")[:500] if gallery_text else ""

            # 7. Click View if available
            view_btn = page.locator('button:has-text("View")').first
            if await view_btn.count() > 0:
                await view_btn.click()
                await page.wait_for_timeout(2000)
                await page.screenshot(path=OUTPUT_DIR / "06_problem_detail.png")
                detail_text = await page.locator("[data-testid='stAppViewContainer'], #root").first.text_content()
                results["problem_detail_shows"] = (detail_text or "")[:500] if detail_text else ""

        except Exception as e:
            results["errors"].append(str(e))
            try:
                await page.screenshot(path=OUTPUT_DIR / "error.png")
            except Exception:
                pass
        finally:
            await browser.close()

    return results


if __name__ == "__main__":
    results = asyncio.run(main())

    print("\n=== E2E Test Results ===")
    print(f"Home page loaded: {results['home_loaded']}")
    print(f"Problem UUID: {results['problem_uuid']}")
    print(f"Pipeline started: {results['pipeline_started']}")
    print(f"Container name: {results['container_name']}")
    print(f"Gallery (excerpt): {results['gallery_shows'][:200] if results['gallery_shows'] else 'N/A'}...")
    print(f"Problem detail (excerpt): {results['problem_detail_shows'][:200] if results['problem_detail_shows'] else 'N/A'}...")
    if results["errors"]:
        print(f"Errors: {results['errors']}")
    print(f"\nScreenshots saved to: {OUTPUT_DIR}")

    sys.exit(0 if results["home_loaded"] and not results["errors"] else 1)
