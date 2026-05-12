"""Slack notifier — pure-logic Block Kit renderers + the synchronous
``notify_finalize`` post path used from ``hermes_runtime._finalize_inner``.

This module owns NO socket state. The Socket Mode lifecycle lives in
``slack_bot.py``; this module only knows how to render meeting data into
Slack Block Kit JSON and how to POST it with the sync ``WebClient``.

Two callers:

* ``hermes_runtime._finalize_inner`` (and the manual finalize route in
  ``qa_route``) spawn a non-daemon worker thread that calls
  :func:`notify_finalize`. ``WebClient`` is sync and thread-safe for
  one-shot calls, so no asyncio plumbing is needed.
* ``slack_bot.on_app_mention`` (asyncio event-loop context) calls
  :func:`render_qa_blocks` directly. It does the network reply itself
  via the async client.

If any of the three required Slack env vars (``SLACK_BOT_TOKEN``,
``SLACK_APP_TOKEN``, ``SLACK_DEFAULT_CHANNEL_ID``) is unset,
``notify_finalize`` returns immediately with one INFO log so finalize
never blocks on Slack config.
"""
from __future__ import annotations

import logging
import os
import re
from typing import Any

log = logging.getLogger(__name__)

# Card-type ordering for the threaded replies. Types with zero items are
# skipped entirely (no empty thread reply).
_FINALIZE_SECTIONS: list[tuple[str, str, list[str]]] = [
    # (heading, emoji, [card_types])
    ("Decisions", ":white_check_mark:", ["decision"]),
    ("Action items", ":memo:", ["action_item"]),
    ("Open questions", ":question:", ["open_question"]),
    ("Risks / pain points", ":warning:", ["risk", "pain_point"]),
]

# Citation patterns from `qa_route.qa_workspace` — keep in lockstep.
_CITE_CARD = re.compile(r"\[meeting:([^:\]]+):card:([^\]]+)\]")
_CITE_SEG = re.compile(r"\[meeting:([^:\]]+):seg:([^\]]+)\]")


def _env() -> dict[str, str | None]:
    """Snapshot Slack env vars. Read at call time so tests can monkeypatch."""
    return {
        "bot_token": os.environ.get("SLACK_BOT_TOKEN"),
        "app_token": os.environ.get("SLACK_APP_TOKEN"),
        "channel_id": os.environ.get("SLACK_DEFAULT_CHANNEL_ID"),
        "frontend_base_url": os.environ.get("SLACK_FRONTEND_BASE_URL", ""),
    }


def _required_present(env: dict[str, str | None]) -> bool:
    return bool(env["bot_token"] and env["app_token"] and env["channel_id"])


def _format_duration(started_at, ended_at) -> str | None:
    if started_at is None or ended_at is None:
        return None
    total = int((ended_at - started_at).total_seconds())
    if total < 0:
        return None
    h, rem = divmod(total, 3600)
    m, s = divmod(rem, 60)
    if h:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def _participants(session, meeting_id: str, meeting) -> list[str]:
    """Distinct speaker_name values from the meeting's segments, after
    applying ``meeting.speaker_label_map`` rewrites. Returns a stable
    ordered list capped at 8 names (long lists clutter the header).
    """
    from storage_router import storage

    label_map = meeting.speaker_label_map or {}
    try:
        transcript = storage.get_transcript(session, meeting_id)
    except Exception:  # noqa: BLE001 — defensive: notify must not crash.
        return []
    seen: set[str] = set()
    out: list[str] = []
    for seg in transcript.segments:
        sid = seg.speaker_id or ""
        name = label_map.get(sid) or seg.speaker_name or sid
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
        if len(out) >= 8:
            break
    return out


def _card_link(frontend_base_url: str, meeting_id: str, card) -> str:
    base = frontend_base_url.rstrip("/")
    if card.source_chunk_ids:
        return f"{base}/meetings/{meeting_id}#seg:{card.source_chunk_ids[0]}"
    return f"{base}/meetings/{meeting_id}"


def render_finalize_blocks(
    title: str,
    summary: str,
    participants: list[str],
    duration: str | None,
) -> list[dict]:
    """Build the top-level Block Kit payload for a finalized meeting.

    Threaded per-card-type replies are built separately by
    :func:`render_finalize_section_blocks` (one call per non-empty type).
    """
    title = (title or "Untitled meeting").strip()

    context_parts: list[str] = []
    if duration:
        context_parts.append(duration)
    context_parts.append("finalized just now")
    if participants:
        context_parts.append(", ".join(participants))
    context_text = " · ".join(context_parts)

    blocks: list[dict] = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f":clipboard: {title}"[:150]},
        },
        {
            "type": "context",
            "elements": [{"type": "mrkdwn", "text": context_text[:3000]}],
        },
    ]
    if summary:
        blocks.append(
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*Summary*\n{summary[:2800]}",
                },
            }
        )
    blocks.append(
        {
            "type": "context",
            "elements": [
                {
                    "type": "mrkdwn",
                    "text": (
                        "Replies in thread :arrow_heading_down:  ·  "
                        "Reply in thread to ask @hermes-bot about this meeting."
                    ),
                }
            ],
        }
    )
    return blocks


def render_finalize_section_blocks(
    heading: str,
    emoji: str,
    cards: list,
    meeting_id: str,
    frontend_base_url: str,
) -> list[dict]:
    """One Slack section block per card-type group: heading + bullet list."""
    lines: list[str] = []
    for c in cards[:25]:  # safety cap to keep the message under Slack's 3 KB section limit
        link = _card_link(frontend_base_url, meeting_id, c)
        title = (c.title or "").strip() or "(untitled)"
        lines.append(f"• <{link}|{title}>")
    body = "\n".join(lines)
    return [
        {
            "type": "section",
            "text": {
                "type": "mrkdwn",
                "text": f"{emoji} *{heading}* ({len(cards)})\n{body}",
            },
        }
    ]


