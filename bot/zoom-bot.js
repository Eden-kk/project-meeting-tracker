// zoom-bot.js — Puppeteer driver for the Hermes Zoom bot (Slice 3).
//
// Spawned by bot.py with these env vars:
//   ZOOM_URL              the join URL to navigate to
//   MEETING_ID            storage-router meeting_id (used by zoom-host.html for JWT fetch)
//   STORAGE_ROUTER_URL    base URL the host page calls for the SDK JWT
//   BOT_SINK_NAME         PulseAudio sink name (we tell Chromium to use it)
//   BOT_DISPLAY_NAME      "Hermes — Note-taking Bot"
//
// On success the page resolves window.__joinPromise after ZoomMtg.join()
// returns; on meeting end the in-meeting service listener fires and we
// exit 0 so bot.py can call /end.
//
// IMPORTANT: this script is intentionally thin — all "real" SDK plumbing
// lives in zoom-host.html (which is what the SDK example apps use).

const path = require('path');
const puppeteer = require('puppeteer');

const ZOOM_URL = process.env.ZOOM_URL;
const STORAGE_ROUTER_URL = process.env.STORAGE_ROUTER_URL;
const BOT_SINK_NAME = process.env.BOT_SINK_NAME;
const DISPLAY_NAME = process.env.BOT_DISPLAY_NAME || 'Hermes — Note-taking Bot';

if (!ZOOM_URL || !STORAGE_ROUTER_URL || !BOT_SINK_NAME) {
  console.error('FATAL: ZOOM_URL, STORAGE_ROUTER_URL, BOT_SINK_NAME must be set');
  process.exit(2);
}

(async () => {
  const browser = await puppeteer.launch({
    headless: 'new',
    args: [
      '--no-sandbox',
      '--disable-setuid-sandbox',
      '--use-fake-ui-for-media-stream',
      // Route the in-meeting audio output into our per-bot sink.
      `--alsa-output-device=${BOT_SINK_NAME}`,
    ],
  });

  const page = await browser.newPage();
  await page.goto(`file://${path.resolve(__dirname, 'zoom-host.html')}`);

  // Hand the join params to the page; zoom-host.html does the JWT fetch
  // + ZoomMtg.join() call. Resolves on ZoomMtg.inMeetingServiceListener
  // 'onMeetingEnd'.
  const exitCode = await page.evaluate(
    async (zoomUrl, storageRouterUrl, displayName) => {
      try {
        return await window.joinMeeting(zoomUrl, displayName, storageRouterUrl);
      } catch (err) {
        console.error('joinMeeting error:', err);
        return 5;
      }
    },
    ZOOM_URL,
    STORAGE_ROUTER_URL,
    DISPLAY_NAME,
  );

  await browser.close();
  process.exit(typeof exitCode === 'number' ? exitCode : 0);
})().catch((err) => {
  console.error('zoom-bot.js fatal:', err);
  process.exit(6);
});
