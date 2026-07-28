// SPDX-License-Identifier: MIT
// QuickBooks Online Action Sequences for browser_run_code
// Each function is a complete Playwright workflow in ONE tool call
// Usage: Copy the async (page) => { ... } into browser_run_code({ code: "..." })
// Replace UPPERCASE_PARAMS with actual values before running

// ============================================================
// 1. RECEIVE PAYMENT
// Navigates to invoice list, finds invoice, opens payment dialog,
// fills form, saves, handles confirmation dialog
// ============================================================
// Parameters to replace:
//   INVOICE_NUM  - e.g. '6753'
//   AMOUNT       - e.g. '22500' (no commas, no $)
//   METHOD       - e.g. 'ACH', 'Check', 'Cash', 'Credit Card'
//   DATE         - e.g. '03/04/2026' (MM/DD/YYYY) or '' to keep default
// ============================================================

const receivePayment = async (page) => {
  const INVOICE_NUM = 'REPLACE_ME';
  const AMOUNT = 'REPLACE_ME';
  const METHOD = 'ACH';
  const DATE = '';

  // Navigate to invoices if needed
  if (!page.url().includes('/invoices')) {
    await page.goto('https://qbo.intuit.com/app/invoices');
    await page.waitForSelector('table tbody tr', { timeout: 15000 });
  }

  // Find and click the invoice row action area
  // QB row buttons: "View/Edit {NUM} Receive payment More actions"
  // The "/" has to be escaped: Playwright serializes a RegExp passed to `name`
  // into an internal selector `button[name=/<pattern>/]` and does not escape
  // "/" itself, so a bare one closes that literal early and the selector fails
  // to parse. The trailing (?!\d) stops "685" from matching invoice 6850's row.
  const rowBtn = page.getByRole('button', {
    name: new RegExp(`View\\/Edit ${INVOICE_NUM}(?!\\d)`)
  });
  await rowBtn.click();
  await page.waitForTimeout(300);

  // Click "Receive payment" in the action dropdown
  const receiveBtn = page.getByRole('button', { name: 'Receive payment' });
  // There may be multiple — get the one inside the expanded dropdown
  const allReceive = await receiveBtn.all();
  await allReceive[allReceive.length - 1].click();

  // Wait for dialog
  await page.waitForSelector('[role="dialog"]', { timeout: 10000 });
  await page.waitForTimeout(1000); // let React finish rendering

  // Set payment method
  if (METHOD) {
    const methodCombo = page.getByRole('combobox', { name: /Select method/i });
    await methodCombo.click();
    await page.waitForTimeout(300);
    const option = page.getByRole('option', { name: new RegExp(`^${METHOD}$`, 'i') });
    await option.click();
    await page.waitForTimeout(300);
  }

  // Set amount if specified
  if (AMOUNT) {
    const amountField = page.getByRole('textbox', { name: /Amount Received/i });
    await amountField.click();
    await page.keyboard.press('Control+a');
    await amountField.fill(AMOUNT);
    await page.keyboard.press('Tab');
    await page.waitForTimeout(500);
  }

  // Set date if specified
  if (DATE) {
    const dateField = page.getByRole('textbox', { name: /Payment Date/i });
    await dateField.click();
    await page.keyboard.press('Control+a');
    await dateField.fill(DATE);
    await page.keyboard.press('Tab');
    await page.waitForTimeout(300);
  }

  // Save
  const saveBtn = page.getByRole('button', { name: /^save$/i });
  await saveBtn.click();
  await page.waitForTimeout(1000);

  // Handle confirmation dialog ("Save transaction?")
  try {
    const confirmBtn = page.getByRole('button', { name: /^Yes$/i });
    await confirmBtn.click({ timeout: 3000 });
    await page.waitForTimeout(1000);
  } catch (e) { /* no confirm needed */ }

  // Check for toast
  await page.waitForTimeout(1500);
  const toast = await page.$('[role="alert"]');
  const toastText = toast ? await toast.textContent() : null;

  return {
    success: !!(toastText && toastText.includes('payment recorded')),
    invoice: INVOICE_NUM,
    amount: AMOUNT,
    method: METHOD,
    toast: toastText?.trim()?.substring(0, 200)
  };
};


