/**
 * Playwright E2E template — Page Object Model + contract-driven validation.
 *
 * A starting point the automation-engineer adapts to the project. Demonstrates:
 *  - the Page Object Model (a page class encapsulating locators/actions),
 *  - stable role/label/data-testid locators (never brittle CSS/XPath),
 *  - a smoke test (critical path) and a contract-driven validation test.
 *
 * Field-level validation cases can be data-driven from the QA cases file produced
 * by testcase_generator.py (see the loop at the bottom).
 *
 * Run:  npx playwright test
 */

import { test, expect, Page } from '@playwright/test';
import * as fs from 'fs';

// ---- Page Object: encapsulate the screen under test ------------------------
class OrderFormPage {
  constructor(private readonly page: Page) {}

  async goto() {
    await this.page.goto('/orders/new');
  }

  // Prefer role/label/testid locators — stable across refactors.
  field(name: string) {
    return this.page.getByLabel(name, { exact: false });
  }

  submit() {
    return this.page.getByRole('button', { name: /save|create|submit/i });
  }

  async fill(values: Record<string, string>) {
    for (const [name, value] of Object.entries(values)) {
      await this.field(name).fill(value);
    }
  }

  async submitForm() {
    await this.submit().click();
  }
}

// ---- Smoke: the critical path must work ------------------------------------
test('@smoke create order happy path', async ({ page }) => {
  const form = new OrderFormPage(page);
  await form.goto();
  await form.fill({ email: 'buyer@example.com', total_amount: '19.99' });
  // status has a default; leave it.
  await form.submitForm();

  // Expect a success signal and the new row visible in the list.
  await expect(page.getByText(/created|success/i)).toBeVisible();
  await page.goto('/orders');
  await expect(page.getByText('buyer@example.com')).toBeVisible();
});

// ---- Contract-driven: required field blocks submit -------------------------
test('required email blocks submit', async ({ page }) => {
  const form = new OrderFormPage(page);
  await form.goto();
  await form.fill({ total_amount: '19.99' }); // omit required email
  await form.submitForm();

  // The form should not navigate away and should surface a field error.
  await expect(page).toHaveURL(/orders\/new/);
  await expect(form.field('email')).toHaveAttribute('aria-invalid', 'true');
});

// ---- Data-driven from the QA cases file (optional) -------------------------
// Loads negative/required cases and asserts each blocks submission.
const CASES_FILE = process.env.QA_CASES_FILE || 'cases.json';
if (fs.existsSync(CASES_FILE)) {
  const cases: Array<{ id: string; table: string; attribute: string; technique: string }> =
    JSON.parse(fs.readFileSync(CASES_FILE, 'utf-8'));

  const requiredCases = cases.filter(
    (c) => c.table === 'order' && c.technique === 'negative/required',
  );

  for (const c of requiredCases) {
    test(`contract: ${c.id}`, async ({ page }) => {
      const form = new OrderFormPage(page);
      await form.goto();
      // Fill everything valid except the field under test, then expect an error.
      await form.fill({ email: 'buyer@example.com', total_amount: '19.99' });
      await form.field(c.attribute).fill('');
      await form.submitForm();
      await expect(form.field(c.attribute)).toHaveAttribute('aria-invalid', 'true');
    });
  }
}
