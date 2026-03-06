#!/usr/bin/env python3
"""
QuickBooks Online MCP Server — High-level QB automation tools for Claude Code.

Connects to an existing Chrome browser via CDP (Chrome DevTools Protocol)
and exposes QB operations as native MCP tools. One tool call = one complete workflow.

Replaces 50K-token browser_snapshot round-trips with targeted DOM extraction
and compound Playwright actions.

Setup: Add to ~/.mcp.json:
{
  "mcpServers": {
    "quickbooks": {
      "type": "stdio",
      "command": "python3",
      "args": ["/home/scott/qb-auto/server.py"]
    }
  }
}
"""

import asyncio
import json
import os
import re
from typing import Optional

from mcp.server.fastmcp import FastMCP

# ---------------------------------------------------------------------------
# MCP Server
# ---------------------------------------------------------------------------

mcp = FastMCP(
    "quickbooks",
    instructions="""\
QuickBooks Online automation server. Provides high-level tools for invoice
and payment operations. Each tool handles an entire workflow (navigate, fill,
save, confirm) in one call. No browser_snapshot needed.

Tools: qb_list_invoices, qb_receive_payment, qb_create_invoice,
qb_invoice_state, qb_page_state, qb_delete_line_item, qb_edit_payment_amount,
qb_batch_receive_payments, qb_report, qb_report_pnl, qb_report_balance_sheet,
qb_report_ar_aging, qb_report_customer_balance, qb_report_open_invoices,
qb_report_vendor_balance.

IMPORTANT: These tools connect to Chrome via CDP. Chrome must be running
with remote debugging enabled. If connection fails, start Chrome with:
  google-chrome --remote-debugging-port=9222
Or connect to existing Playwright MCP browser session.""",
)

# ---------------------------------------------------------------------------
# Browser Connection
# ---------------------------------------------------------------------------

_browser = None
_context = None
_page = None

# CDP port — configurable via env var, default 9222
CDP_PORT = int(os.environ.get("QB_CDP_PORT", "9222"))
CDP_URL = f"http://127.0.0.1:{CDP_PORT}"

# Alternative: connect to Playwright MCP's browser via its user-data-dir
PLAYWRIGHT_MCP_DATA_DIR = os.environ.get(
    "QB_PLAYWRIGHT_DATA_DIR",
    os.path.expanduser("~/.cache/ms-playwright/mcp-chrome-data"),
)


async def get_page():
    """Get or create a browser page connected to Chrome via CDP."""
    global _browser, _context, _page

    if _page and not _page.is_closed():
        return _page

    from playwright.async_api import async_playwright

    pw = await async_playwright().start()

    # Strategy 1: Connect via CDP to existing Chrome
    try:
        _browser = await pw.chromium.connect_over_cdp(CDP_URL, timeout=5000)
        contexts = _browser.contexts
        if contexts:
            _context = contexts[0]
            pages = _context.pages
            # Find the QB tab or use first tab
            for p in pages:
                if "intuit.com" in p.url or "qbo" in p.url:
                    _page = p
                    return _page
            _page = pages[0] if pages else await _context.new_page()
            return _page
    except Exception:
        pass

    # Strategy 2: Launch persistent context (shares cookies with Playwright MCP)
    try:
        _context = await pw.chromium.launch_persistent_context(
            PLAYWRIGHT_MCP_DATA_DIR,
            headless=False,
            args=["--disable-blink-features=AutomationControlled"],
        )
        _page = _context.pages[0] if _context.pages else await _context.new_page()
        return _page
    except Exception:
        pass

    # Strategy 3: Launch fresh browser
    _browser = await pw.chromium.launch(headless=False)
    _context = await _browser.new_context()
    _page = await _context.new_page()
    return _page


async def ensure_on_invoices(page) -> None:
    """Navigate to invoices page if not already there."""
    if "/app/invoices" not in page.url:
        await page.goto("https://qbo.intuit.com/app/invoices")
        await page.wait_for_selector("table tbody tr", timeout=15000)
        await asyncio.sleep(1)


# ---------------------------------------------------------------------------
# Extractors (run JS in page, return compact JSON)
# ---------------------------------------------------------------------------

