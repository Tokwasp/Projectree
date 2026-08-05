from __future__ import annotations

import json
import threading
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import select

from data_pipeline.jobs.outbox import (
    OutboxMessage,
    S3ClaimCheckSqsTransport,
    build_transport_from_env,
)
from data_pipeline.meeting_analysis.consumers import (
    AnalysisCommandConsumer,
    RecordingReadyConsumer,
)
from data_pipeline.meeting_analysis.contracts import (
    AnalysisCommandParser,
    AnalysisCommandValidationError,
)
from data_pipeline.meeting_analysis.coordinator import MeetingAnalysisCoordinator
from data_pipeline.meeting_analysis.persistence import (
    CommandPayloadConflictError,
    RecordingPayloadConflictError,
    persist_analysis_command,
    persist_recording_ready,
)
from data_pipeline.meeting_analysis.result_events import (
    stage_meeting_summary_ready_v3,
    stage_project_graph_changed_v3,
)
from data_pipeline.meeting_analysis.snapshot import (
    GraphSnapshotTooLargeError,
    validate_graph_snapshot_size,
)
from data_pipeline.pipeline.user_graph import create_user_node, user_merge_nodes
from data_pipeline.storage import (
    GraphSnapshotArtifact,
    MeetingAnalysisCommand,
    MeetingAnalysisTask,
    Meeting,
    MeetingSummary,
    OutboxEvent,
    ProjectGraphState,
    RecordingReadyEvent,
)
from data_pipeline.worker.openvidu_events import OpenViduEgressEventParser

ROOM = "550e8400-e29b-41d4-a716-446655440000"
COMMAND_ID = "6f054682-6e8d-4d07-85b1-b576643b411e"
KEY = f"meetings/{ROOM}/mixed/recording.ogg"


def _command(**changes) -> dict:
    value = {
        "commandSchemaVersion": 1,
        "commandId": COMMAND_ID,
        "commandType": "MEETING_ANALYSIS_REQUESTED",
        "requestedAt": "2026-08-04T01:15:00Z",
        "projectId": 15,
        "payload": {
            "meetingId": 35,
            "roomName": ROOM,
            "generateSummary": True,
            "generateNodes": True,
        },
    }
    nested = changes.pop("payload", None)
    value.update(changes)
    if nested:
        value["payload"].update(nested)
    return value


def _recording(**changes) -> dict:
    value = {
        "projectId": 15,
        "roomName": ROOM,
        "kind": "MIXED",
        "objectKey": KEY,
        "egressId": "EG_contract_v3",
        "memberId": None,
        "endedAt": "2026-08-04T01:10:00Z",
    }
    value.update(changes)
    return value


def _parse_command(**changes):
    return AnalysisCommandParser().parse(json.dumps(_command(**changes)))


def _parse_recording(**changes):
    return OpenViduEgressEventParser().parse(json.dumps(_recording(**changes)))


class _Sqs:
    def __init__(self, body: str):
        self.body = body
        self.deleted: list[dict] = []
        self.sent: list[dict] = []

    def receive_message(self, **kwargs):
        return {
            "Messages": [
                {
                    "MessageId": "m-1",
                    "ReceiptHandle": "receipt-1",
                    "Body": self.body,
                }
            ]
        }

    def delete_message(self, **kwargs):
        self.deleted.append(kwargs)

    def send_message(self, **kwargs):
        self.sent.append(kwargs)
        return {"MessageId": "sent-1"}


class _S3:
    def __init__(self):
        self.puts: list[dict] = []

    def put_object(self, **kwargs):
        self.puts.append(kwargs)
        return {"ETag": "fake"}


def test_command_parser_accepts_strict_contract() -> None:
    command = _parse_command()
    assert command.project_id == "15"
    assert command.meeting_id == "35"
    assert command.room_name == ROOM
    assert command.requested_at.tzinfo is not None


@pytest.mark.parametrize(
    "changes",
    [
        {"commandSchemaVersion": 2},
        {"projectId": "15"},
        {"requestedAt": "2026-08-04T10:15:00+09:00"},
        {"payload": {"generateNodes": 1}},
        {"payload": {"meetingId": 0}},
        {"payload": {"roomName": "not-a-uuid"}},
    ],
)
def test_command_parser_rejects_coercion_and_wrong_versions(changes) -> None:
    with pytest.raises(AnalysisCommandValidationError):
        _parse_command(**changes)


