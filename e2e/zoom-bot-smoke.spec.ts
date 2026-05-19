import { test, expect } from '@playwright/test';

/**
 * Wave 9 (zoom-bot) — manual smoke spec.
 *
 * Intentionally NOT part of the headless CI run. The spec requires
 * three operator-supplied env vars and a real Zoom meeting open in
 * the operator's Zoom client at the moment the spec executes:
 *
 *   E2E_ZOOM_URL      — full Zoom join URL (https://zoom.us/j/<n>?pwd=…)
 *   E2E_STORAGE_URL   — public base URL of the storage-router under test
 *   E2E_WORKSPACE_ID  — workspace to file the meeting under (default ws_dev)
 *
 * Run on-demand from the pod (where the bot's prereqs are installed):
 *
 *   E2E_ZOOM_URL='https://zoom.us/j/...' \
 *   E2E_STORAGE_URL='https://....proxy.runpod.net' \
 *   pnpm playwright test e2e/zoom-bot-smoke.spec.ts
 *
 * The spec opens the SPA, pastes the URL into ZoomUrlForm, clicks
 * Dispatch, and waits for the new meeting row to surface on
 * MeetingsPage with the "Zoom bot active" badge. The operator then
 * admits the bot manually in Zoom; the spec waits up to 3 minutes for
 * a live_summary to populate before asserting success.
 */

const REQUIRED = ['E2E_ZOOM_URL', 'E2E_STORAGE_URL'];
const missing = REQUIRED.filter((k) => !process.env[k]);

test.describe('zoom-bot smoke (manual)', () => {
  test.skip(
    missing.length > 0,
    `Skipping: set ${missing.join(', ')} to enable.`,
  );

  test('dispatch → bot joins → badge appears → live_summary populates', async ({
    page,
  }) => {
    test.setTimeout(5 * 60_000);

    const zoomUrl = process.env.E2E_ZOOM_URL!;
    const workspaceId = process.env.E2E_WORKSPACE_ID || 'ws_dev';

    // 1. Open the live page.
    await page.goto(`/ws/${workspaceId}/live`);
    await expect(page.getByTestId('zoom-url-form')).toBeVisible();

    // 2. Paste + dispatch.
    await page.getByLabel(/Zoom meeting URL/i).fill(zoomUrl);
    await page
      .getByRole('button', { name: /Dispatch Hermes/i })
      .click();

    // 3. Navigate to the meetings list; the new meeting should appear.
    await page.goto(`/ws/${workspaceId}/`);
    const badge = page.getByTestId('zoom-bot-active-badge').first();
    await expect(badge).toBeVisible({ timeout: 30_000 });

    // 4. Pause for the operator: admit the bot in Zoom.
    console.log(
      '[zoom-bot-smoke] Admit the bot in Zoom now; waiting up to 3 min for live_summary…',
    );

    // 5. Open the meeting and watch for live_summary to populate.
    await badge.click();
    await expect(page.getByTestId('live-summary-text')).toBeVisible({
      timeout: 3 * 60_000,
    });
  });
});