PAGE_IDENTITY_JS = """() => {
    const d = document.querySelector('[role="dialog"]');
    const t = document.querySelector('[role="alert"]');
    return {
        title: document.title,
        url: location.pathname + location.search,
        dialog: d ? (d.querySelector('h2')?.textContent?.trim() || 'unnamed') : null,
        toast: t ? t.textContent.trim().substring(0, 200) : null
    };
}"""

INVOICE_LIST_JS = """() => {
    const rows = document.querySelectorAll('table tbody tr');
    const inv = [];
    rows.forEach(r => {
        const c = r.querySelectorAll('td');
        if (c.length < 6) return;
        const num = c[3]?.textContent?.trim();
        if (!num || !/^\\d+$/.test(num)) return;
        inv.push({
            num: num,
            date: c[2]?.textContent?.trim(),
            customer: c[4]?.textContent?.trim(),
            amount: c[5]?.textContent?.trim(),
            status: c[6]?.textContent?.trim().replace(/\\s+/g, ' ').substring(0, 60)
        });
    });
    return { invoices: inv, count: inv.length };
}"""

PAYMENT_FORM_JS = """() => {
    const d = document.querySelector('[role="dialog"]');
    if (!d) return { error: 'no dialog open' };
    const g = (l) => { const e = d.querySelector('[role="combobox"][aria-label*="' + l + '"]'); return e ? (e.value || e.textContent?.trim()) : null; };
    const f = (l) => { const e = d.querySelector('[aria-label*="' + l + '"]'); return e ? (e.value || e.textContent?.trim()) : null; };
    const rows = [];
    d.querySelectorAll('table tbody tr').forEach(r => {
        const c = r.querySelectorAll('td');
        if (c.length < 4) return;
        const cb = c[0]?.querySelector('input[type="checkbox"]');
        rows.push({ desc: c[1]?.textContent?.trim()?.substring(0, 60), amt: c[3]?.textContent?.trim(), bal: c[4]?.textContent?.trim(), checked: cb?.checked || false });
    });
    return { customer: g('Customer'), method: g('Select method'), deposit: g('Choose an account'), amount: f('Amount Received'), outstanding: rows };
}"""

INVOICE_FORM_JS = """() => {
    const d = document.querySelector('[role="dialog"]');
    if (!d) return { error: 'no dialog open' };
    const g = (l) => { const e = d.querySelector('[role="combobox"][aria-label*="' + l + '"]'); return e ? (e.value || e.textContent?.trim()) : null; };
    const f = (l) => { const e = d.querySelector('[aria-label*="' + l + '"]'); return e ? (e.value || e.textContent?.trim()) : null; };
    const lines = [];
    d.querySelectorAll('table tbody tr').forEach((r, i) => {
        const p = r.querySelector('[aria-label*="Product or service line"]');
        const desc = r.querySelector('[aria-label*="Description line"]');
        const pv = p ? (p.value || p.textContent?.trim()) : '';
        if (!pv && !(desc?.value)) return;
        lines.push({
            line: i + 1,
            product: pv,
            desc: desc ? (desc.value || desc.textContent?.trim()) : '',
            rate: r.querySelector('[aria-label*="Rate line"]')?.value || '',
            amount: r.querySelector('[aria-label*="Amount line"]')?.value || ''
        });
    });
    const t = d.textContent;
    return {
        num: f('Invoice no.') || d.querySelector('h2')?.textContent?.match(/\\d+/)?.[0],
        customer: g('Customer'),
        date: f('Invoice date'),
        lines: lines,
        total: (t.match(/Invoice total\\s*\\$?([\\d,]+\\.\\d{2})/) || [])[1] || null,
        balance: (t.match(/Balance due\\s*\\$?([\\d,.-]+)/) || [])[1] || null
    };
}"""


# ---------------------------------------------------------------------------
# Tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def qb_page_state() -> str:
    """Check what QuickBooks page or dialog is currently open.
    Returns: page title, URL, dialog name, and any toast message.
    Use this to orient before taking action."""
    page = await get_page()
    result = await page.evaluate(PAGE_IDENTITY_JS)
    return json.dumps(result, indent=2)


