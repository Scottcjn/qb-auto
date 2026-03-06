# QB Automation Playbook

## RULE: Never use browser_snapshot for QuickBooks pages
QB snapshots are 50K+ tokens. Use the extractors below instead (~200-500 tokens each).
Only use browser_snapshot as absolute last resort if all extractors fail.

## Quick Reference

| Task | Tool | What to do |
|------|------|------------|
| Where am I? | `browser_evaluate` | Page Identity extractor |
| List invoices | `browser_evaluate` | Invoice List extractor |
| Payment form state | `browser_evaluate` | Payment Form extractor |
| Invoice form state | `browser_evaluate` | Invoice Form extractor |
| Did save work? | `browser_evaluate` | Post-Save Check extractor |
| Receive 1 payment | `browser_run_code` | Receive Payment action |
| Receive N payments | `browser_run_code` | Batch Receive Payments action |
| Create invoice | `browser_run_code` | Create Invoice action |
| Delete line item | `browser_run_code` | Delete Line Item action |
| Edit payment amount | `browser_run_code` | Edit Payment Amount action |

## Extractor Templates (for browser_evaluate)

### Page Identity (~50 tokens)
```javascript
() => {
  const dialog = document.querySelector('[role="dialog"]');
  const toast = document.querySelector('[role="alert"]');
  return {
    title: document.title,
    url: location.pathname,
    dialog: dialog?.querySelector('h2')?.textContent?.trim() || null,
    toast: toast?.textContent?.trim()?.substring(0, 200) || null
  };
}
```

### Invoice List (~200 tokens)
```javascript
() => {
  const rows = document.querySelectorAll('table tbody tr');
  const inv = [];
  rows.forEach(r => {
    const c = r.querySelectorAll('td');
    if (c.length < 6) return;
    const num = c[3]?.textContent?.trim();
    if (!num || !/^\d+$/.test(num)) return;
    inv.push({n:num, d:c[2]?.textContent?.trim(), c:c[4]?.textContent?.trim(), a:c[5]?.textContent?.trim(), s:c[6]?.textContent?.trim().replace(/\s+/g,' ').substring(0,60)});
  });
  return {invoices:inv, count:inv.length};
}
```

### Payment Form State (~300 tokens)
```javascript
() => {
  const d = document.querySelector('[role="dialog"]');
  if (!d) return {error:'no dialog'};
  const g = (l) => { const e = d.querySelector(`[role="combobox"][aria-label*="${l}"]`); return e?(e.value||e.textContent?.trim()):null; };
  const f = (l) => { const e = d.querySelector(`[aria-label*="${l}"]`); return e?(e.value||e.textContent?.trim()):null; };
  const rows = [];
  d.querySelectorAll('table tbody tr').forEach(r => {
    const c = r.querySelectorAll('td');
    if (c.length<4) return;
    const cb = c[0]?.querySelector('input[type="checkbox"]');
    rows.push({desc:c[1]?.textContent?.trim()?.substring(0,60), amt:c[3]?.textContent?.trim(), bal:c[4]?.textContent?.trim(), checked:cb?.checked||false});
  });
  return {customer:g('Customer'), method:g('Select method'), deposit:g('Choose an account'), amount:f('Amount Received'), outstanding:rows};
}
```

### Invoice Form State (~400 tokens)
```javascript
() => {
  const d = document.querySelector('[role="dialog"]');
  if (!d) return {error:'no dialog'};
  const g = (l) => { const e = d.querySelector(`[role="combobox"][aria-label*="${l}"]`); return e?(e.value||e.textContent?.trim()):null; };
  const f = (l) => { const e = d.querySelector(`[aria-label*="${l}"]`); return e?(e.value||e.textContent?.trim()):null; };
  const lines = [];
  d.querySelectorAll('table tbody tr').forEach((r,i) => {
    const p = r.querySelector('[aria-label*="Product or service line"]');
    const desc = r.querySelector('[aria-label*="Description line"]');
    const pv = p?(p.value||p.textContent?.trim()):'';
    if (!pv && !desc?.value) return;
    lines.push({line:i+1, product:pv, desc:desc?(desc.value||desc.textContent?.trim()):'', rate:r.querySelector('[aria-label*="Rate line"]')?.value||'', amount:r.querySelector('[aria-label*="Amount line"]')?.value||''});
  });
  const t = d.textContent;
  return {num:f('Invoice no.')||d.querySelector('h2')?.textContent?.match(/\d+/)?.[0], customer:g('Customer'), date:f('Invoice date'), lines, total:t.match(/Invoice total\s*\$?([\d,]+\.\d{2})/)?.[1]||null, balance:t.match(/Balance due\s*\$?([\d,.-]+)/)?.[1]||null};
}
```

