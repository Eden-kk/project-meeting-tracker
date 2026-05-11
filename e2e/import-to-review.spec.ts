import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));

test('import → processing → review happy path', async ({ page }) => {
  const transcript = readFileSync(path.resolve(here, '../fixtures/sample_transcript.txt'), 'utf-8');

  await page.goto('/');
  await page.getByRole('tab', { name: /paste transcript/i }).click();
  await page.getByLabel(/pasted transcript/i).fill(transcript);
  await page.getByLabel(/^title$/i).fill('E2E happy');
  await page.getByRole('button', { name: /submit/i }).click();

  await expect(page).toHaveURL(/\/meetings\/.+\/processing/);
  await page.waitForURL(/\/meetings\/[^/]+$/, { timeout: 15_000 });

  const rows = page.getByTestId('transcript-row');
  await expect(rows).toHaveCount(6);

  for (const name of [/memory cards/i, /ask hermes/i, /share \/ export/i]) {
    await expect(page.getByRole('tab', { name })).toHaveAttribute('aria-disabled', 'true');
  }
});
