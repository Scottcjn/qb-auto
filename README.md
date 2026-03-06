# qb-auto — QuickBooks MCP Server

MCP (Model Context Protocol) server that gives Claude Code native tools for QuickBooks Online automation.

Replaces 50K-token `browser_snapshot` round-trips with targeted DOM extraction (~200-500 tokens) and compound Playwright actions that complete entire workflows in one tool call.

## Tools

| Tool | Description |
|------|-------------|
| `qb_page_state` | Check current page/dialog state (~50 tokens) |
| `qb_list_invoices` | List all visible invoices with optional customer filter |
| `qb_invoice_state` | Inspect an open invoice form (line items, totals) |
| `qb_receive_payment` | Record a payment (navigate → fill → save → confirm) |
| `qb_create_invoice` | Create a new invoice with line items |
| `qb_delete_line_item` | Delete a line from an existing invoice |
| `qb_edit_payment_amount` | Edit an existing payment amount |
| `qb_batch_receive_payments` | Record multiple payments in sequence |
| `qb_report` | Run any QBO report (30+ report types) with date range options |
| `qb_report_pnl` | Profit & Loss (income statement) |
| `qb_report_balance_sheet` | Balance Sheet (assets, liabilities, equity) |
| `qb_report_ar_aging` | A/R Aging Summary (who owes, how overdue) |
| `qb_report_customer_balance` | Customer Balance Summary |
| `qb_report_open_invoices` | Open (unpaid) Invoices |
| `qb_report_vendor_balance` | Vendor Balance Summary |

## Token Savings

| Workflow | Before (snapshots) | After (MCP) | Savings |
|----------|--------------------|-------------|---------|
| Receive Payment | ~290K tokens | ~13K tokens | 95% |
| Create Invoice | ~350K tokens | ~18K tokens | 95% |
| Full session (5 ops) | ~500K tokens | ~45K tokens | 91% |

## Setup

### Prerequisites

- Python 3.10+
- `mcp` and `playwright` packages
- Chrome running with remote debugging: `google-chrome --remote-debugging-port=9222`

### Install

```bash
pip install mcp playwright
playwright install chromium
```

### Register with Claude Code

Add to `~/.mcp.json`:

```json
{
  "mcpServers": {
    "quickbooks": {
      "type": "stdio",
      "command": "python3",
      "args": ["/path/to/qb-auto/server.py"]
    }
  }
}
```

### Configuration

The server connects to Chrome via CDP (Chrome DevTools Protocol) on port 9222 by default. Set the `CDP_PORT` variable in `server.py` if using a different port.

## Architecture

- **Extractors**: JavaScript functions injected via `page.evaluate()` that return compact JSON from QB's DOM using ARIA selectors
- **Actions**: Complete Playwright workflows using `getByRole()` and `getByLabel()` — ARIA-stable selectors that survive QB page reloads
- **Playbook**: `PLAYBOOK.md` contains the full reference for manual use with `browser_evaluate`/`browser_run_code`

## Files

| File | Purpose |
|------|---------|
| `server.py` | MCP server with 15 tools |
| `extractors.js` | Standalone JS extractor functions (reference) |
| `actions.js` | Playwright action templates (reference) |
| `PLAYBOOK.md` | Quick reference for manual browser automation |

## How It Works

1. Claude calls `qb_receive_payment(invoice_num="6865", amount="22500", method="ACH")`
2. Server connects to your Chrome browser via CDP
3. Navigates to QB invoices, finds the invoice, opens payment dialog
4. Fills method, amount, saves, handles confirmations
5. Returns compact JSON result (~200 tokens)

No browser snapshots. No 50K token pages. One tool call = one complete operation.

## License

MIT
