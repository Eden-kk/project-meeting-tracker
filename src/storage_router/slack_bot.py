"""Slack Socket Mode lifecycle + @mention handler.

Wired into the FastAPI app factory via :func:`start` (startup event) and
:func:`stop` (shutdown event). One outbound WebSocket from the router to
Slack — chosen so the bot survives tunnel-URL rotation that an Events
API setup would not.

Operating contract:

* If any of the three required env vars (``SLACK_BOT_TOKEN``,
  ``SLACK_APP_TOKEN``, ``SLACK_DEFAULT_CHANNEL_ID``) is unset on startup,
  the integration logs ``slack integration disabled (env not set)`` and
  stays dormant. Everything else in the router runs unchanged.
* The bot token is validated up front with a synchronous
  ``WebClient.auth_test`` so configuration errors fail fast at startup
  rather than hours later on first finalize.
* ``app_mention`` handler strips the leading ``<@U…>`` user-id, calls
  ``hermes_runtime.run_workspace_qa("ws_dev", text)`` in a worker thread
  (the LLM call is blocking and must not stall the asyncio loop), and
  replies in-thread. ``HermesUnavailable`` → one-line "Hermes is offline"
  reply; other failures → log + silent (no retry).
"""
from __future__ import annotations

import asyncio
import logging
import os
import re

log = logging.getLogger(__name__)

_MENTION_RE = re.compile(r"<@[UW][A-Z0-9]+>")


def _strip_mention(text: str) -> str:
    """Remove the leading ``<@U…>`` Slack user-id tag(s) from an event text."""
    return _MENTION_RE.sub("", text or "").strip()


def _env() -> dict[str, str | None]:
    return {
        "bot_token": os.environ.get("SLACK_BOT_TOKEN"),
        "app_token": os.environ.get("SLACK_APP_TOKEN"),
        "channel_id": os.environ.get("SLACK_DEFAULT_CHANNEL_ID"),
    }


def _required_present(env: dict[str, str | None]) -> bool:
    return bool(env["bot_token"] and env["app_token"] and env["channel_id"])


async def _handle_app_mention(event: dict, web_client) -> None:
    """Reply in-thread to an ``app_mention`` event.

    ``web_client`` is the AsyncWebClient bound to the SocketModeClient;
    we use it to post the reply. Failures here are logged WARN and
    swallowed — the bot must never crash the Socket Mode loop.
    """
    # Local imports keep module load cheap.
    from storage_router import hermes_runtime, slack_notifier

    text = _strip_mention(event.get("text") or "")
    channel = event.get("channel")
    thread_ts = event.get("thread_ts") or event.get("ts")
    if not channel or not thread_ts:
        log.warning("slack app_mention: missing channel or ts: %r", event)
        return
    if not text:
        try:
            await web_client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text="Ask me a question after the mention, e.g. *@hermes-bot what did we decide about X?*",
            )
        except Exception as e:  # noqa: BLE001
            log.warning("slack app_mention: empty-prompt reply failed: %s", e)
        return

    try:
        answer = await asyncio.to_thread(
            hermes_runtime.run_workspace_qa, "ws_dev", text
        )
    except hermes_runtime.HermesUnavailable as e:
        log.info("slack app_mention: hermes unavailable: %s", e)
        try:
            await web_client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text="Hermes is offline right now, try again in a moment.",
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("slack app_mention: 503 reply failed: %s", exc)
        return
    except Exception as e:  # noqa: BLE001
        log.exception("slack app_mention: workspace_qa crashed")
        try:
            await web_client.chat_postMessage(
                channel=channel,
                thread_ts=thread_ts,
                text=f"Something went wrong answering that: {e}",
            )
        except Exception as exc:  # noqa: BLE001
            log.warning("slack app_mention: error reply failed: %s", exc)
        return

    blocks = slack_notifier.render_qa_blocks(answer)
    fallback = (answer.get("final_text") or answer.get("answer") or "")[:300] or "Hermes reply"
    try:
        await web_client.chat_postMessage(
            channel=channel,
            thread_ts=thread_ts,
            blocks=blocks,
            text=fallback,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("slack app_mention: reply post failed: %s", e)


def _make_listener(web_client):
    """Build a SocketModeRequest listener bound to ``web_client``.

    The slack-sdk Socket Mode client invokes this callback for every
    incoming event; we ack immediately (Slack's 3-second budget) and
    then dispatch ``app_mention`` events to the async handler.
    """
    from slack_sdk.socket_mode.response import SocketModeResponse

    async def _listener(client, req) -> None:  # noqa: ANN001 — slack-sdk types
        # Always ack first — Slack closes the socket otherwise.
        try:
            await client.send_socket_mode_response(
                SocketModeResponse(envelope_id=req.envelope_id)
            )
        except Exception as e:  # noqa: BLE001
            log.warning("slack: ack failed: %s", e)

        if req.type != "events_api":
            return
        event = (req.payload or {}).get("event") or {}
        if event.get("type") != "app_mention":
            return
        # Ignore the bot's own messages echoed back as mentions.
        if event.get("bot_id"):
            return
        await _handle_app_mention(event, web_client)

    return _listener


async def start(app) -> None:
    """Startup hook. Validates env + token, spawns the Socket Mode task.

    No-ops when env is unset (logs once at INFO). Token validation uses
    the sync ``WebClient.auth_test`` from a worker thread so a typo /
    revoked token fails fast at startup rather than hours later on
    first @mention.
    """
    env = _env()
    if not _required_present(env):
        log.info("slack integration disabled (env not set)")
        app.state.slack_task = None
        return

    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError
    from slack_sdk.socket_mode.websockets import SocketModeClient
    from slack_sdk.web.async_client import AsyncWebClient

    bot_token: str = env["bot_token"]  # type: ignore[assignment]
    app_token: str = env["app_token"]  # type: ignore[assignment]

    # Fast-fail token validation.
    try:
        await asyncio.to_thread(lambda: WebClient(token=bot_token).auth_test())
    except SlackApiError as e:
        log.warning(
            "slack: auth_test failed (%s) — integration disabled this run",
            e.response.get("error") if getattr(e, "response", None) else e,
        )
        app.state.slack_task = None
        return
    except Exception as e:  # noqa: BLE001
        log.warning("slack: auth_test crashed (%s) — integration disabled this run", e)
        app.state.slack_task = None
        return

    async_web = AsyncWebClient(token=bot_token)
    client = SocketModeClient(app_token=app_token, web_client=async_web)
    client.socket_mode_request_listeners.append(_make_listener(async_web))

    async def _run() -> None:
        try:
            await client.connect()
            log.info("slack bot connected (socket mode)")
            # Block forever — disconnects are handled internally by slack-sdk.
            await asyncio.Event().wait()
        except asyncio.CancelledError:
            log.info("slack bot task cancelled")
            raise
        except Exception:  # noqa: BLE001
            log.exception("slack bot task crashed")
        finally:
            try:
                await client.close()
            except Exception:  # noqa: BLE001
                pass

    app.state.slack_task = asyncio.create_task(_run(), name="slack-socket-mode")
    app.state.slack_client = client


async def stop(app) -> None:
    """Shutdown hook. Cancels the Socket Mode task with a 5 s budget."""
    task = getattr(app.state, "slack_task", None)
    if task is None:
        return
    task.cancel()
    try:
        await asyncio.wait_for(task, timeout=5.0)
    except (asyncio.CancelledError, asyncio.TimeoutError):
        pass
    except Exception:  # noqa: BLE001
        log.exception("slack: stop encountered unexpected error")
    finally:
        app.state.slack_task = None
