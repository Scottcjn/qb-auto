#!/usr/bin/env python3
"""Open a QBO invoice by customer + amount match.

Usage: CUSTOMER='Wachter' AMOUNT='725.00' python3 oneoff_open_by_customer.py
"""
import asyncio, os, re


async def safe_click(loc, timeout=8000):
    try:
        await loc.scroll_into_view_if_needed(timeout=2000)
    except Exception:
        pass
    try:
        await loc.click(timeout=timeout); return
    except Exception:
        pass
    try:
        await loc.click(force=True, timeout=3000); return
    except Exception:
        pass
    h = await loc.element_handle()
    if h:
        await h.evaluate("el => el.click()"); return
    raise RuntimeError("safe_click failed")


async def main():
    customer = os.environ.get("CUSTOMER", "Wachter")
    amount = os.environ.get("AMOUNT", "")

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

    # Try to use the search/filter input at top of invoices list
    # QBO renders a textbox for filtering — try common labels
    filter_box = None
    for sel in [
        'input[placeholder*="Search" i]',
        'input[aria-label*="Search" i]',
        'input[aria-label*="filter" i]',
        'input[type="search"]',
    ]:
        try:
            el = await page.query_selector(sel)
            if el:
                filter_box = el
                print(f"[open] filter selector matched: {sel}")
                break
        except Exception:
            pass

    if filter_box:
        await filter_box.click()
        await page.keyboard.press("Control+a")
        await filter_box.fill(customer)
        await asyncio.sleep(1.5)

    rows = await page.query_selector_all("table tbody tr")
    print(f"[open] {len(rows)} rows visible after filter")

    target = None
    target_text = ""
    for r in rows:
        txt = " ".join(((await r.text_content()) or "").split())
        if customer.lower() in txt.lower() and (not amount or amount in txt):
            target = r
            target_text = txt
            break
    if not target:
        print(f"[open] no row matches customer='{customer}' amount='{amount}'")
        print("[open] dumping first 10 rows for inspection:")
        for i, r in enumerate(rows[:10]):
            print(f"  [{i}] {' '.join(((await r.text_content()) or '').split())[:160]}")
        return

    print(f"[open] match: {target_text[:180]}")
    link = await target.query_selector("a, button[role='link']")
    if link:
        await safe_click(link)
    else:
        await safe_click(target)
    await asyncio.sleep(2)
    print(f"[open] page now: {page.url}")


if __name__ == "__main__":
    asyncio.run(main())