### Post-Save Check (~30 tokens)
```javascript
() => {
  const d = document.querySelector('[role="dialog"]');
  const t = document.querySelector('[role="alert"]');
  const c = document.querySelector('[role="dialog"] h1');
  return {dialogOpen:!!d, confirm:c?.textContent?.trim()||null, toast:t?.textContent?.trim()?.substring(0,200)||null};
}
```

## Action Templates (for browser_run_code)

See `/home/scott/qb-auto/actions.js` for full code. Below are the parameter signatures:

### Receive Payment
Replace in the template: `INVOICE_NUM`, `AMOUNT`, `METHOD`, `DATE`
```
INVOICE_NUM = '6753'    // invoice number
AMOUNT = '22500'        // no $ or commas
METHOD = 'ACH'          // ACH | Check | Cash | Credit Card
DATE = ''               // MM/DD/YYYY or empty for today
```

### Create Invoice
Replace: `CUSTOMER`, `LINE_ITEMS`, `NOTE`, `INVOICE_DATE`
```
CUSTOMER = 'Wachter'
LINE_ITEMS = [
  {product: 'Hourly Labor-Wachter', description: '5 hours on-site', qty: '5', rate: '105'},
  {product: 'Materials', description: 'Zip ties', qty: '1', rate: '5'}
]
NOTE = 'WJID: 1254049'
INVOICE_DATE = '03/04/2026'
```

### Batch Receive Payments
Replace: `PAYMENTS` array
```
PAYMENTS = [
  {invoiceNum: '6865', amount: '22500', method: 'ACH'},
  {invoiceNum: '6823', amount: '1620.46', method: 'ACH'}
]
```

## QB Constants

### Payment Methods (exact option text)
ACH, Cash, Check, Credit Card, PayPal

### Deposit Accounts
- First Horizon Checking 2776 (default for Wachter ACH)
- Undeposited Funds

### QB URLs
- Invoices: `https://qbo.intuit.com/app/invoices`
- New Invoice: `https://qbo.intuit.com/app/invoice`
- Dashboard: `https://qbo.intuit.com/app/homepage`

### Wachter Rates
- Normal hourly: $70/hr
- Time-and-a-half: $105/hr
- Product names: "Hourly Labor-Wachter", "Materials"
- WJID goes in "Note to customer" footer
- Job# format: `133428 - 01201 - 1254049`

### Auto Late Fees
- QB auto-adds $5.00 LATE FEE line to overdue invoices (internet subs)
- To remove: use Delete Line Item action on the LATE FEE line
- Remember to also edit the linked payment amount if already paid

## Error Recovery

If an action fails:
1. Run Page Identity extractor — see where we are
2. If dialog still open — run the appropriate form state extractor
3. Fix the specific issue with a targeted browser_run_code
4. If completely stuck — use browser_snapshot as last resort

## Typical Session Flow

```
1. Read this playbook (you're doing it now)
2. User says "receive payment for invoice 6865, $22500, ACH"
3. Copy Receive Payment action from actions.js
4. Replace params: INVOICE_NUM='6865', AMOUNT='22500', METHOD='ACH'
5. Run via browser_run_code — ONE tool call does the whole thing
6. Return result JSON to user
```

Old way: 15 snapshots + 30 tool calls = ~500K tokens
New way: 1 read + 1 run_code + 1 verify = ~15K tokens
