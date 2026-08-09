from __future__ import annotations

import pytest

from data_pipeline.pipeline import (
    TranscriptSegmentConflictError,
    upsert_segments,
)
from data_pipeline.storage import TranscriptSegment


def _segment(*, raw_text: str, normalized_text: str) -> dict:
    return {
        "segmentId": "s1",
        "sequenceNo": 0,
        "rawText": raw_text,
        "normalizedText": normalized_text,
        "text": normalized_text,
    }


@pytest.mark.parametrize(
    ("changed_raw", "changed_normalized"),
    [
        ("changed raw", "GitLab을 사용한다."),
        ("깃랩을 사용한다.", "changed normalized"),
    ],
)
def test_existing_segment_text_conflict_rolls_back_without_overwrite(
    session_factory,
    changed_raw,
    changed_normalized,
):
    original = _segment(
        raw_text="깃랩을 사용한다.",
        normalized_text="GitLab을 사용한다.",
    )
    with session_factory() as session:
        assert upsert_segments(
            session,
            "project-a",
            "meeting-a",
            [original],
        ) == 1
        session.commit()

    with pytest.raises(TranscriptSegmentConflictError):
        with session_factory() as session:
            upsert_segments(
                session,
                "project-a",
                "meeting-a",
                [
                    _segment(
                        raw_text=changed_raw,
                        normalized_text=changed_normalized,
                    )
                ],
            )
            session.commit()

    with session_factory() as session:
        stored = session.query(TranscriptSegment).one()
        assert stored.raw_text == original["rawText"]
        assert stored.normalized_text == original["normalizedText"]
        assert upsert_segments(
            session,
            "project-a",
            "meeting-a",
            [original],
        ) == 0
