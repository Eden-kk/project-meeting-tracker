import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));

test('delete meeting → row disappears → detail URL shows not found', async ({ page }) => {
  const transcript = readFileSync(path.resolve(here, '../fixtures/sample_transcript.txt'), 'utf-8');

  // Import a meeting so there is a known row on the meetings list.
  await page.goto('/import');
  await page.getByRole('tab', { name: /paste transcript/i }).click();
  await page.getByLabel(/pasted transcript/i).fill(transcript);
  await page.getByLabel(/^title$/i).fill('E2E delete test');
  await page.getByRole('button', { name: /submit/i }).click();

  // Wait for processing to finish and land on the review page.
  await page.waitForURL(/\/meetings\/[^/]+$/, { timeout: 15_000 });

  // Capture the meeting id from the URL before navigating away.
  const reviewUrl = page.url();
  const meetingId = reviewUrl.match(/\/meetings\/([^/?#]+)/)?.[1] ?? '';
  expect(meetingId).toBeTruthy();

  // Capture workspace id from the URL.
  const wsId = reviewUrl.match(/\/ws\/([^/?#]+)/)?.[1] ?? 'ws_dev';

  // Go to the meetings list.
  await page.goto(`/ws/${wsId}/meetings`);
  await expect(page.getByRole('link', { name: 'E2E delete test' })).toBeVisible();

  // Open the delete dialog for this row.
  await page.getByRole('button', { name: /delete E2E delete test/i }).click();
  await expect(page.getByRole('dialog')).toBeVisible();

  // Confirm deletion.
  await page.getByRole('button', { name: /^delete$/i }).click();

  // Row must vanish from the list.
  await expect(page.getByRole('link', { name: 'E2E delete test' })).not.toBeVisible();

  // Navigating directly to the detail URL must show the not-found state.
  await page.goto(`/ws/${wsId}/meetings/${meetingId}`);
  await expect(page.getByText(/meeting not found/i)).toBeVisible();
});
