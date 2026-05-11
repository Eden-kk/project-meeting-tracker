import { test, expect } from '@playwright/test';

/**
 * Wave 6.1 e2e for the /live page.
 *
 * The real `MediaRecorder` + `getUserMedia` chain can't run in headless
 * Chromium without a fake media stream and a permissions grant, so this
 * spec asserts the surface that _does_ render: the page mounts, the
 * sidebar exposes the route, and the title input + start button are wired
 * up. The full capture path is verified manually via the handbook.
 */

test('sidebar exposes the Live entry and the page renders idle controls', async ({
  page,
}) => {
  await page.goto('/');

  await page.getByRole('link', { name: 'Live' }).first().click();
  await expect(page).toHaveURL(/\/live$/);

  await expect(
    page.getByRole('heading', { name: /live meeting/i }),
  ).toBeVisible();
  await expect(
    page.getByRole('button', { name: /start meeting/i }),
  ).toBeVisible();
  await expect(page.getByLabel(/title/i)).toHaveValue('Live meeting');

  // We don't click "Start meeting" — that triggers getUserMedia, which
  // browsers prompt or reject in headless mode. The unit test covers the
  // idle-render contract; the manual handbook covers the full capture.
});
