# Pending meeting uploads (post-pod-rebuild)

Requested 2026-05-22. Upload after the new durable pod is up + the
`moss` and `ambient agent` workspaces exist. Files live on the user's
Mac (paths below) — they must be transferred to the pod or uploaded via
the SPA import UI (the agent cannot read the user's local disk).

Verify after each: the generated **summary** reads as a narrative (not
"Created N cards…") and the **memory cards** look right.

OpenAI key: provided by user 2026-05-22 — store in the pod's
`/workspace/app/.env.local` as `OPENAI_API_KEY` (do NOT commit).

## Workspace: ambient agent

| Meeting | Source file (on Mac) | Type |
|---|---|---|
| sync-0514 | `/Users/yvette/Downloads/GMT20260514-212646_Recording.transcript.vtt` | transcript (vtt) |
| sync-0518 | `/Users/yvette/Downloads/audio1367051673.m4a` | audio (m4a) |
| sync-0521 (part 1) | `/Users/yvette/Documents/Zoom/2026-05-21 15.32.22 Yiting Dai's Zoom Meeting/video1438949390.mp4` | video (mp4) |
| sync-0521 (part 2) | `/Users/yvette/Downloads/GMT20260521-230635_Recording.transcript.vtt` | transcript (vtt) |

**Special handling:** sync-0521-1 (mp4) and sync-0521-2 (vtt) are the
SAME meeting and must be merged into ONE `sync-0521` meeting (not two
separate meetings). Approach TBD — likely import one as the base meeting
and fold the other's transcript/cards in, or concatenate sources before
finalize.

## Workspace: moss

| Meeting | Source file (on Mac) | Type |
|---|---|---|
| interview-finance | `/Users/yvette/Library/Application Support/zoom.us/data/UnifyWebView_Download/GMT20260507-213848_Recording.transcript_0.vtt` | transcript (vtt) |

## Status

- [ ] New durable pod up + healthy
- [ ] Workspaces `moss` + `ambient agent` created
- [ ] Files transferred from Mac (await user / SPA upload)
- [ ] ambient agent: sync-0514, sync-0518, sync-0521 (merged)
- [ ] moss: interview-finance
- [ ] Summaries + cards verified
