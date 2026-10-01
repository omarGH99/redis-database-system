"""
take_screenshots.py
--------------------
Regenerates the README / website screenshots in docs/img/.

Runs the Flask app against an in-memory fakeredis loaded with the real CSVs,
so no Redis server is needed.  Requires:

    pip install fakeredis playwright
    python -m playwright install chromium     # or have Google Chrome installed

Usage:  python scripts/take_screenshots.py
"""

import sys
import threading
import time
from pathlib import Path

import fakeredis
from playwright.sync_api import sync_playwright
from werkzeug.serving import make_server

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "img"
PORT = 5055
BASE = f"http://127.0.0.1:{PORT}"

sys.path.insert(0, str(ROOT / "app"))
sys.path.insert(0, str(ROOT / "scripts"))


def start_server():
    import load_redis
    import queries

    r = fakeredis.FakeRedis(decode_responses=True)
    load_redis.load_all(r)
    queries.core.get_redis = lambda: r

    import app as app_module
    app_module.get_redis = queries.core.get_redis
    srv = make_server("127.0.0.1", PORT, app_module.app, threaded=True)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def launch(p):
    try:
        return p.chromium.launch(channel="chrome")
    except Exception:
        return p.chromium.launch()


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    srv = start_server()
    time.sleep(0.5)

    with sync_playwright() as p:
        browser = launch(p)
        ctx = browser.new_context(viewport={"width": 1440, "height": 900}, device_scale_factor=2)
        page = ctx.new_page()

        def shot(name, full=False):
            page.wait_for_timeout(900)           # let chart animations settle
            page.screenshot(path=str(OUT / f"{name}.png"), full_page=full)
            print("saved", name)

        # Dashboard
        page.goto(BASE + "/")
        page.wait_for_selector("#c-row_counts")
        page.wait_for_selector("#timing:not(:empty)")
        # fakeredis is pure Python, so its timing says nothing about real Redis
        page.add_style_tag(content="#timing { visibility: hidden; }")
        shot("dashboard", full=True)

        # Browse: table + row detail
        page.goto(BASE + "/browse?table=students&sort_col=gpa&sort_dir=desc")
        page.wait_for_selector("table.dt tbody tr")
        shot("browse")
        page.click("table.dt tbody tr:nth-child(1)")
        page.wait_for_selector("dialog[open]")
        shot("browse-row-detail")

        # Browse: another domain
        page.goto(BASE + "/browse?table=properties&sort_col=listed_price_usd&sort_dir=desc")
        page.wait_for_selector("table.dt tbody tr")
        shot("browse-properties")

        # Tasks: multi-condition search
        page.goto(BASE + "/tasks")
        page.wait_for_selector(".tbtn")
        page.click('.tbtn[data-n="06"]')
        page.click("text=▶ Run")
        page.wait_for_selector("#outpanel", state="visible")
        shot("tasks")

        # Query (natural language)
        page.goto(BASE + "/ask?q=" + "students with GPA above 3.9")
        page.wait_for_selector("#result table")
        # hide the long pattern reference so the answer is the focus
        page.add_style_tag(content=".panel.mt16 { display: none; }")
        # drop the fakeredis timing (not representative of a real Redis server)
        page.evaluate("""() => { const r = document.querySelector('#result');
            r.innerHTML = r.innerHTML.replace(/&nbsp;·&nbsp; answered in <span[^>]*>[^<]*<\/span>/, ''); }""")
        shot("ask")

        # Mobile dashboard
        mob = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2,
                                  is_mobile=True)
        mp = mob.new_page()
        mp.goto(BASE + "/")
        mp.wait_for_selector("#c-row_counts")
        mp.wait_for_timeout(1200)
        mp.screenshot(path=str(OUT / "dashboard-mobile.png"))
        print("saved dashboard-mobile")

        browser.close()
    srv.shutdown()


if __name__ == "__main__":
    main()
