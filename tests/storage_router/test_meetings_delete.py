"""DELETE /api/meetings/{meeting_id} — soft-delete endpoint tests."""
from __future__ import annotations

from storage_router.db import SessionLocal
from storage_router.models.db import MemoryCardRow, SpeakerSegmentRow
from storage_router.storage import create_artifact, create_meeting, create_memory_card


def _seed_meeting(*, raw_file_url: str | None = None) -> str:
    with SessionLocal() as s:
        a = create_artifact(
            s,
            workspace_id="ws_dev",
            source_type="pasted_transcript",
            capture_mode="imported",
            title="T",
            created_by="u_dev",
            raw_file_url=raw_file_url,
            raw_text="hi",
        )
        m = create_meeting(s, artifact_id=a.id, title="T")
        s.commit()
        return m.id


async def test_delete_meeting_sets_deleted_at(client) -> None:
    mid = _seed_meeting()
    with SessionLocal() as s:
        s.add(
            SpeakerSegmentRow(
                id="seg_del1",
                meeting_id=mid,
                speaker_id="alice",
                speaker_name="Alice",
                start_ms=0,
                end_ms=1000,
                text="hello",
                confidence=0.9,
                source_type="pasted_transcript",
                is_final=True,
            )
        )
        s.add(
            MemoryCardRow(
                id="card_del1",
                meeting_id=mid,
                type="decision",
                title="Ship it",
                content="yes",
                source_chunk_ids=["c1"],
                confidence=0.8,
            )
        )
        s.commit()

    resp = await client.delete(f"/api/meetings/{mid}")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["meeting_id"] == mid
    assert body["deleted_at"] is not None

    # child rows NOT cascaded
    with SessionLocal() as s:
        seg = s.get(SpeakerSegmentRow, "seg_del1")
        card = s.get(MemoryCardRow, "card_del1")
        assert seg is not None
        assert card is not None


async def test_delete_meeting_excludes_from_list(client) -> None:
    mid = _seed_meeting()
    await client.delete(f"/api/meetings/{mid}")

    resp = await client.get("/api/meetings", params={"workspace_id": "ws_dev"})
    assert resp.status_code == 200
    ids = [m["meeting_id"] for m in resp.json()["items"]]
    assert mid not in ids


async def test_delete_meeting_404_when_missing(client) -> None:
    resp = await client.delete("/api/meetings/m_does_not_exist")
    assert resp.status_code == 404


async def test_delete_meeting_409_when_already_deleted(client) -> None:
    mid = _seed_meeting()
    r1 = await client.delete(f"/api/meetings/{mid}")
    assert r1.status_code == 200

    r2 = await client.delete(f"/api/meetings/{mid}")
    assert r2.status_code == 409
    body = r2.json()
    assert body["error"]["code"] == "already_deleted"


async def test_delete_meeting_unlinks_blob(client, tmp_path) -> None:
    blob = tmp_path / "blob.bin"
    blob.write_bytes(b"data")

    mid = _seed_meeting(raw_file_url=blob.as_uri())

    resp = await client.delete(f"/api/meetings/{mid}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["blob_removed"] is True
    assert not blob.exists()


async def test_delete_meeting_blob_missing_returns_false(client, tmp_path) -> None:
    blob = tmp_path / "blob.bin"
    blob.write_bytes(b"data")

    mid = _seed_meeting(raw_file_url=blob.as_uri())
    blob.unlink()

    resp = await client.delete(f"/api/meetings/{mid}")
    assert resp.status_code == 200, resp.text
    assert resp.json()["blob_removed"] is False