@pytest.mark.parametrize("recording_first", [True, False])
def test_two_inputs_join_in_either_order(session_factory, recording_first) -> None:
    command = _parse_command()
    recording = _parse_recording()
    calls = (
        (
            lambda: persist_recording_ready(
                session_factory,
                event=recording,
                recording_bucket="recordings",
            ),
            lambda: persist_analysis_command(session_factory, command=command),
        )
        if recording_first
        else (
            lambda: persist_analysis_command(session_factory, command=command),
            lambda: persist_recording_ready(
                session_factory,
                event=recording,
                recording_bucket="recordings",
            ),
        )
    )
    calls[0]()
    calls[1]()
    with session_factory() as session:
        stored_command = session.execute(select(MeetingAnalysisCommand)).scalar_one()
        stored_recording = session.execute(select(RecordingReadyEvent)).scalar_one()
        tasks = list(session.execute(select(MeetingAnalysisTask)).scalars())
        assert stored_command.status == "READY"
        assert stored_recording.status == "READY"
        assert {task.status for task in tasks} == {"READY"}


def test_false_false_creates_two_skipped_tasks(session_factory) -> None:
    command = _parse_command(
        payload={"generateSummary": False, "generateNodes": False}
    )
    persist_analysis_command(session_factory, command=command)
    with session_factory() as session:
        tasks = list(session.execute(select(MeetingAnalysisTask)).scalars())
        assert {(task.task_type, task.status) for task in tasks} == {
            ("SUMMARY", "SKIPPED"),
            ("NODES", "SKIPPED"),
        }


def test_duplicate_inputs_are_noop_and_conflicts_are_explicit(session_factory) -> None:
    command = _parse_command()
    recording = _parse_recording()
    assert persist_analysis_command(session_factory, command=command)[1] is True
    assert persist_analysis_command(session_factory, command=command)[1] is False
    assert persist_recording_ready(
        session_factory, event=recording, recording_bucket="recordings"
    )[1] is True
    assert persist_recording_ready(
        session_factory, event=recording, recording_bucket="recordings"
    )[1] is False
    with pytest.raises(CommandPayloadConflictError):
        persist_analysis_command(
            session_factory,
            command=_parse_command(payload={"generateNodes": False}),
        )
    with pytest.raises(RecordingPayloadConflictError):
        persist_recording_ready(
            session_factory,
            event=_parse_recording(projectId=16),
            recording_bucket="recordings",
        )


def test_consumers_ack_only_after_commit(session_factory) -> None:
    recording_sqs = _Sqs(json.dumps(_recording()))
    result = RecordingReadyConsumer(
        sqs_client=recording_sqs,
        queue_url="recording-queue",
        session_factory=session_factory,
        parser=OpenViduEgressEventParser(),
        recording_bucket="recordings",
        wait_time_seconds=0,
    ).poll_once()
    assert result.acknowledged == 1
    assert len(recording_sqs.deleted) == 1

    invalid_sqs = _Sqs("not-json")
    result = AnalysisCommandConsumer(
        sqs_client=invalid_sqs,
        queue_url="command-queue",
        session_factory=session_factory,
        wait_time_seconds=0,
    ).poll_once()
    assert result.failed == 1
    assert invalid_sqs.deleted == []


def test_coordinator_shares_stt_and_tasks_fail_independently(session_factory) -> None:
    persist_analysis_command(session_factory, command=_parse_command())
    persist_recording_ready(
        session_factory,
        event=_parse_recording(),
        recording_bucket="recordings",
    )
    loads: list[int] = []
    nodes: list[int] = []

    def transcript_loader(command, recording):
        loads.append(1)
        return [{"segmentId": "s1", "text": "회의"}]

    def summary(command, recording, transcript):
        raise RuntimeError("summary unavailable")

    def node_processor(command, recording, transcript):
        nodes.append(1)

    coordinator = MeetingAnalysisCoordinator(
        session_factory=session_factory,
        transcript_loader=transcript_loader,
        summary_processor=summary,
        nodes_processor=node_processor,
    )
    first = coordinator.run_once()
    second = coordinator.run_once()
    third = coordinator.run_once()
    assert first.succeeded == ("NODES",)
    assert first.retrying == ("SUMMARY",)
    assert second.retrying == ("SUMMARY",)
    assert third.failed == ("SUMMARY",)
    assert len(loads) == 3
    assert len(nodes) == 1
    with session_factory() as session:
        tasks = {
            task.task_type: task
            for task in session.execute(select(MeetingAnalysisTask)).scalars()
        }
        assert tasks["NODES"].status == "SUCCEEDED"
        assert tasks["SUMMARY"].status == "FAILED"
        events = list(
            session.execute(
                select(OutboxEvent).where(
                    OutboxEvent.event_type == "ANALYSIS_TASK_STATUS_CHANGED"
                )
            ).scalars()
        )
        assert len(events) == 1
        assert events[0].payload["payload"]["taskType"] == "SUMMARY"