@mcp.tool()
async def qb_list_invoices(customer: Optional[str] = None) -> str:
    """List all invoices currently visible on the QuickBooks invoices page.
    Optionally filter by customer name (case-insensitive substring match).
    Returns: array of {num, date, customer, amount, status}."""
    page = await get_page()
    await ensure_on_invoices(page)
    result = await page.evaluate(INVOICE_LIST_JS)

    if customer and result.get("invoices"):
        customer_lower = customer.lower()
        result["invoices"] = [
            inv for inv in result["invoices"]
            if customer_lower in inv.get("customer", "").lower()
        ]
        result["count"] = len(result["invoices"])
        result["filter"] = customer

    return json.dumps(result, indent=2)


@mcp.tool()
async def qb_invoice_state() -> str:
    """Get the current state of an open invoice form (edit or create).
    Returns: invoice number, customer, line items, totals.
    Use after opening an invoice to inspect before editing."""
    page = await get_page()
    result = await page.evaluate(INVOICE_FORM_JS)
    return json.dumps(result, indent=2)


@mcp.tool()
async def qb_receive_payment(
    invoice_num: str,
    amount: str,
    method: str = "ACH",
    date: str = "",
) -> str:
    """Record a payment for a specific invoice.

    Args:
        invoice_num: Invoice number (e.g. '6865')
        amount: Payment amount without $ or commas (e.g. '22500')
        method: Payment method — ACH, Check, Cash, Credit Card (default: ACH)
        date: Payment date MM/DD/YYYY (default: today)

    Returns: success status and toast message.
    Handles the entire workflow: navigate, find invoice, open payment dialog,
    fill form, save, and handle confirmation dialogs."""
    page = await get_page()
    await ensure_on_invoices(page)

    try:
        # Find invoice row and click action button
        row_btn = page.get_by_role("button", name=re.compile(rf"View/Edit {invoice_num}"))
        count = await row_btn.count()
        if count == 0:
            return json.dumps({"success": False, "error": f"Invoice {invoice_num} not found in list. May need to scroll or change filters."})

        await row_btn.click()
        await asyncio.sleep(0.3)

        # Click "Receive payment" in dropdown
        receive_btn = page.get_by_role("button", name="Receive payment")
        all_receive = await receive_btn.all()
        await all_receive[-1].click()

        # Wait for dialog
        await page.wait_for_selector('[role="dialog"]', timeout=10000)
        await asyncio.sleep(1)

        # Set payment method
        if method:
            method_combo = page.get_by_role("combobox", name=re.compile(r"Select method", re.I))
            await method_combo.click()
            await asyncio.sleep(0.3)
            option = page.get_by_role("option", name=re.compile(rf"^{re.escape(method)}$", re.I))
            await option.click()
            await asyncio.sleep(0.3)

        # Set amount
        if amount:
            amount_field = page.get_by_role("textbox", name=re.compile(r"Amount Received", re.I))
            await amount_field.click()
            await page.keyboard.press("Control+a")
            await amount_field.fill(amount)
            await page.keyboard.press("Tab")
            await asyncio.sleep(0.5)

        # Set date
        if date:
            date_field = page.get_by_role("textbox", name=re.compile(r"Payment Date", re.I))
            await date_field.click()
            await page.keyboard.press("Control+a")
            await date_field.fill(date)
            await page.keyboard.press("Tab")
            await asyncio.sleep(0.3)

        # Save
        save_btn = page.get_by_role("button", name=re.compile(r"^save$", re.I))
        await save_btn.click()
        await asyncio.sleep(1)

        # Handle confirmation dialog
        try:
            confirm_btn = page.get_by_role("button", name=re.compile(r"^Yes$", re.I))
            await confirm_btn.click(timeout=3000)
            await asyncio.sleep(1)
        except Exception:
            pass

        # Check toast
        await asyncio.sleep(1.5)
        toast_el = await page.query_selector('[role="alert"]')
        toast_text = await toast_el.text_content() if toast_el else None

        return json.dumps({
            "success": bool(toast_text and "payment recorded" in toast_text),
            "invoice": invoice_num,
            "amount": amount,
            "method": method,
            "toast": (toast_text or "").strip()[:200],
        })

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)[:300]})