def render_qa_blocks(answer: dict, frontend_base_url: str | None = None) -> list[dict]:
    """Rewrite citation tags in ``answer['final_text']`` into clickable
    Slack links and return a single-section Block Kit payload.

    Citation shapes (from ``run_workspace_qa``):
        [meeting:<mid>:card:<cid>]   → /meetings/<mid>
        [meeting:<mid>:seg:<sid>]    → /meetings/<mid>#seg:<sid>

    Malformed / unrecognised tags pass through unchanged so the user
    still sees the answer text — never raise on a bad citation.
    """
    text = answer.get("final_text") or answer.get("answer") or ""
    base = (frontend_base_url or os.environ.get("SLACK_FRONTEND_BASE_URL") or "").rstrip("/")

    def _seg_repl(m: re.Match[str]) -> str:
        mid, sid = m.group(1), m.group(2)
        return f"<{base}/meetings/{mid}#seg:{sid}|:arrow_upper_right: source>"

    def _card_repl(m: re.Match[str]) -> str:
        mid, _cid = m.group(1), m.group(2)
        return f"<{base}/meetings/{mid}|:arrow_upper_right: source>"

    rewritten = _CITE_SEG.sub(_seg_repl, text)
    rewritten = _CITE_CARD.sub(_card_repl, rewritten)
    # Slack section text caps at 3000 chars; truncate defensively.
    if len(rewritten) > 2900:
        rewritten = rewritten[:2900] + "…"
    return [
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": rewritten or "(empty answer)"},
        }
    ]


def notify_finalize(meeting_id: str) -> None:
    """POST a Block Kit summary for the just-finalized meeting.

    Opens its own ``SessionLocal()`` because this runs in a worker thread
    spawned from ``_finalize_inner`` after the request-scoped session has
    closed. Mirrors the ``hermes_runtime.auto_finalize_meeting`` pattern.

    Failures (network, bot-not-in-channel, channel-not-found, etc.) are
    logged at WARN and never raised — the meeting is already finalized
    in the DB and Slack is a best-effort side-channel.
    """
    env = _env()
    if not _required_present(env):
        log.info("slack notify_finalize: integration disabled (env not set)")
        return

    # Local imports keep module load cheap and avoid circularity.
    from slack_sdk import WebClient

    from storage_router import storage
    from storage_router.db import SessionLocal
    from storage_router.models.db import MeetingRow

    bot_token: str = env["bot_token"]  # type: ignore[assignment]
    channel_id: str = env["channel_id"]  # type: ignore[assignment]
    frontend_base_url: str = env["frontend_base_url"] or ""

    # Snapshot everything we need from the DB up front so we don't hold a
    # session across blocking Slack calls.
    with SessionLocal() as session:
        meeting = session.get(MeetingRow, meeting_id)
        if meeting is None:
            log.warning("slack notify_finalize: meeting %s missing", meeting_id)
            return
        title = meeting.title or ""
        summary = meeting.finalized_summary or ""
        duration = _format_duration(meeting.started_at, meeting.ended_at)
        participants = _participants(session, meeting_id, meeting)
        cards_by_type: dict[str, list[Any]] = {}
        # One query per card type — types are small (≤6) and this keeps
        # ordering stable without an extra group-by.
        for _heading, _emoji, types in _FINALIZE_SECTIONS:
            for t in types:
                rows, _total = storage.list_meeting_cards(
                    session, meeting_id=meeting_id, type=t, limit=50
                )
                cards_by_type[t] = list(rows)

    client = WebClient(token=bot_token)
    top_blocks = render_finalize_blocks(title, summary, participants, duration)
    fallback = f"Meeting finalized: {title or meeting_id}"

    try:
        resp = client.chat_postMessage(
            channel=channel_id, blocks=top_blocks, text=fallback
        )
    except Exception as e:  # noqa: BLE001 — SlackApiError, network, DNS.
        log.warning(
            "slack notify_finalize: top-level post failed (meeting=%s): %s",
            meeting_id,
            e,
        )
        return

    thread_ts = resp.get("ts") if hasattr(resp, "get") else None
    if not thread_ts:
        log.warning("slack notify_finalize: top-level post returned no ts")
        return

    # Persist the thread ts before posting replies so a mid-sequence
    # crash still leaves the meeting linked to the existing thread.
    try:
        with SessionLocal() as session:
            m = session.get(MeetingRow, meeting_id)
            if m is not None:
                m.slack_thread_ts = thread_ts
                session.commit()
    except Exception:  # noqa: BLE001
        log.exception(
            "slack notify_finalize: failed to persist slack_thread_ts (meeting=%s)",
            meeting_id,
        )

    for heading, emoji, types in _FINALIZE_SECTIONS:
        section_cards: list = []
        for t in types:
            section_cards.extend(cards_by_type.get(t, []))
        if not section_cards:
            continue
        section_blocks = render_finalize_section_blocks(
            heading, emoji, section_cards, meeting_id, frontend_base_url
        )
        try:
            client.chat_postMessage(
                channel=channel_id,
                thread_ts=thread_ts,
                blocks=section_blocks,
                text=f"{heading} ({len(section_cards)})",
            )
        except Exception as e:  # noqa: BLE001
            log.warning(
                "slack notify_finalize: thread reply failed (meeting=%s, section=%s): %s",
                meeting_id,
                heading,
                e,
            )
