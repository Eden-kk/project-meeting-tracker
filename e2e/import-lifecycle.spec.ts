import { test, expect } from '@playwright/test';

test('offline harness does not expose model-capable routes', async ({ request }) => {
  const schema = await (await request.get('/openapi.json')).json();
  expect(Object.keys(schema.paths).filter(path => path.startsWith('/api/')).sort()).toEqual([
    '/api/conversations/import', '/api/meetings', '/api/meetings/{meeting_id}',
    '/api/meetings/{meeting_id}/import-job', '/api/meetings/{meeting_id}/import-job/cancel',
    '/api/meetings/{meeting_id}/import-job/retry', '/api/meetings/{meeting_id}/memory-cards',
    '/api/meetings/{meeting_id}/transcript', '/api/workspaces',
  ].sort());
  expect((await request.post('/api/qa/workspace', { data: {} })).ok()).toBe(false);
});

test('real API and PostgreSQL: import, cancel, reopen, retry, review', async ({ page }) => {
  await page.goto('/ws/ws_dev/import');
  await page.getByRole('tab', { name: /paste transcript/i }).click();
  await page.getByLabel(/pasted transcript/i).fill('Synthetic offline demo');
  await page.getByLabel(/^title$/i).fill('Lifecycle demo');
  await page.getByRole('button', { name: /submit/i }).click();
  await expect(page).toHaveURL(/\/processing$/);
  const processing = page.url();
  await page.getByRole('button', { name: 'Cancel import' }).click();
  await expect(page.getByText('Import cancelled locally.')).toBeVisible();
  // Simulate entering the normal library link instead of the processing URL.
  await page.goto(processing.replace('/processing', ''));
  await expect(page).toHaveURL(/\/processing$/);
  const retry = page.getByRole('button', { name: 'Retry import' });
  await expect(retry).toBeDisabled();
  await page.screenshot({ path: test.info().outputPath('cancelled.png'), fullPage: true });
  // Wait for this harness's known 3-second fake request to finish. Production
  // users must verify their provider separately; cancellation does not stop it.
  await page.waitForTimeout(3500);
  await page.getByRole('checkbox', { name: /previous remote job has stopped/i }).check();
  await retry.click();
  await expect(page).toHaveURL(/\/meetings\/[^/]+$/, { timeout: 15_000 });
  await expect(page.getByTestId('transcript-row')).toHaveCount(6);
  await page.screenshot({ path: test.info().outputPath('review.png'), fullPage: true });
});