// ============================================================
// 2. CREATE INVOICE
// Opens new invoice, sets customer, adds line items, saves
// ============================================================
// Parameters to replace:
//   CUSTOMER      - e.g. 'Wachter'
//   INVOICE_DATE  - e.g. '03/04/2026' or '' for today
//   DUE_DATE      - e.g. '04/03/2026' or '' for default terms
//   LINE_ITEMS    - Array of {product, description, qty, rate}
//   NOTE          - Customer note (footer), e.g. 'WJID: 1254049'
//   JOB_NUM       - Job/PO number field
// ============================================================

const createInvoice = async (page) => {
  const CUSTOMER = 'REPLACE_ME';
  const INVOICE_DATE = '';
  const DUE_DATE = '';
  const LINE_ITEMS = [
    // { product: 'Hourly Labor-Wachter', description: '5 hours on-site', qty: '5', rate: '105' },
    // { product: 'Hourly Labor-Wachter', description: '3 hours travel', qty: '3', rate: '105' },
    // { product: 'Materials', description: 'Bag of zip ties', qty: '1', rate: '5' }
  ];
  const NOTE = '';
  const JOB_NUM = '';

  // Navigate to new invoice
  await page.goto('https://qbo.intuit.com/app/invoice');
  await page.waitForSelector('[role="dialog"]', { timeout: 15000 });
  await page.waitForTimeout(1500);

  // Set customer
  const customerCombo = page.getByRole('combobox', { name: /Customer/i });
  await customerCombo.click();
  await customerCombo.fill(CUSTOMER);
  await page.waitForTimeout(500);
  // Select from dropdown
  const customerOption = page.getByRole('option', { name: new RegExp(CUSTOMER, 'i') });
  await customerOption.first().click();
  await page.waitForTimeout(500);

  // Set invoice date
  if (INVOICE_DATE) {
    const dateField = page.getByRole('textbox', { name: /Invoice date/i });
    await dateField.click();
    await page.keyboard.press('Control+a');
    await dateField.fill(INVOICE_DATE);
    await page.keyboard.press('Tab');
    await page.waitForTimeout(300);
  }

  // Set due date
  if (DUE_DATE) {
    const dueField = page.getByRole('textbox', { name: /Due date/i });
    await dueField.click();
    await page.keyboard.press('Control+a');
    await dueField.fill(DUE_DATE);
    await page.keyboard.press('Tab');
    await page.waitForTimeout(300);
  }

  // Set Job/PO number
  if (JOB_NUM) {
    // QB may not always show this field — try to find it
    try {
      const jobField = page.getByRole('textbox', { name: /P\.O\.|PO|Job/i });
      await jobField.fill(JOB_NUM);
    } catch (e) { /* field not visible */ }
  }

  // Fill line items
  for (let i = 0; i < LINE_ITEMS.length; i++) {
    const item = LINE_ITEMS[i];
    const lineNum = i + 1;

    // Product/service combobox
    const productCombo = page.getByRole('combobox', {
      name: new RegExp(`Product or service line ${lineNum}`)
    });
    await productCombo.click();
    await productCombo.fill(item.product);
    await page.waitForTimeout(500);
    // Select from dropdown
    const productOption = page.getByRole('option', { name: new RegExp(item.product, 'i') });
    await productOption.first().click();
    await page.waitForTimeout(500);

    // Description
    if (item.description) {
      const descField = page.getByRole('textbox', {
        name: new RegExp(`Description line ${lineNum}`)
      });
      await descField.click();
      await page.keyboard.press('Control+a');
      await descField.fill(item.description);
    }

    // Quantity
    if (item.qty) {
      const qtyField = page.getByRole('textbox', {
        name: new RegExp(`Qty|Quantity.*line ${lineNum}`)
      });
      await qtyField.click();
      await page.keyboard.press('Control+a');
      await qtyField.fill(item.qty);
    }

    // Rate
    if (item.rate) {
      const rateField = page.getByRole('textbox', {
        name: new RegExp(`Rate line ${lineNum}`)
      });
      await rateField.click();
      await page.keyboard.press('Control+a');
      await rateField.fill(item.rate);
      await page.keyboard.press('Tab');
      await page.waitForTimeout(300);
    }

    // If there's a next line item, we may need to wait for the new row to appear
    if (i < LINE_ITEMS.length - 1) {
      await page.waitForTimeout(500);
    }
  }

  // Note to customer (footer)
  if (NOTE) {
    try {
      const noteField = page.getByRole('textbox', { name: /Note to customer|note to customer/i });
      await noteField.fill(NOTE);
    } catch (e) {
      // Try scrolling down to find it
      await page.keyboard.press('End');
      await page.waitForTimeout(300);
      const noteField2 = page.getByRole('textbox', { name: /Note to customer/i });
      await noteField2.fill(NOTE);
    }
  }

  // Wait for totals to calculate
  await page.waitForTimeout(1000);

  // Extract total before saving
  const totalText = await page.evaluate(() => {
    const text = document.querySelector('[role="dialog"]')?.textContent || '';
    const match = text.match(/Invoice total\s*\$?([\d,]+\.\d{2})/);
    return match ? match[1] : null;
  });

  // Save and close
  const saveBtn = page.getByRole('button', { name: /Save and close/i });
  await saveBtn.first().click();
  await page.waitForTimeout(1500);

  // Handle confirmation if needed
  try {
    const confirmBtn = page.getByRole('button', { name: /^Yes$/i });
    await confirmBtn.click({ timeout: 3000 });
    await page.waitForTimeout(1000);
  } catch (e) { /* no confirm needed */ }

  // Check toast
  const toast = await page.$('[role="alert"]');
  const toastText = toast ? await toast.textContent() : null;

  return {
    success: !!(toastText && toastText.includes('saved')),
    customer: CUSTOMER,
    total: totalText,
    lineItems: LINE_ITEMS.length,
    toast: toastText?.trim()?.substring(0, 200)
  };
};


