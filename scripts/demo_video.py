"""OAK E2E Demo with Playwright video recording and screenshots.

Navigates the React Hub, submits a problem, waits for completion,
and showcases the inline file viewer. Records everything as a .webm video.

Usage: python3 scripts/demo_video.py
"""
import time
import json
import sys
from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://localhost:8501"
API = "http://localhost:8000"
OUT = Path(__file__).resolve().parent.parent / "demo_video"
OUT.mkdir(exist_ok=True)

PROBLEM_TITLE = "Wine Quality Analysis"
PROBLEM_DESC = (
    "Analyze the Wine Quality dataset (use sklearn.datasets or generate synthetic wine data). "
    "Perform EDA with descriptive statistics and correlation analysis. "
    "Train a Random Forest classifier to predict wine quality. "
    "Evaluate with accuracy, classification report, and confusion matrix. "
    "Generate ANALYSIS_REPORT.md with all findings."
)


def screenshot(page, name):
    path = OUT / f"{name}.png"
    page.screenshot(path=str(path), full_page=True)
    print(f"  [screenshot] {name}.png")


def run():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        ctx = browser.new_context(
            viewport={"width": 1440, "height": 900},
            record_video_dir=str(OUT),
            record_video_size={"width": 1440, "height": 900},
        )
        page = ctx.new_page()

        # -- 1. Dashboard --
        print("[1/7] Dashboard")
        page.goto(BASE, wait_until="networkidle")
        page.wait_for_timeout(2000)
        screenshot(page, "01_dashboard")

        # -- 2. Submit Problem --
        print("[2/7] Submit Problem")
        page.click('a[href="/submit"]')
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1000)
        screenshot(page, "02_submit_empty")

        page.fill('input[placeholder*="title" i], input[name="title"], input[type="text"]', PROBLEM_TITLE)
        page.fill('textarea', PROBLEM_DESC)
        page.wait_for_timeout(500)
        screenshot(page, "03_submit_filled")

        page.click('button:has-text("Submit")')
        page.wait_for_timeout(3000)
        screenshot(page, "04_submit_result")

        # -- 3. Gallery --
        print("[3/7] Gallery")
        page.click('a[href="/gallery"]')
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        screenshot(page, "05_gallery")

        # Find the problem we just submitted and navigate to it
        problem_link = page.locator(f'text="{PROBLEM_TITLE}"').first
        if problem_link.count() > 0:
            problem_link.click()
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(2000)
        else:
            # Try via API to get the problem ID
            import urllib.request
            resp = urllib.request.urlopen(f"{API}/api/problems")
            problems = json.loads(resp.read())
            pid = None
            for prob in problems:
                if prob["title"] == PROBLEM_TITLE:
                    pid = prob["id"]
                    break
            if pid:
                page.goto(f"{BASE}/problems/{pid}", wait_until="networkidle")
                page.wait_for_timeout(2000)

        screenshot(page, "06_problem_detail")

        # -- 4. Wait for pipeline to complete (poll every 15s, max 5 min) --
        print("[4/7] Waiting for pipeline completion...")
        import urllib.request
        problem_id = page.url.split("/problems/")[-1].split("?")[0] if "/problems/" in page.url else None

        if problem_id:
            deadline = time.time() + 300
            last_status = "unknown"
            while time.time() < deadline:
                try:
                    resp = urllib.request.urlopen(f"{API}/api/problems/{problem_id}")
                    data = json.loads(resp.read())
                    last_status = data.get("status", "unknown")
                    print(f"  Status: {last_status}")
                    if last_status in ("complete", "failed"):
                        break
                except Exception as e:
                    print(f"  Poll error: {e}")
                time.sleep(15)
            print(f"  Final status: {last_status}")

        # Refresh the detail page
        page.reload(wait_until="networkidle")
        page.wait_for_timeout(2000)
        screenshot(page, "07_problem_after_pipeline")

        # -- 5. Click through tabs --
        print("[5/7] Exploring tabs")

        # Tasks tab
        tasks_tab = page.locator('button:has-text("Tasks")')
        if tasks_tab.count() > 0:
            tasks_tab.click()
            page.wait_for_timeout(1500)
            screenshot(page, "08_tasks_tab")

        # Logs tab
        logs_tab = page.locator('button:has-text("Logs")')
        if logs_tab.count() > 0:
            logs_tab.click()
            page.wait_for_timeout(1500)
            screenshot(page, "09_logs_tab")

        # Files tab with inline viewer
        files_tab = page.locator('button:has-text("Files")')
        if files_tab.count() > 0:
            files_tab.click()
            page.wait_for_timeout(2000)
            screenshot(page, "10_files_tab")

            # Try to expand ANALYSIS_REPORT.md
            report_item = page.locator('text="ANALYSIS_REPORT.md"').first
            if report_item.count() > 0:
                report_item.click()
                page.wait_for_timeout(3000)
                screenshot(page, "11_report_rendered")

            # Try to expand solution.py
            solution_item = page.locator('text="solution.py"').first
            if solution_item.count() > 0:
                solution_item.click()
                page.wait_for_timeout(2000)
                screenshot(page, "12_solution_code")

        # Judge Verdicts tab
        verdicts_tab = page.locator('button:has-text("Judge")')
        if verdicts_tab.count() > 0:
            verdicts_tab.click()
            page.wait_for_timeout(1500)
            screenshot(page, "13_verdicts_tab")

        # -- 6. Other pages --
        print("[6/7] Other pages")

        page.click('a[href="/skills"]')
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)
        screenshot(page, "14_skills")

        page.click('a[href="/telemetry"]')
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)
        screenshot(page, "15_telemetry")

        page.click('a[href="/settings"]')
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(1500)
        screenshot(page, "16_settings")

        # -- 7. Final dashboard --
        print("[7/7] Final dashboard")
        page.click('a[href="/"]')
        page.wait_for_load_state("networkidle")
        page.wait_for_timeout(2000)
        screenshot(page, "17_dashboard_final")

        # Close context to finalize video
        video_path = page.video.path()
        ctx.close()
        browser.close()

        # Copy video to a known name
        import shutil
        final_video = OUT / "oak_demo.webm"
        if Path(video_path).exists():
            shutil.copy2(video_path, final_video)
            print(f"\n[DONE] Video saved: {final_video}")
            print(f"       Size: {final_video.stat().st_size / (1024*1024):.1f} MB")

    print(f"\nAll screenshots saved to: {OUT}/")
    print(f"Files: {sorted([f.name for f in OUT.iterdir()])}")


if __name__ == "__main__":
    run()
