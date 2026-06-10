#!/usr/bin/env python3
"""Open via /app/transactions (All Sales) which includes ALL statuses."""
import asyncio, os


async def safe_click(loc, timeout=8000):
    try: await loc.scroll_into_view_if_needed(timeout=2000)
    except: pass
    try: await loc.click(timeout=timeout); return
    except: pass
    try: await loc.click(force=True, timeout=3000); return
    except: pass
    h = await loc.element_handle()
    if h: await h.evaluate("el => el.click()"); return


async def main():
    customer = os.environ.get("CUSTOMER", "Wachter")
    amount = os.environ.get("AMOUNT", "725.00")

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

    await page.goto("https://qbo.intuit.com/app/transactions")
    await page.wait_for_selector("table tbody tr", timeout=20000)
    await asyncio.sleep(2)
    rows = await page.query_selector_all("table tbody tr")
    print(f"All Sales view: {len(rows)} rows")

    target = None
    for r in rows:
        txt = " ".join(((await r.text_content()) or "").split())
        if customer.lower() in txt.lower() and amount in txt:
            target = r
            print(f"[open] match: {txt[:200]}")
            break
    if not target:
        print(f"[open] No row matches '{customer}' + '{amount}' in {len(rows)} rows. Dumping any Wachter rows:")
        for r in rows[:50]:
            txt = " ".join(((await r.text_content()) or "").split())
            if customer.lower() in txt.lower():
                print(f"  WACHTER: {txt[:200]}")
        return

    link = await target.query_selector("a, button[role='link']")
    if link:
        await safe_click(link)
    else:
        await safe_click(target)
    await asyncio.sleep(2)
    print(f"[open] page now: {page.url}")


if __name__ == "__main__":
    asyncio.run(main())
