import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));

test('import → processing → review happy path', async ({ page }) => {
  const transcript = readFileSync(path.resolve(here, '../fixtures/sample_transcript.txt'), 'utf-8');

  await page.goto('/import');
  await page.getByRole('tab', { name: /paste transcript/i }).click();
  await page.getByLabel(/pasted transcript/i).fill(transcript);
  await page.getByLabel(/^title$/i).fill('E2E happy');
  await page.getByRole('button', { name: /submit/i }).click();

  await expect(page).toHaveURL(/\/meetings\/.+\/processing/);
  await page.waitForURL(/\/meetings\/[^/]+$/, { timeout: 15_000 });

  const rows = page.getByTestId('transcript-row');
  await expect(rows).toHaveCount(6);

  // Phase 2: only Share / Export remains disabled; Memory Cards + Ask Hermes
  // are activated by worktree H (memory-cards-frontend).
  await expect(page.getByRole('tab', { name: /share \/ export/i })).toHaveAttribute(
    'aria-disabled',
    'true',
  );
});
