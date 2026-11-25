"""Open the live page in headless Chromium with real ESPN data and check it renders."""
import functools
import http.server
import pathlib
import threading

from playwright.sync_api import sync_playwright

site = pathlib.Path(__file__).parent / "site"
handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(site))
srv = http.server.ThreadingHTTPServer(("127.0.0.1", 8765), handler)
threading.Thread(target=srv.serve_forever, daemon=True).start()

with sync_playwright() as p:
    b = p.chromium.launch()
    page = b.new_page(viewport={"width": 390, "height": 844})
    # ESPN refuses headless browsers, so serve the real data fetched by curl a moment ago.
    fx = pathlib.Path("/tmp/fx")

    def espn(route):
        url = route.request.url
        name = "summary.json" if "/summary" in url else url.split("/soccer/")[1].split("/")[0] + ".json"
        f = fx / name
        route.fulfill(status=200, body=f.read_text() if f.exists() else '{"events":[]}',
                      headers={"content-type": "application/json", "access-control-allow-origin": "*"})
    page.route("https://site.api.espn.com/**", espn)
    errors = []
    page.on("pageerror", lambda e: errors.append(str(e)))
    page.on("requestfailed", lambda r: print("request failed:", r.url[:100], r.failure))
    page.on("response", lambda r: print("response:", r.status, r.url[:100]) if "espn" in r.url else None)
    page.on("console", lambda m: print("console:", m.type, m.text[:200]))
    page.goto("http://127.0.0.1:8765/")
    page.wait_for_function("document.getElementById('updt').textContent !== 'Loading…'", timeout=30000)
    for label in ("Yesterday",):
        page.get_by_role("button", name=label, exact=True).click()
        page.wait_for_timeout(4000)
        cards = page.locator(".card").count()
        print(f"{label}: {cards} games, {page.locator('.league').count()} leagues, "
              f"{page.locator('.hl').count()} highlight links, status: {page.locator('#updt').text_content()}")
    page.get_by_role("button", name="Yesterday", exact=True).click()
    page.wait_for_timeout(3000)
    if page.locator(".card").count():
        page.locator(".card").first.click()
        page.wait_for_selector(".tabs", timeout=15000)
        print("match sheet:", page.locator(".big .nm").all_text_contents(), page.locator(".big .score").text_content(),
              "| events:", page.locator(".ev").count())
        page.get_by_role("button", name="Lineups").click()
        print("lineup players:", page.locator(".lu li").count())
    page.screenshot(path="live-board.png", full_page=False)
    print("page errors:", errors or "none")
    b.close()
    assert not errors, errors
