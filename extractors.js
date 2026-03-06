// QuickBooks Online Extractors for browser_evaluate
// Each function returns compact JSON instead of 50K+ accessibility snapshots
// Usage: Copy the function body into browser_evaluate({ function: "..." })

// ============================================================
// 1. PAGE IDENTITY (~50 tokens output)
// Use: "Where am I? What's on screen?"
// ============================================================
const pageIdentity = () => {
  const title = document.title;
  const dialog = document.querySelector('[role="dialog"]');
  const dialogH2 = dialog ? dialog.querySelector('h2') : null;
  const toast = document.querySelector('[role="alert"]');
  const url = location.pathname + location.search;
  return {
    title,
    url,
    dialog: dialogH2 ? dialogH2.textContent.trim() : null,
    toast: toast ? toast.textContent.trim().substring(0, 200) : null
  };
};

// ============================================================
// 2. INVOICE LIST (~20 tokens per invoice)
// Use: "Show me all invoices" / "Find invoice 6753"
// ============================================================
const invoiceList = () => {
  const rows = document.querySelectorAll('table tbody tr');
  const invoices = [];
  rows.forEach(r => {
    const cells = r.querySelectorAll('td');
    if (cells.length < 6) return;
    // QB invoice table: checkbox | empty | date | num | customer | amount | status | actions
    const num = cells[3]?.textContent?.trim();
    if (!num || !/^\d+$/.test(num)) return;
    invoices.push({
      num,
      date: cells[2]?.textContent?.trim(),
      customer: cells[4]?.textContent?.trim(),
      amount: cells[5]?.textContent?.trim(),
      status: cells[6]?.textContent?.trim().replace(/\s+/g, ' ').substring(0, 60)
    });
  });
  // Get filter state
  const statusFilter = document.querySelector('[aria-label="Status filter"]');
  const dateFilter = document.querySelector('[aria-label="Date filter"]');
  return {
    invoices,
    count: invoices.length,
    filters: {
      status: statusFilter?.textContent?.trim() || 'unknown',
      date: dateFilter?.textContent?.trim() || 'unknown'
    }
  };
};

// ============================================================
// 3. PAYMENT FORM STATE (~300 tokens output)
// Use: After opening Receive Payment dialog
// ============================================================
const paymentFormState = () => {
  const dialog = document.querySelector('[role="dialog"]');
  if (!dialog) return { error: 'No dialog open' };

  // Helper: find element by aria-label pattern within dialog
  const getField = (selector) => {
    const el = dialog.querySelector(selector);
    return el ? (el.value || el.textContent?.trim()) : null;
  };

  const getCombo = (label) => {
    const el = dialog.querySelector(`[role="combobox"][aria-label*="${label}"]`);
    return el ? (el.value || el.textContent?.trim()) : null;
  };

  const getInput = (label) => {
    const el = dialog.querySelector(`[aria-label*="${label}"]`);
    return el ? (el.value || el.textContent?.trim()) : null;
  };

  // Outstanding invoices in the payment table
  const invoiceRows = [];
  const table = dialog.querySelectorAll('table tbody tr');
  table.forEach(r => {
    const cells = r.querySelectorAll('td');
    if (cells.length < 4) return;
    const checkbox = cells[0]?.querySelector('input[type="checkbox"]');
    const desc = cells[1]?.textContent?.trim();
    if (!desc) return;
    invoiceRows.push({
      desc: desc.substring(0, 80),
      dueDate: cells[2]?.textContent?.trim(),
      origAmount: cells[3]?.textContent?.trim(),
      openBalance: cells[4]?.textContent?.trim(),
      checked: checkbox?.checked || false
    });
  });

  return {
    page: 'receive_payment',
    customer: getCombo('Customer'),
    paymentMethod: getCombo('Select method'),
    depositTo: getCombo('Choose an account'),
    amount: getInput('Amount Received'),
    refNo: getInput('Reference'),
    memo: getInput('Memo'),
    outstanding: invoiceRows,
    outstandingCount: invoiceRows.length
  };
};

