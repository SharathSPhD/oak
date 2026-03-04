"""Final demo screenshots showing live system state."""

from pathlib import Path
from playwright.sync_api import sync_playwright

BASE = "http://spark-5208:8501"
OUT = Path("/home/sharaths/projects/oak/demo_screenshots")


def main():
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(viewport={"width": 1440, "height": 900})
        page = ctx.new_page()

        page.goto(f"{BASE}/", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)
        page.screenshot(path=str(OUT / "11_final_dashboard.png"), full_page=True)
        print("Dashboard: saved")

        page.goto(f"{BASE}/gallery", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)
        page.screenshot(path=str(OUT / "12_final_gallery.png"), full_page=True)
        print("Gallery: saved")

        page.goto(f"{BASE}/telemetry", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)
        page.screenshot(path=str(OUT / "13_final_telemetry.png"), full_page=True)
        print("Telemetry: saved")

        page.goto(f"{BASE}/settings", wait_until="networkidle", timeout=30000)
        page.wait_for_timeout(3000)
        page.screenshot(path=str(OUT / "14_final_settings.png"), full_page=True)
        print("Settings: saved")

        browser.close()

    shots = sorted(OUT.glob("*.png"))
    print(f"\nTotal screenshots: {len(shots)}")
    for s in shots:
        print(f"  {s.name} ({s.stat().st_size / 1024:.1f} KB)")


if __name__ == "__main__":
    main()