@mcp.tool()
async def qb_create_invoice(
    customer: str,
    line_items: str,
    note: str = "",
    invoice_date: str = "",
    job_num: str = "",
) -> str:
    """Create a new invoice in QuickBooks.

    Args:
        customer: Customer name (e.g. 'Wachter')
        line_items: JSON array of line items, each with: product, description, qty, rate
                    Example: [{"product":"Hourly Labor-Wachter","description":"5 hrs on-site","qty":"5","rate":"105"}]
        note: Note to customer (appears in footer, e.g. 'WJID: 1254049')
        invoice_date: Invoice date MM/DD/YYYY (default: today)
        job_num: Job/PO number

    Returns: success status, invoice total, and toast message."""
    page = await get_page()

    items = json.loads(line_items) if isinstance(line_items, str) else line_items

    try:
        # Navigate to new invoice
        await page.goto("https://qbo.intuit.com/app/invoice")
        await page.wait_for_selector('[role="dialog"]', timeout=15000)
        await asyncio.sleep(1.5)

        # Set customer
        customer_combo = page.get_by_role("combobox", name=re.compile(r"Customer", re.I))
        await customer_combo.click()
        await customer_combo.fill(customer)
        await asyncio.sleep(0.5)
        customer_option = page.get_by_role("option", name=re.compile(re.escape(customer), re.I))
        await customer_option.first.click()
        await asyncio.sleep(0.5)

        # Set invoice date
        if invoice_date:
            date_field = page.get_by_role("textbox", name=re.compile(r"Invoice date", re.I))
            await date_field.click()
            await page.keyboard.press("Control+a")
            await date_field.fill(invoice_date)
            await page.keyboard.press("Tab")
            await asyncio.sleep(0.3)

        # Set job number
        if job_num:
            try:
                job_field = page.get_by_role("textbox", name=re.compile(r"P\.O\.|PO|Job", re.I))
                await job_field.fill(job_num)
            except Exception:
                pass

        # Fill line items
        for i, item in enumerate(items):
            line_num = i + 1

            # Product/service
            product_combo = page.get_by_role("combobox", name=re.compile(rf"Product or service line {line_num}"))
            await product_combo.click()
            await product_combo.fill(item["product"])
            await asyncio.sleep(0.5)
            product_option = page.get_by_role("option", name=re.compile(re.escape(item["product"]), re.I))
            await product_option.first.click()
            await asyncio.sleep(0.5)

            # Description
            if item.get("description"):
                desc_field = page.get_by_role("textbox", name=re.compile(rf"Description line {line_num}"))
                await desc_field.click()
                await page.keyboard.press("Control+a")
                await desc_field.fill(item["description"])

            # Quantity
            if item.get("qty"):
                qty_field = page.get_by_role("textbox", name=re.compile(rf"Qty|Quantity.*line {line_num}"))
                await qty_field.click()
                await page.keyboard.press("Control+a")
                await qty_field.fill(str(item["qty"]))

            # Rate
            if item.get("rate"):
                rate_field = page.get_by_role("textbox", name=re.compile(rf"Rate line {line_num}"))
                await rate_field.click()
                await page.keyboard.press("Control+a")
                await rate_field.fill(str(item["rate"]))
                await page.keyboard.press("Tab")
                await asyncio.sleep(0.3)

            await asyncio.sleep(0.5)

        # Note to customer
        if note:
            try:
                note_field = page.get_by_role("textbox", name=re.compile(r"Note to customer|note to customer", re.I))
                await note_field.fill(note)
            except Exception:
                await page.keyboard.press("End")
                await asyncio.sleep(0.3)
                note_field = page.get_by_role("textbox", name=re.compile(r"Note to customer", re.I))
                await note_field.fill(note)

        # Wait for totals
        await asyncio.sleep(1)

        # Get total before save
        total = await page.evaluate("""() => {
            const t = document.querySelector('[role="dialog"]')?.textContent || '';
            return (t.match(/Invoice total\\s*\\$?([\\d,]+\\.\\d{2})/) || [])[1] || null;
        }""")

        # Save and close
        save_btn = page.get_by_role("button", name=re.compile(r"Save and close", re.I))
        await save_btn.first.click()
        await asyncio.sleep(1.5)

        # Handle confirmation
        try:
            confirm_btn = page.get_by_role("button", name=re.compile(r"^Yes$", re.I))
            await confirm_btn.click(timeout=3000)
            await asyncio.sleep(1)
        except Exception:
            pass

        # Check toast
        toast_el = await page.query_selector('[role="alert"]')
        toast_text = await toast_el.text_content() if toast_el else None

        return json.dumps({
            "success": bool(toast_text and "saved" in toast_text.lower()),
            "customer": customer,
            "total": total,
            "lineItems": len(items),
            "toast": (toast_text or "").strip()[:200],
        })

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)[:300]})


