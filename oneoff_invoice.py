#!/usr/bin/env python3
"""One-off invoice creator using the patched safe_click logic.

Reads invoice spec from $INVOICE_JSON env var, creates the invoice against
the Chrome already running on port 9222.

Usage:
  INVOICE_JSON='{"customer":"Wachter","invoice_date":"04/17/2026",...}' python3 oneoff_invoice.py
"""
import asyncio, json, os, re, sys


async def safe_click(locator, timeout: int = 10000):
    try:
        await locator.scroll_into_view_if_needed(timeout=3000)
    except Exception:
        pass
    try:
        await locator.click(timeout=timeout); return
    except Exception:
        pass
    try:
        await locator.click(force=True, timeout=3000); return
    except Exception:
        pass
    handle = await locator.element_handle()
    if handle:
        await handle.evaluate("el => el.click()"); return
    raise RuntimeError("safe_click failed")


async def main():
    spec = json.loads(os.environ["INVOICE_JSON"])
    customer = spec["customer"]
    items = spec["line_items"]
    note = spec.get("note", "")
    invoice_date = spec.get("invoice_date", "")
    job_num = spec.get("job_num", "")

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

    print(f"[oneoff] page={page.url}")
    await page.goto("https://qbo.intuit.com/app/invoice")
    await page.wait_for_selector('[role="dialog"]', timeout=15000)
    await asyncio.sleep(1.5)

    # Customer
    cc = page.get_by_role("combobox", name=re.compile(r"Customer", re.I))
    await safe_click(cc)
    await cc.fill(customer)
    await asyncio.sleep(0.5)
    opt = page.get_by_role("option", name=re.compile(re.escape(customer), re.I))
    await safe_click(opt.first)
    await asyncio.sleep(0.7)
    print(f"[oneoff] customer set: {customer}")

    # Date
    if invoice_date:
        df = page.get_by_role("textbox", name=re.compile(r"Invoice date", re.I))
        await safe_click(df)
        await page.keyboard.press("Control+a")
        await df.fill(invoice_date)
        await page.keyboard.press("Tab")
        await asyncio.sleep(0.3)
        print(f"[oneoff] date set: {invoice_date}")

    # Job num
    if job_num:
        try:
            jf = page.get_by_role("textbox", name=re.compile(r"P\.O\.|PO|Job", re.I))
            await jf.fill(job_num)
        except Exception:
            pass

    # Line items
    for i, item in enumerate(items):
        n = i + 1
        pc = page.get_by_role("combobox", name=re.compile(rf"Product or service line {n}"))
        await safe_click(pc)
        await pc.fill(item["product"])
        await asyncio.sleep(0.7)
        po = page.get_by_role("option", name=re.compile(re.escape(item["product"]), re.I))
        await safe_click(po.first)
        await asyncio.sleep(0.5)
        print(f"[oneoff] line {n} product set: {item['product']}")

        if item.get("description"):
            df2 = page.get_by_role("textbox", name=re.compile(rf"Description line {n}"))
            await safe_click(df2)
            await page.keyboard.press("Control+a")
            await df2.fill(item["description"])

        if item.get("qty"):
            qf = page.get_by_role("textbox", name=re.compile(rf"Qty|Quantity.*line {n}"))
            await safe_click(qf)
            await page.keyboard.press("Control+a")
            await qf.fill(str(item["qty"]))

        if item.get("rate"):
            rf = page.get_by_role("textbox", name=re.compile(rf"Rate line {n}"))
            await safe_click(rf)
            await page.keyboard.press("Control+a")
            await rf.fill(str(item["rate"]))
            await page.keyboard.press("Tab")
            await asyncio.sleep(0.3)
        await asyncio.sleep(0.4)

    # Note
    if note:
        try:
            nf = page.get_by_role("textbox", name=re.compile(r"Note to customer", re.I))
            await nf.fill(note)
        except Exception:
            pass

    await asyncio.sleep(1)
    total = await page.evaluate("""() => {
        const t = document.querySelector('[role="dialog"]')?.textContent || '';
        return (t.match(/Invoice total\\s*\\$?([\\d,]+\\.\\d{2})/) || [])[1] || null;
    }""")
    print(f"[oneoff] total before save: ${total}")

    # NOTE: NOT clicking Save automatically. Leaving form filled for Scott
    # to review and click Save (and Send + CC) himself.
    print("[oneoff] form filled — review, click 'Save and send', add CC, then submit")


if __name__ == "__main__":
    asyncio.run(main())