def test_generate_summary_and_nodes_run_in_parallel_after_shared_stt(
    session_factory,
) -> None:
    persist_analysis_command(session_factory, command=_parse_command())
    persist_recording_ready(
        session_factory,
        event=_parse_recording(),
        recording_bucket="recordings",
    )
    started = threading.Barrier(2)
    completed: list[str] = []
    transcript = [{"segmentId": "s1", "text": "회의"}]

    def transcript_loader(command, recording):
        return transcript

    def processor(task_type: str):
        def run(command, recording, received_transcript):
            assert received_transcript is transcript
            started.wait(timeout=2)
            completed.append(task_type)

        return run

    result = MeetingAnalysisCoordinator(
        session_factory=session_factory,
        transcript_loader=transcript_loader,
        summary_processor=processor("SUMMARY"),
        nodes_processor=processor("NODES"),
    ).run_once()

    assert result.transcript_loads == 1
    assert result.succeeded == ("NODES", "SUMMARY")
    assert set(completed) == {"NODES", "SUMMARY"}


def test_snapshot_artifact_and_standard_fifo_claim_check(
    session_factory,
    monkeypatch,
) -> None:
    monkeypatch.setenv(
        "PROJECTREE_GRAPH_SNAPSHOT_PREFIX", "contract-snapshots/"
    )
    command, _ = persist_analysis_command(
        session_factory,
        command=_parse_command(payload={"generateSummary": False}),
    )
    source = create_user_node(
        session_factory,
        project_id="15",
        actor_id="tester",
        request_id="snapshot-source",
        node_type="DECISION",
        category="BACKEND",
        title="source",
        content="source content",
        due_date=None,
        evidence_assertion="source evidence",
        external_meeting_id="35",
    )
    target = create_user_node(
        session_factory,
        project_id="15",
        actor_id="tester",
        request_id="snapshot-target",
        node_type="DECISION",
        category="BACKEND",
        title="target",
        content="target content",
        due_date=None,
        evidence_assertion="target evidence",
        external_meeting_id="35",
    )
    user_merge_nodes(
        session_factory,
        project_id="15",
        source_node_id=source.node_id,
        target_node_id=target.node_id,
        source_expected_version=source.version,
        target_expected_version=target.version,
        actor_id="tester",
        reason="snapshot lineage",
    )
    with session_factory() as session:
        stored = session.execute(select(MeetingAnalysisCommand)).scalar_one()
        event, artifact, version = stage_project_graph_changed_v3(
            session,
            command=stored,
        )
        session.commit()
        event_id = event.id
        artifact_id = artifact.id
        assert version >= 1

    with session_factory() as session:
        event = session.get(OutboxEvent, event_id)
        artifact = session.get(GraphSnapshotArtifact, artifact_id)
        message = OutboxMessage(
            event_id=str(event.id),
            event_type=event.event_type,
            aggregate_type=event.aggregate_type,
            aggregate_id=event.aggregate_id,
            project_id=event.project_id,
            schema_version=event.schema_version,
            occurred_at=event.created_at,
            payload=dict(event.payload),
        )
        states = {
            row["nodeId"]: row["graphState"]
            for row in artifact.payload_json["nodes"]
        }
        assert states[str(source.node_id)] == "MERGED"
        assert states[str(target.node_id)] == "ACTIVE"
        assert {row["nodeId"] for row in artifact.payload_json["evidences"]} == {
            str(source.node_id),
            str(target.node_id),
        }
        assert artifact.payload_json["mergeRecords"][0]["sourceNodeId"] == str(
            source.node_id
        )
        assert artifact.object_key.startswith("contract-snapshots/")
        artifact_size = artifact.size_bytes

    rejected_s3 = _S3()
    rejected_sqs = _Sqs("")
    with pytest.raises(GraphSnapshotTooLargeError):
        S3ClaimCheckSqsTransport(
            session_factory=session_factory,
            s3_client=rejected_s3,
            sqs_client=rejected_sqs,
            queue_url="result-standard",
            snapshot_bucket="snapshots",
            snapshot_max_size_bytes=artifact_size - 1,
        ).publish(message)
    assert rejected_s3.puts == []
    assert rejected_sqs.sent == []

    s3 = _S3()
    standard = _Sqs("")
    S3ClaimCheckSqsTransport(
        session_factory=session_factory,
        s3_client=s3,
        sqs_client=standard,
        queue_url="result-standard",
        snapshot_bucket="snapshots",
        queue_type="STANDARD",
        snapshot_max_size_bytes=artifact_size,
    ).publish(message)
    body = json.loads(standard.sent[0]["MessageBody"])
    assert body["eventSchemaVersion"] == 3
    assert body["projectId"] == 15
    assert body["meetingId"] == 35
    assert "snapshotArtifactId" not in body["payload"]
    assert body["payload"]["snapshotRef"]["sha256"]
    assert "MessageGroupId" not in standard.sent[0]

    fifo = _Sqs("")
    S3ClaimCheckSqsTransport(
        session_factory=session_factory,
        s3_client=s3,
        sqs_client=fifo,
        queue_url="result.fifo",
        snapshot_bucket="snapshots",
        queue_type="FIFO",
    ).publish(message)
    assert fifo.sent[0]["MessageGroupId"] == "15"
    assert fifo.sent[0]["MessageDeduplicationId"] == str(event_id)


