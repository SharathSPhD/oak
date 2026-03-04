#!/usr/bin/env python3
"""E2E demo of OAK Hub React UI. Run with: python scripts/demo_react_ui.py"""
import asyncio
import sys
from pathlib import Path

from playwright.async_api import async_playwright

BASE_URL = "http://spark-5208:8501"
OUTPUT_DIR = Path("/home/sharaths/projects/oak/demo_screenshots")


async def main() -> dict:
    """Run demo and return results dict."""
    OUTPUT_DIR.mkdir(exist_ok=True)
    results: dict = {
        "pages_loaded": [],
        "pages_with_errors": [],
        "screenshots_saved": [],
        "bugs": [],
    }

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={"width": 1280, "height": 900})
        page = await context.new_page()

        def save_screenshot(name: str) -> bool:
            path = OUTPUT_DIR / name
            try:
                page.screenshot(path=path)
                results["screenshots_saved"].append(str(path))
                return True
            except Exception as e:
                results["bugs"].append(f"Screenshot {name}: {e}")
                return False

        async def save_screenshot_async(name: str) -> bool:
            path = OUTPUT_DIR / name
            try:
                await page.screenshot(path=path)
                results["screenshots_saved"].append(str(path))
                return True
            except Exception as e:
                results["bugs"].append(f"Screenshot {name}: {e}")
                return False

        try:
            # 1. Dashboard
            await page.goto(BASE_URL, wait_until="networkidle", timeout=15000)
            await page.wait_for_timeout(2000)
            await save_screenshot_async("01_dashboard.png")
            content = await page.content()
            checks = {
                "OAK Hub": "OAK Hub" in content or "OAK" in content,
                "Dashboard": "Dashboard" in content,
                "Total Problems": "Total Problems" in content,
                "Completed": "Completed" in content,
                "Active Agents": "Active Agents" in content,
                "Models": "Models" in content,
                "Submit Problem": "Submit Problem" in content,
                "View Gallery": "View Gallery" in content,
                "Telemetry": "Telemetry" in content,
            }
            if all(checks.values()):
                results["pages_loaded"].append("Dashboard")
            else:
                results["pages_with_errors"].append(f"Dashboard: missing {[k for k,v in checks.items() if not v]}")
            health = "System Healthy" in content or "System Unreachable" in content
            results["health_status"] = "Healthy" if "System Healthy" in content else ("Unreachable" if "System Unreachable" in content else "Unknown")

            # 2. Submit page - empty form
            await page.goto(f"{BASE_URL}/submit", wait_until="networkidle", timeout=15000)
            await page.wait_for_timeout(2000)
            await save_screenshot_async("02_submit_empty.png")
            if "Submit a Problem" in await page.content():
                results["pages_loaded"].append("Submit (empty)")

            # 3. Fill form
            await page.fill('input[id="title"]', "Wine Quality Prediction")
            await page.fill(
                'textarea[id="desc"]',
                "Load the wine quality dataset (red wine) from UCI ML Repository. "
                "Perform EDA including correlation analysis and feature distributions. "
                "Train a gradient boosting classifier to predict wine quality ratings. "
                "Evaluate with accuracy, F1-score, and confusion matrix. "
                "Generate ANALYSIS_REPORT.md with findings and MODEL_REPORT.md with model details.",
            )
            await page.wait_for_timeout(500)
            await save_screenshot_async("03_submit_filled.png")

            # 4. Submit
            await page.click('button[type="submit"]:has-text("Submit")')
            await page.wait_for_timeout(8000)  # Creating + uploading + starting
            await save_screenshot_async("04_submit_result.png")
            submit_content = await page.content()
            if "Problem created successfully" in submit_content or "Redirecting" in submit_content:
                results["pages_loaded"].append("Submit (result)")
            elif "error" in submit_content.lower() or "failed" in submit_content.lower():
                results["pages_with_errors"].append("Submit: creation may have failed")

            # 5. Gallery
            await page.goto(f"{BASE_URL}/gallery", wait_until="networkidle", timeout=15000)
            await page.wait_for_timeout(2000)
            await save_screenshot_async("05_gallery.png")
            if "Problem Gallery" in await page.content():
                results["pages_loaded"].append("Gallery")

            # 6. Clean Stale button
            clean_btn = page.locator('button:has-text("Clean Stale")')
            if await clean_btn.count() > 0:
                await clean_btn.click()
                await page.wait_for_timeout(3000)
                await save_screenshot_async("06_gallery_cleanup.png")

            # 7. Problem detail - click first problem link
            problem_link = page.locator('a[href^="/problems/"]').first
            if await problem_link.count() > 0:
                await problem_link.click()
                await page.wait_for_timeout(3000)
                await save_screenshot_async("07_problem_detail.png")
                if "Tasks" in await page.content():
                    results["pages_loaded"].append("Problem Detail")

                # Click through tabs
                for tab_name in ["Tasks", "Logs", "Files"]:
                    tab = page.locator(f'button:has-text("{tab_name}"), [role="tab"]:has-text("{tab_name}")').first
                    if await tab.count() > 0:
                        await tab.click(force=True)
                        await page.wait_for_timeout(1000)
                        await save_screenshot_async(f"07_problem_detail_{tab_name.lower()}.png")

            # 8. Skills
            await page.goto(f"{BASE_URL}/skills", wait_until="networkidle", timeout=15000)
            await page.wait_for_timeout(2000)
            await save_screenshot_async("08_skills.png")
            if "skills" in (await page.content()).lower():
                results["pages_loaded"].append("Skills")

            # 9. Telemetry
            await page.goto(f"{BASE_URL}/telemetry", wait_until="networkidle", timeout=15000)
            await page.wait_for_timeout(2000)
            await save_screenshot_async("09_telemetry.png")
            if "telemetry" in (await page.content()).lower() or "Telemetry" in await page.content():
                results["pages_loaded"].append("Telemetry")

            # 10. Settings
            await page.goto(f"{BASE_URL}/settings", wait_until="networkidle", timeout=15000)
            await page.wait_for_timeout(2000)
            await save_screenshot_async("10_settings.png")
            if "settings" in (await page.content()).lower() or "Settings" in await page.content():
                results["pages_loaded"].append("Settings")
            else:
                results["pages_with_errors"].append("Settings: page may not exist or failed to load")

        except Exception as e:
            results["bugs"].append(str(e))
            try:
                await page.screenshot(path=OUTPUT_DIR / "error.png")
                results["screenshots_saved"].append(str(OUTPUT_DIR / "error.png"))
            except Exception:
                pass
        finally:
            await browser.close()

    return results


if __name__ == "__main__":
    results = asyncio.run(main())

    print("\n=== OAK Hub React UI Demo Results ===")
    print(f"Pages loaded successfully: {results['pages_loaded']}")
    print(f"Pages with errors: {results['pages_with_errors']}")
    print(f"Screenshots saved: {len(results['screenshots_saved'])} files")
    for p in results["screenshots_saved"]:
        print(f"  - {p}")
    if results.get("health_status"):
        print(f"System health: {results['health_status']}")
    if results["bugs"]:
        print(f"Bugs/errors: {results['bugs']}")
    print(f"\nOutput directory: {OUTPUT_DIR}")

    sys.exit(0 if not results["bugs"] else 1)