// ============================================================
// 4. INVOICE FORM STATE (~400 tokens output)
// Use: When creating or editing an invoice
// ============================================================
const invoiceFormState = () => {
  const dialog = document.querySelector('[role="dialog"]');
  if (!dialog) return { error: 'No dialog open' };

  const getCombo = (label) => {
    const el = dialog.querySelector(`[role="combobox"][aria-label*="${label}"]`);
    return el ? (el.value || el.textContent?.trim()) : null;
  };

  const getInput = (label) => {
    const el = dialog.querySelector(`[aria-label*="${label}"]`);
    return el ? (el.value || el.textContent?.trim()) : null;
  };

  // Extract line items
  const lineItems = [];
  const rows = dialog.querySelectorAll('table tbody tr');
  rows.forEach((r, i) => {
    const product = r.querySelector('[aria-label*="Product or service line"]');
    const desc = r.querySelector('[aria-label*="Description line"]');
    const qty = r.querySelector('[aria-label*="Quantity line"], [aria-label*="Qty line"]');
    const rate = r.querySelector('[aria-label*="Rate line"]');
    const amount = r.querySelector('[aria-label*="Amount line"]');
    const taxCheckbox = r.querySelector('[aria-label="Tax"] input[type="checkbox"], [role="checkbox"][aria-label="Tax"]');

    const productVal = product ? (product.value || product.textContent?.trim()) : '';
    if (!productVal && !desc?.value) return; // skip empty rows

    lineItems.push({
      line: i + 1,
      product: productVal,
      description: desc ? (desc.value || desc.textContent?.trim()) : '',
      qty: qty ? (qty.value || qty.textContent?.trim()) : '',
      rate: rate ? (rate.value || rate.textContent?.trim()) : '',
      amount: amount ? (amount.value || amount.textContent?.trim()) : '',
      taxed: taxCheckbox ? (taxCheckbox.checked || taxCheckbox.getAttribute('aria-checked') === 'true') : false
    });
  });

  // Get totals from the summary area
  const subtotalEl = dialog.querySelector('[class*="subtotal"], [class*="Subtotal"]');
  const totalEl = dialog.querySelector('[class*="total"], [class*="Total"]');

  // Simpler: look for text patterns
  const allText = dialog.textContent;
  const subtotalMatch = allText.match(/Subtotal\s*\$?([\d,]+\.\d{2})/);
  const totalMatch = allText.match(/Invoice total\s*\$?([\d,]+\.\d{2})/);
  const balanceMatch = allText.match(/Balance due\s*\$?([\d,.-]+\.\d{2})/);

  return {
    page: 'invoice',
    invoiceNum: getInput('Invoice no.') || dialog.querySelector('h2')?.textContent?.match(/\d+/)?.[0],
    customer: getCombo('Customer'),
    invoiceDate: getInput('Invoice date'),
    dueDate: getInput('Due date'),
    lineItems,
    lineCount: lineItems.length,
    subtotal: subtotalMatch ? subtotalMatch[1] : null,
    total: totalMatch ? totalMatch[1] : null,
    balanceDue: balanceMatch ? balanceMatch[1] : null,
    noteToCustomer: getInput('Note to customer') || getInput('note to customer'),
    memo: getInput('Memo')
  };
};

// ============================================================
// 5. REPORT EXTRACTOR (~50-500 tokens depending on report)
// Use: After navigating to any QBO report page
// ============================================================
const reportExtract = () => {
  const titleEl = document.querySelector('h1');
  const title = titleEl ? titleEl.textContent.trim() : document.title;
  const h2s = Array.from(document.querySelectorAll('h2'));
  const dateEl = h2s.find(h => /\d{4}|January|February|March|April|May|June|July|August|September|October|November|December/.test(h.textContent));
  const dateRange = dateEl ? dateEl.textContent.trim() : null;
  const tables = document.querySelectorAll('table');
  const sections = [];
  tables.forEach(table => {
    const headers = [];
    const headerRow = table.querySelector('thead tr');
    if (headerRow) headerRow.querySelectorAll('th').forEach(th => headers.push(th.textContent.trim()));
    const rows = [];
    table.querySelectorAll('tbody tr').forEach(r => {
      const cells = [];
      r.querySelectorAll('td').forEach(td => cells.push(td.textContent.trim()));
      if (cells.length > 0 && cells.some(c => c !== '')) rows.push({ cells, isTotal: r.textContent.includes('Total') });
    });
    const footer = [];
    table.querySelectorAll('tfoot tr').forEach(r => {
      const cells = [];
      r.querySelectorAll('td, th').forEach(td => cells.push(td.textContent.trim()));
      if (cells.length > 0) footer.push(cells);
    });
    if (rows.length > 0) sections.push({ headers, rows: rows.slice(0, 200), footer, rowCount: rows.length });
  });
  return { title, dateRange, sections, sectionCount: sections.length, url: location.pathname };
};

// ============================================================
// 6. POST-SAVE VERIFICATION (~30 tokens output)
// Use: After clicking save to verify success
// ============================================================
const postSaveCheck = () => {
  const dialog = document.querySelector('[role="dialog"]');
  const toast = document.querySelector('[role="alert"]');
  const confirmDialog = document.querySelector('[role="dialog"] h1');
  return {
    dialogOpen: !!dialog,
    dialogTitle: dialog?.querySelector('h2')?.textContent?.trim() || null,
    confirmPrompt: confirmDialog?.textContent?.trim() || null,
    toast: toast?.textContent?.trim()?.substring(0, 200) || null,
    url: location.pathname
  };
};