// ============================================================
// 3. EDIT INVOICE - DELETE LINE ITEM
// Opens invoice, removes a specific line, saves
// ============================================================
// Parameters:
//   INVOICE_NUM    - e.g. '6753'
//   DELETE_LINE    - 1-based line number to delete, e.g. 2
// ============================================================

const deleteLineItem = async (page) => {
  const INVOICE_NUM = 'REPLACE_ME';
  const DELETE_LINE = 2;

  // Navigate to invoice via search
  await page.goto('https://qbo.intuit.com/app/invoices');
  await page.waitForSelector('table', { timeout: 15000 });

  // Click the search box and find the invoice
  const search = page.getByRole('searchbox', { name: 'search' });
  await search.click();
  await page.waitForTimeout(500);

  // Look for it in recent transactions
  const recentBtn = page.getByRole('button', {
    name: new RegExp(`Invoice ${INVOICE_NUM}`)
  });
  await recentBtn.first().click();
  await page.waitForSelector('[role="dialog"]', { timeout: 10000 });
  await page.waitForTimeout(1000);

  // Delete the line
  const deleteBtn = page.getByRole('button', {
    name: new RegExp(`Delete line ${DELETE_LINE}`)
  });
  await deleteBtn.first().click();
  await page.waitForTimeout(500);

  // Save and close
  const saveBtn = page.getByRole('button', { name: /Save and close/i });
  await saveBtn.first().click();
  await page.waitForTimeout(1000);

  // Handle confirmation
  try {
    const confirmBtn = page.getByRole('button', { name: /^Yes$/i });
    await confirmBtn.click({ timeout: 3000 });
    await page.waitForTimeout(1000);
  } catch (e) { /* no confirm needed */ }

  const toast = await page.$('[role="alert"]');
  const toastText = toast ? await toast.textContent() : null;

  return {
    success: !!(toastText && toastText.includes('saved')),
    invoice: INVOICE_NUM,
    deletedLine: DELETE_LINE,
    toast: toastText?.trim()?.substring(0, 200)
  };
};


// ============================================================
// 4. EDIT PAYMENT AMOUNT
// Opens existing payment, changes amount, saves
// ============================================================
// Parameters:
//   INVOICE_NUM   - Invoice the payment is linked to
//   NEW_AMOUNT    - New amount, e.g. '22500'
// ============================================================

