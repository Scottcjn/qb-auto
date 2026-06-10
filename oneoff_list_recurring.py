#!/usr/bin/env python3
"""List recurring transactions in QBO. Read-only."""
import asyncio


async def main():
    from playwright.async_api import async_playwright
    pw = await async_playwright().start()
    browser = await pw.chromium.connect_over_cdp("http://127.0.0.1:9222", timeout=5000)
    ctx = browser.contexts[0]
    page = None
    for p in ctx.pages:
        if "intuit.com" in p.url or "qbo" in p.url:
            page = p; break
    if page is None:
        page = ctx.pages[0] if ctx.pages else await ctx.new_page()

    await page.goto("https://qbo.intuit.com/app/recurringtransactions")
    # Wait for either a table row or "no data" message
    try:
        await page.wait_for_selector("table tbody tr, [class*='empty'], [class*='zero']", timeout=20000)
    except Exception:
        pass
    await asyncio.sleep(2)
    print(f"URL: {page.url}")
    print(f"Title: {await page.title()}")

    rows = await page.query_selector_all("table tbody tr")
    print(f"\n=== {len(rows)} recurring template rows ===\n")
    for i, r in enumerate(rows):
        txt = " ".join(((await r.text_content()) or "").split())
        print(f"[{i+1}] {txt[:250]}")
    if not rows:
        # Try a broader probe
        body = await page.content()
        if "empty" in body.lower() or "no recurring" in body.lower():
            print("(page appears to indicate no recurring transactions)")
        else:
            print("(no table rows found — UI may use a different element)")


if __name__ == "__main__":
    asyncio.run(main())