@mcp.tool()
async def qb_delete_line_item(invoice_num: str, line_number: int) -> str:
    """Delete a line item from an existing invoice.

    Args:
        invoice_num: Invoice number (e.g. '6753')
        line_number: 1-based line number to delete (e.g. 2 for the second line)

    Returns: success status. Commonly used to remove auto-applied late fees."""
    page = await get_page()

    try:
        # Find invoice via search
        await ensure_on_invoices(page)
        search = page.get_by_role("searchbox", name="search")
        await search.click()
        await asyncio.sleep(0.5)

        recent_btn = page.get_by_role("button", name=re.compile(rf"Invoice {invoice_num}"))
        await recent_btn.first.click()
        await page.wait_for_selector('[role="dialog"]', timeout=10000)
        await asyncio.sleep(1)

        # Delete the line
        delete_btn = page.get_by_role("button", name=re.compile(rf"Delete line {line_number}"))
        await delete_btn.first.click()
        await asyncio.sleep(0.5)

        # Save
        save_btn = page.get_by_role("button", name=re.compile(r"Save and close", re.I))
        await save_btn.first.click()
        await asyncio.sleep(1)

        # Confirmation
        try:
            confirm_btn = page.get_by_role("button", name=re.compile(r"^Yes$", re.I))
            await confirm_btn.click(timeout=3000)
            await asyncio.sleep(1)
        except Exception:
            pass

        toast_el = await page.query_selector('[role="alert"]')
        toast_text = await toast_el.text_content() if toast_el else None

        return json.dumps({
            "success": bool(toast_text and "saved" in toast_text.lower()),
            "invoice": invoice_num,
            "deletedLine": line_number,
            "toast": (toast_text or "").strip()[:200],
        })

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)[:300]})


@mcp.tool()
async def qb_edit_payment_amount(invoice_num: str, new_amount: str) -> str:
    """Edit the amount of an existing payment linked to an invoice.

    Args:
        invoice_num: Invoice number the payment is linked to (used to find via search)
        new_amount: New payment amount without $ or commas (e.g. '22500')

    Returns: success status. Use after removing a late fee to rebalance."""
    page = await get_page()

    try:
        # Find payment via search
        await ensure_on_invoices(page)
        search = page.get_by_role("searchbox", name="search")
        await search.click()
        await asyncio.sleep(0.5)

        # Look for payment in recent transactions
        payment_btn = page.get_by_role("button", name=re.compile(r"Payment.*Wachter"))
        await payment_btn.first.click()
        await page.wait_for_selector('[role="dialog"]', timeout=10000)
        await asyncio.sleep(1)

        # Update amount
        amount_field = page.get_by_role("textbox", name=re.compile(r"Amount Received", re.I))
        await amount_field.click()
        await page.keyboard.press("Control+a")
        await amount_field.fill(new_amount)
        await page.keyboard.press("Tab")
        await asyncio.sleep(0.5)

        # Save
        save_btn = page.get_by_role("button", name=re.compile(r"^save$", re.I))
        await save_btn.click()
        await asyncio.sleep(1)

        # Confirmation
        try:
            confirm_btn = page.get_by_role("button", name=re.compile(r"^Yes$", re.I))
            await confirm_btn.click(timeout=3000)
            await asyncio.sleep(1)
        except Exception:
            pass

        await asyncio.sleep(1.5)
        toast_el = await page.query_selector('[role="alert"]')
        toast_text = await toast_el.text_content() if toast_el else None

        return json.dumps({
            "success": bool(toast_text and "payment recorded" in toast_text.lower()),
            "newAmount": new_amount,
            "toast": (toast_text or "").strip()[:200],
        })

    except Exception as e:
        return json.dumps({"success": False, "error": str(e)[:300]})