const editPaymentAmount = async (page) => {
  const INVOICE_NUM = 'REPLACE_ME';
  const NEW_AMOUNT = 'REPLACE_ME';

  // Use search to find the payment
  await page.goto('https://qbo.intuit.com/app/invoices');
  await page.waitForSelector('table', { timeout: 15000 });

  const search = page.getByRole('searchbox', { name: 'search' });
  await search.click();
  await page.waitForTimeout(500);

  // Find payment linked to this invoice in recent transactions
  // Payment entries show as "Payment | Customer | date | amount"
  const paymentBtn = page.getByRole('button', {
    name: new RegExp(`Payment.*Wachter`)
  });
  await paymentBtn.first().click();
  await page.waitForSelector('[role="dialog"]', { timeout: 10000 });
  await page.waitForTimeout(1000);

  // Update amount
  const amountField = page.getByRole('textbox', { name: /Amount Received/i });
  await amountField.click();
  await page.keyboard.press('Control+a');
  await amountField.fill(NEW_AMOUNT);
  await page.keyboard.press('Tab');
  await page.waitForTimeout(500);

  // Save
  const saveBtn = page.getByRole('button', { name: /^save$/i });
  await saveBtn.click();
  await page.waitForTimeout(1000);

  // Confirmation
  try {
    const confirmBtn = page.getByRole('button', { name: /^Yes$/i });
    await confirmBtn.click({ timeout: 3000 });
    await page.waitForTimeout(1000);
  } catch (e) {}

  const toast = await page.$('[role="alert"]');
  const toastText = toast ? await toast.textContent() : null;

  return {
    success: !!(toastText && toastText.includes('payment recorded')),
    newAmount: NEW_AMOUNT,
    toast: toastText?.trim()?.substring(0, 200)
  };
};


// ============================================================
// 5. BATCH RECEIVE PAYMENTS
// Process multiple invoice payments in sequence
// ============================================================
// Parameters:
//   PAYMENTS - Array of {invoiceNum, amount, method}
// ============================================================

const batchReceivePayments = async (page) => {
  const PAYMENTS = [
    // { invoiceNum: '6865', amount: '22500', method: 'ACH' },
    // { invoiceNum: '6823', amount: '1620.46', method: 'ACH' },
  ];

  const results = [];

  for (const pmt of PAYMENTS) {
    try {
      // Navigate to invoices
      await page.goto('https://qbo.intuit.com/app/invoices');
      await page.waitForSelector('table tbody tr', { timeout: 15000 });
      await page.waitForTimeout(500);

      // Find invoice row
      const rowBtn = page.getByRole('button', {
        name: new RegExp(`View/Edit ${pmt.invoiceNum}`)
      });

      // Check if invoice is visible
      const count = await rowBtn.count();
      if (count === 0) {
        results.push({ invoice: pmt.invoiceNum, success: false, error: 'Invoice not found in list' });
        continue;
      }

      await rowBtn.click();
      await page.waitForTimeout(300);

      const receiveBtn = page.getByRole('button', { name: 'Receive payment' });
      const allReceive = await receiveBtn.all();
      await allReceive[allReceive.length - 1].click();
      await page.waitForSelector('[role="dialog"]', { timeout: 10000 });
      await page.waitForTimeout(1000);

      // Payment method
      const methodCombo = page.getByRole('combobox', { name: /Select method/i });
      await methodCombo.click();
      await page.waitForTimeout(300);
      await page.getByRole('option', { name: new RegExp(`^${pmt.method}$`, 'i') }).click();
      await page.waitForTimeout(300);

      // Amount (if different from auto-filled)
      if (pmt.amount) {
        const amountField = page.getByRole('textbox', { name: /Amount Received/i });
        await amountField.click();
        await page.keyboard.press('Control+a');
        await amountField.fill(pmt.amount);
        await page.keyboard.press('Tab');
        await page.waitForTimeout(500);
      }

      // Save
      const saveBtn = page.getByRole('button', { name: /^save$/i });
      await saveBtn.click();
      await page.waitForTimeout(1000);

      // Confirmation
      try {
        const confirmBtn = page.getByRole('button', { name: /^Yes$/i });
        await confirmBtn.click({ timeout: 3000 });
        await page.waitForTimeout(1000);
      } catch (e) {}

      await page.waitForTimeout(1500);
      const toast = await page.$('[role="alert"]');
      const toastText = toast ? await toast.textContent() : null;

      results.push({
        invoice: pmt.invoiceNum,
        amount: pmt.amount,
        method: pmt.method,
        success: !!(toastText && toastText.includes('payment recorded')),
        toast: toastText?.trim()?.substring(0, 200)
      });

      // Close any remaining dialogs
      try {
        const closeBtn = page.getByRole('button', { name: 'Close' });
        await closeBtn.first().click({ timeout: 2000 });
      } catch (e) {}

      await page.waitForTimeout(500);

    } catch (err) {
      results.push({
        invoice: pmt.invoiceNum,
        success: false,
        error: err.message?.substring(0, 200)
      });
    }
  }

  return { results, total: PAYMENTS.length, succeeded: results.filter(r => r.success).length };
};
