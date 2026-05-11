"""Wave 4.1 — cross-meeting FTS search over speaker_segments.

Uses live Postgres; the generated `search_tsv` column is populated by the
DB at insert time, so no app-side priming is required.
"""
from __future__ import annotations

from sqlalchemy import text as sql_text

from storage_router.db import SessionLocal
from storage_router.models.db import SpeakerSegmentRow
from storage_router.storage import create_artifact, create_meeting


def _seed_meeting(title: str = "M1", workspace_id: str = "ws_dev", created_by: str = "u_dev") -> str:
    with SessionLocal() as s:
        a = create_artifact(
            s,
            workspace_id=workspace_id,
            source_type="pasted_transcript",
            capture_mode="imported",
            title=title,
            created_by=created_by,
            raw_text="hi",
        )
        m = create_meeting(s, artifact_id=a.id, title=title)
        s.commit()
        return m.id


def _seed_segment(meeting_id: str, sid: str, text: str, speaker: str = "Alice") -> None:
    with SessionLocal() as s:
        s.add(
            SpeakerSegmentRow(
                id=sid,
                meeting_id=meeting_id,
                speaker_id=speaker.lower(),
                speaker_name=speaker,
                start_ms=0,
                end_ms=5000,
                text=text,
                confidence=0.9,
                source_type="pasted_transcript",
                is_final=True,
            )
        )
        s.commit()


async def test_search_transcripts_returns_matching_segments(client) -> None:
    m1 = _seed_meeting("Architecture review")
    m2 = _seed_meeting("Standup")
    _seed_segment(m1, "seg_a", "We chose Postgres for memory storage")
    _seed_segment(m1, "seg_b", "Tomorrow we deploy the new frontend")
    _seed_segment(m2, "seg_c", "Coffee chat about the weather")

    r = await client.get(
        "/api/search/transcripts",
        params={"q": "postgres", "workspace_id": "ws_dev"},
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 1
    hit = body["items"][0]
    assert hit["segment_id"] == "seg_a"
    assert hit["meeting_id"] == m1
    assert hit["meeting_title"] == "Architecture review"
    assert "Postgres" in hit["text"]


async def test_search_transcripts_scoped_to_workspace(client) -> None:
    # Seed second workspace + meeting
    with SessionLocal() as s:
        s.execute(
            sql_text(
                "INSERT INTO workspaces (id, name) VALUES ('ws_other','Other') "
                "ON CONFLICT (id) DO NOTHING"
            )
        )
        s.execute(
            sql_text(
                "INSERT INTO users (id, workspace_id, email, display_name) "
                "VALUES ('u_other','ws_other','o@x.test','O') ON CONFLICT (id) DO NOTHING"
            )
        )
        s.commit()
    m1 = _seed_meeting("M1")
    _seed_segment(m1, "seg_in", "vector search is deferred")
    m2 = _seed_meeting("X", workspace_id="ws_other", created_by="u_other")
    _seed_segment(m2, "seg_other", "vector search is amazing")

    r = await client.get(
        "/api/search/transcripts",
        params={"q": "vector", "workspace_id": "ws_dev"},
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 1
    assert body["items"][0]["meeting_id"] == m1


async def test_search_transcripts_empty_q_422(client) -> None:
    r = await client.get(
        "/api/search/transcripts",
        params={"q": "", "workspace_id": "ws_dev"},
    )
    assert r.status_code == 422


async def test_search_transcripts_no_match_returns_empty(client) -> None:
    m = _seed_meeting()
    _seed_segment(m, "seg_x", "hello there")
    r = await client.get(
        "/api/search/transcripts",
        params={"q": "nonexistentwordxyz", "workspace_id": "ws_dev"},
    )
    assert r.status_code == 200
    assert r.json() == {"items": [], "total": 0}


async def test_search_transcripts_pagination(client) -> None:
    m = _seed_meeting()
    for i in range(5):
        _seed_segment(m, f"seg_p{i}", f"deployment plan number {i}")
    r = await client.get(
        "/api/search/transcripts",
        params={
            "q": "deployment",
            "workspace_id": "ws_dev",
            "limit": 2,
            "offset": 0,
        },
    )
    assert r.status_code == 200
    body = r.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2