@mcp.tool()
async def qb_batch_receive_payments(payments: str) -> str:
    """Record payments for multiple invoices in sequence.

    Args:
        payments: JSON array of payments, each with: invoiceNum, amount, method
                  Example: [{"invoiceNum":"6865","amount":"22500","method":"ACH"}]

    Returns: results array with success/failure for each payment."""
    page = await get_page()
    items = json.loads(payments) if isinstance(payments, str) else payments
    results = []

    for pmt in items:
        inv = pmt["invoiceNum"]
        amt = pmt["amount"]
        method = pmt.get("method", "ACH")

        try:
            await ensure_on_invoices(page)
            await asyncio.sleep(0.5)

            row_btn = page.get_by_role("button", name=re.compile(rf"View/Edit {inv}"))
            count = await row_btn.count()
            if count == 0:
                results.append({"invoice": inv, "success": False, "error": "Not found in list"})
                continue

            await row_btn.click()
            await asyncio.sleep(0.3)
            receive_btn = page.get_by_role("button", name="Receive payment")
            all_receive = await receive_btn.all()
            await all_receive[-1].click()
            await page.wait_for_selector('[role="dialog"]', timeout=10000)
            await asyncio.sleep(1)

            # Method
            method_combo = page.get_by_role("combobox", name=re.compile(r"Select method", re.I))
            await method_combo.click()
            await asyncio.sleep(0.3)
            await page.get_by_role("option", name=re.compile(rf"^{re.escape(method)}$", re.I)).click()
            await asyncio.sleep(0.3)

            # Amount
            if amt:
                amount_field = page.get_by_role("textbox", name=re.compile(r"Amount Received", re.I))
                await amount_field.click()
                await page.keyboard.press("Control+a")
                await amount_field.fill(amt)
                await page.keyboard.press("Tab")
                await asyncio.sleep(0.5)

            # Save
            save_btn = page.get_by_role("button", name=re.compile(r"^save$", re.I))
            await save_btn.click()
            await asyncio.sleep(1)

            try:
                confirm_btn = page.get_by_role("button", name=re.compile(r"^Yes$", re.I))
                await confirm_btn.click(timeout=3000)
                await asyncio.sleep(1)
            except Exception:
                pass

            await asyncio.sleep(1.5)
            toast_el = await page.query_selector('[role="alert"]')
            toast_text = await toast_el.text_content() if toast_el else None

            results.append({
                "invoice": inv,
                "amount": amt,
                "method": method,
                "success": bool(toast_text and "payment recorded" in toast_text),
                "toast": (toast_text or "").strip()[:200],
            })

            # Close any remaining dialogs
            try:
                close_btn = page.get_by_role("button", name="Close")
                await close_btn.first.click(timeout=2000)
            except Exception:
                pass
            await asyncio.sleep(0.5)

        except Exception as e:
            results.append({"invoice": inv, "success": False, "error": str(e)[:200]})

    return json.dumps({
        "results": results,
        "total": len(items),
        "succeeded": sum(1 for r in results if r.get("success")),
    }, indent=2)


# ---------------------------------------------------------------------------
# Report Extractors
# ---------------------------------------------------------------------------

# QBO report URLs — date_macro can be: This Month, Last Month, This Quarter,
# Last Quarter, This Year, Last Year, This Month-to-date, This Quarter-to-date,
# This Year-to-date, or custom (requires start_date/end_date)
# QBO report tokens — use /app/report/builder?token=TOKEN format (NOT /app/reports/)
# rptId GUIDs are account-specific; token is universal across QBO accounts
QBO_REPORT_TOKENS = {
    "profit-and-loss": "PANDL",
    "pnl": "PANDL",
    "balance-sheet": "BAL_SHEET",
    "balance-sheet-detail": "BAL_SHEET_DET",
    "balance-sheet-summary": "BAL_SHEET_SUM",
    "ar-aging": "AR_AGING",
    "ar-aging-detail": "AR_AGING_DET",
    "ap-aging": "AP_AGING",
    "ap-aging-detail": "AP_AGING_DET",
    "customer-balance": "CUST_BAL",
    "customer-balance-detail": "CUST_BAL_DET",
    "general-ledger": "GEN_LEDGER",
    "trial-balance": "TRIAL_BAL",
    "expenses-by-vendor": "VEND_EXP",
    "sales-by-customer": "CUST_SALES",
    "sales-by-customer-detail": "CUST_SALES_DET",
    "cash-flow": "CASH_FLOW",
    "invoice-list": "INVOICE_LIST",
    "open-invoices": "OPEN_INVOICES",
    "pnl-by-customer": "PANDL_BYCUST",
    "pnl-by-month": "PANDL_BY_MONTH",
    "pnl-detail": "PANDL_DET",
    "pnl-comparison": "PANDL_COMP",
    "vendor-balance": "VEND_BAL",
    "unpaid-bills": "UNPAID_BILLS",
    "deposit-detail": "DEPOSIT_DETAIL",
    "journal": "JOURNAL",
    "transaction-list": "TX_LIST_BY_DATE",
    "transaction-detail": "TX_DET_BY_ACCT",
    "collections": "COLLECTIONS",
    "income-by-customer": "CUST_INC",
}