def test_snapshot_size_limit_uses_bytes_and_is_inclusive() -> None:
    assert validate_graph_snapshot_size(b"1234", max_size_bytes=4) == 4
    with pytest.raises(GraphSnapshotTooLargeError, match="5 exceeds maximum 4"):
        validate_graph_snapshot_size(b"12345", max_size_bytes=4)


def test_oversized_snapshot_rolls_back_version_artifact_and_outbox(
    session_factory,
    monkeypatch,
) -> None:
    monkeypatch.setenv("PROJECTREE_GRAPH_SNAPSHOT_MAX_SIZE_BYTES", "1")
    persist_analysis_command(
        session_factory,
        command=_parse_command(payload={"generateSummary": False}),
    )

    with session_factory() as session:
        command = session.execute(select(MeetingAnalysisCommand)).scalar_one()
        with pytest.raises(GraphSnapshotTooLargeError):
            stage_project_graph_changed_v3(session, command=command)
        session.rollback()

    with session_factory() as session:
        assert session.get(ProjectGraphState, "15") is None
        assert list(session.execute(select(GraphSnapshotArtifact)).scalars()) == []
        assert list(
            session.execute(
                select(OutboxEvent).where(
                    OutboxEvent.event_type == "PROJECT_GRAPH_CHANGED"
                )
            ).scalars()
        ) == []


def test_result_transport_reads_java_aligned_environment_names(
    session_factory,
    monkeypatch,
) -> None:
    import boto3

    regions: list[tuple[str, str]] = []
    s3 = _S3()
    sqs = _Sqs("")

    def client(service_name: str, *, region_name: str):
        regions.append((service_name, region_name))
        return s3 if service_name == "s3" else sqs

    monkeypatch.setattr(boto3, "client", client)
    monkeypatch.setenv("OUTBOX_TRANSPORT", "result-sqs")
    monkeypatch.setenv("AWS_REGION", "ap-northeast-2")
    monkeypatch.setenv(
        "PROJECTREE_ANALYSIS_RESULT_QUEUE_URL", "https://sqs/result"
    )
    monkeypatch.setenv("PROJECTREE_ANALYSIS_RESULT_QUEUE_TYPE", "STANDARD")
    monkeypatch.setenv("AWS_S3_BUCKET", "projectree-bucket")
    monkeypatch.setenv(
        "PROJECTREE_GRAPH_SNAPSHOT_MAX_SIZE_BYTES", "10485760"
    )
    transport = build_transport_from_env(session_factory=session_factory)

    assert isinstance(transport, S3ClaimCheckSqsTransport)
    assert transport._queue_url == "https://sqs/result"
    assert transport._bucket == "projectree-bucket"
    assert transport._snapshot_max_size_bytes == 10_485_760
    assert regions == [
        ("s3", "ap-northeast-2"),
        ("sqs", "ap-northeast-2"),
    ]


def test_summary_ready_v3_is_independent_and_contains_only_api_reference(
    session_factory,
) -> None:
    persist_analysis_command(
        session_factory,
        command=_parse_command(payload={"generateNodes": False}),
    )
    with session_factory() as session:
        session.add(
            Meeting(
                project_id="15",
                external_meeting_id="35",
                status="COMPLETED",
            )
        )
        session.flush()
        summary = MeetingSummary(
            project_id="15",
            external_meeting_id="35",
            summary_version=1,
            source_hash="a" * 64,
            title="meeting",
            body="full body stays in PostgreSQL",
            structured_summary={},
            status="READY",
            generator_name="fake",
            generator_version="1",
        )
        session.add(summary)
        session.flush()
        command = session.execute(select(MeetingAnalysisCommand)).scalar_one()
        event = stage_meeting_summary_ready_v3(
            session,
            command=command,
            summary=summary,
            api_path="/api/v1/meetings/35/summary?summaryVersion=1",
        )
        session.commit()

        payload = event.payload["payload"]
        assert payload["meetingSummaryId"] == str(summary.id)
        assert payload["apiPath"].endswith("summaryVersion=1")
        assert "body" not in payload
        assert event.schema_version == "3"
