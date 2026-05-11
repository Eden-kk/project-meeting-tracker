import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));

test('memory cards review + ask hermes happy path', async ({ page }) => {
  const transcript = readFileSync(
    path.resolve(here, '../fixtures/sample_transcript.txt'),
    'utf-8',
  );

  await page.goto('/import');
  await page.getByRole('tab', { name: /paste transcript/i }).click();
  await page.getByLabel(/pasted transcript/i).fill(transcript);
  await page.getByLabel(/^title$/i).fill('E2E memory cards');
  await page.getByRole('button', { name: /submit/i }).click();

  await expect(page).toHaveURL(/\/meetings\/.+\/processing/);
  await page.waitForURL(/\/meetings\/[^/]+$/, { timeout: 15_000 });

  // 1. Switch to Memory Cards tab and assert seeded cards render.
  await page.getByRole('tab', { name: /memory cards/i }).click();
  const cards = page.getByTestId('memory-card-item');
  await expect(cards).toHaveCount(4);

  // 2. Filter to Draft → 3 cards.
  const stateRow = page.getByText('State', { exact: false }).locator('..');
  await stateRow.getByRole('button', { name: /^draft$/i }).click();
  await expect(cards).toHaveCount(3);

  // 3. Switch back to All so the approved card stays visible after committing,
  //    then approve a specific draft card (locked by data-card-id) and assert
  //    its pill flips to Committed.
  await stateRow.getByRole('button', { name: /^all$/i }).click();
  await expect(cards).toHaveCount(4);
  const draftAttr = await page
    .getByTestId('memory-card-item')
    .filter({ has: page.getByRole('button', { name: /approve/i }) })
    .first()
    .getAttribute('data-card-id');
  expect(draftAttr).not.toBeNull();
  const targetCard = page.locator(`[data-card-id="${draftAttr}"]`);
  await targetCard.getByRole('button', { name: /approve/i }).click();
  await expect(targetCard.getByText(/committed/i)).toBeVisible();

  // After committing, refiltering to Draft drops to 2.
  await stateRow.getByRole('button', { name: /^draft$/i }).click();
  await expect(cards).toHaveCount(2);

  // 4. Switch to Ask Hermes; ask a strong question.
  await page.getByRole('tab', { name: /ask hermes/i }).click();
  const textarea = page.getByLabel(/ask hermes/i);
  await textarea.fill('what was decided?');
  await page.getByRole('button', { name: /send/i }).click();

  await expect(page.getByText(/auth migration/i)).toBeVisible();
  await expect(page.getByTestId('evidence-pill').first()).toBeVisible();

  // 5. Ask a weak question → low-confidence chip appears.
  await textarea.fill('weak signal please');
  await page.getByRole('button', { name: /send/i }).click();
  await expect(page.getByTestId('low-confidence-chip').first()).toBeVisible();
});