REPORT_EXTRACT_JS = """() => {
    // Extract report title — QBO uses h1 for report name
    const titleEl = document.querySelector('h1');
    const title = titleEl ? titleEl.textContent.trim() : document.title;

    // Extract date range — QBO uses h2 for date range (skip nav h2s)
    const h2s = Array.from(document.querySelectorAll('h2'));
    const dateEl = h2s.find(h => /\\d{4}|January|February|March|April|May|June|July|August|September|October|November|December/.test(h.textContent));
    const dateRange = dateEl ? dateEl.textContent.trim() : null;

    // Extract the report table(s)
    const tables = document.querySelectorAll('table');
    const sections = [];

    tables.forEach((table, ti) => {
        const headers = [];
        const headerRow = table.querySelector('thead tr');
        if (headerRow) {
            headerRow.querySelectorAll('th').forEach(th => {
                headers.push(th.textContent.trim());
            });
        }

        const rows = [];
        table.querySelectorAll('tbody tr').forEach(r => {
            const cells = [];
            const isTotal = r.classList.contains('total') ||
                           r.querySelector('[class*="total"], [class*="Total"]') !== null ||
                           r.textContent.includes('Total');
            const indent = r.querySelector('td')?.style?.paddingLeft || '0';

            r.querySelectorAll('td').forEach(td => {
                cells.push(td.textContent.trim());
            });

            if (cells.length > 0 && cells.some(c => c !== '')) {
                rows.push({
                    cells: cells,
                    isTotal: isTotal,
                    depth: parseInt(indent) > 0 ? Math.round(parseInt(indent) / 20) : 0
                });
            }
        });

        // Footer/totals
        const footerRows = [];
        table.querySelectorAll('tfoot tr').forEach(r => {
            const cells = [];
            r.querySelectorAll('td, th').forEach(td => {
                cells.push(td.textContent.trim());
            });
            if (cells.length > 0) footerRows.push(cells);
        });

        if (rows.length > 0 || footerRows.length > 0) {
            sections.push({
                headers: headers,
                rows: rows.slice(0, 200),  // Cap at 200 rows per table
                footer: footerRows,
                rowCount: rows.length
            });
        }
    });

    // Fallback: if no tables, try to extract from the report grid/div structure
    if (sections.length === 0) {
        const gridRows = document.querySelectorAll('[class*="ReportRow"], [class*="report-row"], [role="row"]');
        const fallbackRows = [];
        gridRows.forEach(r => {
            const cells = [];
            r.querySelectorAll('[role="cell"], [class*="cell"], [class*="Cell"], span, div > span').forEach(c => {
                const text = c.textContent.trim();
                if (text) cells.push(text);
            });
            if (cells.length > 0) fallbackRows.push({ cells: cells, isTotal: false, depth: 0 });
        });
        if (fallbackRows.length > 0) {
            sections.push({ headers: [], rows: fallbackRows.slice(0, 200), footer: [], rowCount: fallbackRows.length });
        }
    }

    return {
        title: title,
        dateRange: dateRange,
        sections: sections,
        sectionCount: sections.length,
        url: location.pathname + location.search
    };
}"""


async def navigate_to_report(page, report_token: str, date_macro: str = "",
                              start_date: str = "", end_date: str = "") -> None:
    """Navigate to a QBO report using the token-based URL format.

    QBO uses /app/report/builder?token=TOKEN (not /app/reports/).
    Date params are added as query parameters alongside the token.
    """
    # First ensure we're on a QBO page (SPA routing requires being in-app)
    current_url = page.url
    if "qbo.intuit.com" not in current_url:
        await page.goto("https://qbo.intuit.com/app/standardreports")
        await asyncio.sleep(3)

    # Build the report URL with token
    base_url = f"https://qbo.intuit.com/app/report/builder?token={report_token}"

    params = []
    if date_macro:
        params.append(f"date_macro={date_macro.replace(' ', '%20')}")
    if start_date:
        params.append(f"start_date={start_date}")
    if end_date:
        params.append(f"end_date={end_date}")

    url = base_url + ("&" + "&".join(params) if params else "")
    await page.goto(url)

    # Wait for report to render — QBO reports use standard <table> elements
    try:
        await page.wait_for_selector("table tbody tr, h1",
                                      timeout=20000)
    except Exception:
        pass
    await asyncio.sleep(3)  # Reports load data async after DOM renders


