#!/usr/bin/env python3
"""Open a QBO invoice in the existing Chrome by matching its description.

Usage: SEARCH='1269994' python3 oneoff_open_invoice.py
"""
import asyncio, os, re


async def main():
    needle = os.environ.get("SEARCH", "").strip()
    if not needle:
        raise SystemExit("set SEARCH= to the substring to find")

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

    await page.goto("https://qbo.intuit.com/app/invoices")
    await page.wait_for_selector("table tbody tr", timeout=15000)
    await asyncio.sleep(1.5)

    # Pull all rows and find one whose text contains the needle
    rows = await page.query_selector_all("table tbody tr")
    print(f"[open] {len(rows)} rows scanned")
    target = None
    for r in rows:
        txt = (await r.text_content()) or ""
        if needle in txt:
            target = r
            print(f"[open] match: {txt[:120]}")
            break
    if not target:
        print(f"[open] NO ROW matches '{needle}'. Try a different substring (date/amount).")
        return

    # Click the first link-like element in the row (usually invoice number)
    link = await target.query_selector("a, button[role='link']")
    if not link:
        # Fallback: click the row
        await target.click(force=True)
    else:
        await link.click(force=True)
    await asyncio.sleep(1.5)
    print(f"[open] opened — page now: {page.url}")


if __name__ == "__main__":
    asyncio.run(main())
