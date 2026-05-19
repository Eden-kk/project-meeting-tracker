# Hermes Zoom bot

Headless Chromium driver that joins a Zoom meeting as a participant
named **"Hermes — Note-taking Bot"** and streams audio chunks back to
the storage-router. Audio is captured via a per-bot PulseAudio
null-sink (concurrent bots can't cross-contaminate); each chunk lands
at the same `POST /api/live-meetings/{id}/audio-chunk` endpoint the
SPA's browser-mic flow already uses, so the downstream live ticks
(summary / extraction / topic-tracker / interview-questioner) work
without any changes.

The bot is spawned automatically by
`storage_router.zoom_bot_dispatcher` when the SPA POSTs to
`/api/zoom-bot/dispatch`. It can also be run standalone for smoke
testing (see below).

## One-time prereqs on the host

```bash
# System packages: pulseaudio (for the null-sink + monitor), ffmpeg
# (for the chunk slicer), chromium (Puppeteer can download its own —
# you don't strictly need this), node >=18.
apt-get install -y pulseaudio ffmpeg chromium node
pulseaudio --start  # if not already running

# npm deps (Puppeteer + a few helpers):
cd bot && npm install
```

## Required env vars

| Var | Purpose |
|---|---|
| `MEETING_ID` | storage-router meeting_id (target of upload) |
| `ZOOM_URL` | full Zoom join URL (`https://zoom.us/j/<n>?pwd=...`) |
| `STORAGE_ROUTER_URL` | base URL the bot calls back into |
| `ZOOM_BOT_ACCOUNT_EMAIL` | informational only (shows up as the bot's profile suffix) |

The Zoom Marketplace credentials (`ZOOM_SDK_KEY`, `ZOOM_SDK_SECRET`)
live on the storage-router, NOT in the bot — the bot fetches a fresh
SDK JWT from `POST /api/zoom-bot/sdk-jwt` on every join. This means
secrets never touch the bot's process.

## Smoke test

1. Start a real Zoom meeting in your client.
2. Run the bot from the worktree root:
   ```bash
   export MEETING_ID=smoke_$(date +%s)
   export ZOOM_URL='https://zoom.us/j/85412345678?pwd=abc'
   export STORAGE_ROUTER_URL='https://<your-storage-router-base>'
   python bot/bot.py
   ```
3. Within ~5 s the bot appears in Zoom's waiting room. Admit it.
4. Speak. `chunk-NNNN.webm` files appear in `$BOT_CHUNK_DIR` (a
   tempdir by default) and 202s are logged on every successful upload.
5. After ~2 min the SPA's live view for that meeting shows
   `live_summary` populating; speaker labels arrive as the diarization
   gate releases.
6. Hang up the Zoom call. The bot drains its final chunk, calls
   `POST /api/live-meetings/{MEETING_ID}/end`, and exits 0.

## Exit codes

| Code | Meaning |
|---|---|
| `0` | Clean exit — Zoom emitted `onMeetingEnd` and the bot finished gracefully. |
| `2` | Host did not admit the bot within `not_admitted_timeout_s` (default 5 min). The dispatcher marks `last_finalize_error='not_admitted'`. |
| `3` | ffmpeg crashed mid-meeting. |
| `4` | Startup prereq missing (pactl / node / ffmpeg). |
| `5` | `ZoomMtg.join()` rejected — usually means Zoom refused the join (anti-bot detection or bad creds). |
| `6` | Puppeteer / Node fatal. |

## Fallback if Zoom rejects headless Chromium

Zoom occasionally hardens against headless detection. When that
happens, exit code `5` surfaces with a specific Zoom SDK error. The
documented fallback is to swap the Web SDK driver for the
[Native Linux Meeting SDK](https://developers.zoom.us/docs/meeting-sdk/linux/)
(C++ binding; ~1–2 weeks of work). That option is deliberately out
of scope for v1 — keep the Web SDK path as the primary and treat
exit-5 as the canary.
