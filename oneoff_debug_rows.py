#!/usr/bin/env python3
"""Dump first 5 invoice rows for debugging."""
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
    await page.goto("https://qbo.intuit.com/app/invoices")
    await page.wait_for_selector("table tbody tr", timeout=15000)
    await asyncio.sleep(2)

    rows = await page.query_selector_all("table tbody tr")
    print(f"Total rows: {len(rows)}")
    for i, r in enumerate(rows[:6]):
        txt = (await r.text_content()) or ""
        # Collapse whitespace
        txt = " ".join(txt.split())
        print(f"[{i}] {txt[:200]}")


if __name__ == "__main__":
    asyncio.run(main())
