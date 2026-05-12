"""Slack notifier citation-rewriter unit tests.

Pure-logic tests for ``slack_notifier.render_qa_blocks``: makes sure
the ``[meeting:<mid>:card:<cid>]`` / ``[meeting:<mid>:seg:<sid>]`` tags
emitted by ``hermes_runtime.run_workspace_qa`` become clickable Slack
links and that malformed tags pass through unchanged rather than
crashing the reply path.
"""
from __future__ import annotations

from storage_router.slack_notifier import render_qa_blocks


def _section_text(blocks: list[dict]) -> str:
    # render_qa_blocks always returns a single section block.
    assert len(blocks) == 1, blocks
    return blocks[0]["text"]["text"]


def test_render_qa_blocks_rewrites_card_citation():
    answer = {
        "final_text": "We decided to ship next Tuesday [meeting:m1:card:c1].",
    }
    text = _section_text(render_qa_blocks(answer, frontend_base_url="https://x.test"))
    assert "[meeting:m1:card:c1]" not in text
    assert "<https://x.test/meetings/m1|" in text


def test_render_qa_blocks_rewrites_segment_citation():
    answer = {
        "final_text": "Alice raised the risk [meeting:m1:seg:s99].",
    }
    text = _section_text(render_qa_blocks(answer, frontend_base_url="https://x.test"))
    assert "[meeting:m1:seg:s99]" not in text
    assert "<https://x.test/meetings/m1#seg:s99|" in text


def test_render_qa_blocks_rewrites_multiple_citations():
    answer = {
        "final_text": (
            "Alpha [meeting:m1:card:c1]. Beta [meeting:m2:seg:s2]. "
            "Gamma [meeting:m3:card:c3]."
        ),
    }
    text = _section_text(render_qa_blocks(answer, frontend_base_url="https://x.test"))
    # All three citation tags consumed.
    assert "[meeting:" not in text
    assert "https://x.test/meetings/m1" in text
    assert "https://x.test/meetings/m2#seg:s2" in text
    assert "https://x.test/meetings/m3" in text


def test_render_qa_blocks_passes_through_malformed_citation():
    # Missing card/seg keyword — must NOT crash, must pass through unchanged.
    answer = {"final_text": "Per [meeting:m1:bogus:c1] we shipped it."}
    text = _section_text(render_qa_blocks(answer, frontend_base_url="https://x.test"))
    assert "[meeting:m1:bogus:c1]" in text


def test_render_qa_blocks_handles_empty_citations():
    answer = {"final_text": "No citations here, just a plain reply."}
    text = _section_text(render_qa_blocks(answer, frontend_base_url="https://x.test"))
    assert text.startswith("No citations here")
    assert "meetings/" not in text