# ---------------------------------------------------------------------------
# Report Tools
# ---------------------------------------------------------------------------

@mcp.tool()
async def qb_report(
    report_name: str,
    date_macro: str = "This Month",
    start_date: str = "",
    end_date: str = "",
) -> str:
    """Run any QuickBooks report and extract its data as structured JSON.

    Args:
        report_name: Report name. Options: profit-and-loss (or pnl), balance-sheet,
                     ar-aging, ar-aging-detail, ap-aging, customer-balance,
                     customer-balance-detail, general-ledger, trial-balance,
                     expenses-by-vendor, sales-by-customer, cash-flow,
                     invoice-list, open-invoices, pnl-by-customer, pnl-by-month,
                     pnl-detail, vendor-balance, unpaid-bills, deposit-detail,
                     journal, transaction-list, collections, income-by-customer
        date_macro: Date range preset — This Month, Last Month, This Quarter,
                    Last Quarter, This Year, Last Year, This Year-to-date, etc.
                    Ignored if start_date/end_date are provided.
        start_date: Custom start date MM/DD/YYYY (overrides date_macro)
        end_date: Custom end date MM/DD/YYYY (overrides date_macro)

    Returns: Report title, date range, headers, and row data as JSON."""
    page = await get_page()

    report_token = QBO_REPORT_TOKENS.get(report_name.lower())
    if not report_token:
        available = ", ".join(sorted(QBO_REPORT_TOKENS.keys()))
        return json.dumps({"error": f"Unknown report '{report_name}'. Available: {available}"})

    try:
        effective_macro = "" if (start_date and end_date) else date_macro
        await navigate_to_report(page, report_token, effective_macro, start_date, end_date)
        result = await page.evaluate(REPORT_EXTRACT_JS)
        return json.dumps(result, indent=2)
    except Exception as e:
        return json.dumps({"error": str(e)[:300]})


@mcp.tool()
async def qb_report_pnl(date_macro: str = "This Month") -> str:
    """Get Profit & Loss (Income Statement) report.

    Args:
        date_macro: This Month, Last Month, This Quarter, Last Quarter,
                    This Year, Last Year, This Year-to-date

    Returns: Income, expenses, and net income broken down by account."""
    return await qb_report("pnl", date_macro=date_macro)


@mcp.tool()
async def qb_report_balance_sheet(date_macro: str = "This Month") -> str:
    """Get Balance Sheet report.

    Args:
        date_macro: This Month, Last Month, This Quarter, This Year, etc.

    Returns: Assets, liabilities, and equity balances."""
    return await qb_report("balance-sheet", date_macro=date_macro)


@mcp.tool()
async def qb_report_ar_aging() -> str:
    """Get Accounts Receivable Aging Summary report.

    Returns: Customer balances organized by aging buckets
    (Current, 1-30, 31-60, 61-90, 91+ days overdue).
    Great for seeing who owes money and how overdue they are."""
    return await qb_report("ar-aging", date_macro="")


@mcp.tool()
async def qb_report_customer_balance() -> str:
    """Get Customer Balance Summary report.

    Returns: Total outstanding balance per customer.
    Use this to quickly see who owes what."""
    return await qb_report("customer-balance", date_macro="")


@mcp.tool()
async def qb_report_open_invoices() -> str:
    """Get Open Invoices report.

    Returns: All unpaid invoices with customer, date, due date, and balance."""
    return await qb_report("open-invoices", date_macro="")


@mcp.tool()
async def qb_report_vendor_balance() -> str:
    """Get Vendor Balance Summary report.

    Returns: Total outstanding balance owed to each vendor."""
    return await qb_report("vendor-balance", date_macro="")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    mcp.run()
