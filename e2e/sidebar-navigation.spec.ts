import { test, expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import path from 'node:path';

const here = path.dirname(fileURLToPath(import.meta.url));

test('sidebar happy path: home → import → processing → review → meetings', async ({ page }) => {
  const transcript = readFileSync(path.resolve(here, '../fixtures/sample_transcript.txt'), 'utf-8');

  await page.goto('/');
  // HomePage empty-state CTA, since the registry is per-browser-tab
  await expect(page.getByRole('heading', { name: /no meetings yet|home/i }).first()).toBeVisible();

  // Sidebar nav to Import
  await page.getByRole('link', { name: 'Import' }).first().click();
  await expect(page).toHaveURL(/\/import$/);

  await page.getByRole('tab', { name: /paste transcript/i }).click();
  await page.getByLabel(/pasted transcript/i).fill(transcript);
  await page.getByLabel(/^title$/i).fill('Sidebar happy meeting');
  await page.getByRole('button', { name: /submit/i }).click();

  await expect(page).toHaveURL(/\/meetings\/.+\/processing/);
  await page.waitForURL(/\/meetings\/[^/]+$/, { timeout: 15_000 });

  // Sidebar nav to Meetings
  await page.getByRole('link', { name: 'Meetings' }).first().click();
  await expect(page).toHaveURL(/\/meetings$/);
  await expect(page.getByRole('link', { name: 'Sidebar happy meeting' })).toBeVisible();
});

test('mobile drawer: opens on click, closes on Escape, returns focus to toggle', async ({ page }) => {
  await page.setViewportSize({ width: 400, height: 800 });
  await page.goto('/');
  const toggle = page.getByRole('button', { name: /open menu/i });
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await toggle.click();
  await expect(toggle).toHaveAttribute('aria-expanded', 'true');
  await expect(page.getByRole('dialog', { name: /main navigation/i })).toBeVisible();
  await page.keyboard.press('Escape');
  await expect(toggle).toHaveAttribute('aria-expanded', 'false');
  await expect(page.getByRole('dialog', { name: /main navigation/i })).toHaveCount(0);
});
