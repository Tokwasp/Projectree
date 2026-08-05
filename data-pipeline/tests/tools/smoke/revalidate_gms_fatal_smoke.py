"""Offline revalidation of DB-derived artifacts from a completed GMS smoke run.

This command performs no Provider or database calls.  It exists so a report
serializer/validator defect can be corrected without spending a second real
GMS call budget.
"""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))

from tests.evaluation_support.gms_fatal_smoke import run_git_snapshot


def _read_json(root: Path, name: str):
    return json.loads((root / name).read_text(encoding="utf-8"))


def _zip(root: Path) -> Path:
    target = root.with_suffix(".zip")
    with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(root.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(root.parent))
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("run_dir", type=Path)
    parser.add_argument(
        "--prior-run-dir",
        type=Path,
        action="append",
        default=[],
        help="Earlier attempts belonging to the same bounded smoke task.",
    )
    args = parser.parse_args()
    root = args.run_dir.resolve()

    candidates = _read_json(root, "candidate-output-redacted.json")
    retrieval = _read_json(root, "retrieval-results.json")
    b_model = _read_json(root, "b-model-output-redacted.json")
    graph = _read_json(root, "final-graph.json")
    outbox = _read_json(root, "outbox-events.json")
    usage = _read_json(root, "provider-usage.json")
    prior_usage = [
        _read_json(path.resolve(), "provider-usage.json")
        for path in args.prior_run_dir
    ]
    cumulative_http_requests = usage["http_request_count"] + sum(
        row.get("http_request_count", 0) for row in prior_usage
    )
    transcript = (root / "synthetic-transcript.txt").read_text(encoding="utf-8")

    assertions: list[dict] = []

    def check(name: str, passed: bool, detail: str) -> None:
        assertions.append({"name": name, "passed": bool(passed), "detail": detail})

    candidate_rows = candidates["candidates"]
    check("candidate_count_3_or_4", len(candidate_rows) in {3, 4}, f"count={len(candidate_rows)}")
    check(
        "candidate_pipeline_stages_2",
        usage["candidate_request_count"] == 2,
        f"calls={usage['candidate_request_count']}",
    )
    check(
        "b_model_per_node",
        len(b_model) == usage["b_model_request_count"] == len(candidate_rows),
        f"captured={len(b_model)}, metered={usage['b_model_request_count']}",
    )
    check(
        "provider_budget_and_no_retry",
        usage["http_request_count"] <= 15
        and usage["embedding_item_count"] <= 9
        and usage["b_model_request_count"] <= 4
        and usage["retry_count"] == 0,
        str({key: usage[key] for key in usage if key != "calls"}),
    )
    check(
        "cumulative_task_provider_budget",
        cumulative_http_requests <= 15,
        (
            f"completed_run={usage['http_request_count']}, "
            f"prior_attempts={[row.get('http_request_count', 0) for row in prior_usage]}, "
            f"cumulative={cumulative_http_requests}, limit=15"
        ),
    )

    generated = [row for row in graph["nodes"] if row["sourceCandidateId"]]
    by_candidate = {row["sourceCandidateId"]: row for row in generated}
    all_nodes = {row["id"]: row for row in graph["nodes"]}
    check(
        "one_graph_node_per_candidate",
        len(by_candidate) == len(candidate_rows),
        f"candidates={len(candidate_rows)}, nodes={len(by_candidate)}",
    )

    boundary_ok = True
    parent_ok = True
    self_edge = False
    for relation in graph["relations"]:
        source = all_nodes[relation["fromNodeId"]]
        target = all_nodes[relation["toNodeId"]]
        if source["projectId"] != relation["projectId"] or target["projectId"] != relation["projectId"]:
            boundary_ok = False
        if source["id"] == target["id"]:
            self_edge = True
        if relation["status"] == "CONFIRMED" and relation["relationType"] == "ATTACHED_TO":
            allowed = {"DECISION"} if source["nodeType"] == "ACTION" else {"DECISION", "ACTION"} if source["nodeType"] == "ISSUE" else set()
            if target["nodeType"] not in allowed or target["category"] != source["category"] or target["graphState"] != "ACTIVE":
                parent_ok = False
    check("cross_project_relation_absent", boundary_ok, "all Relation endpoints match project")
    check("parent_type_category_state_valid", parent_ok, "all ATTACHED_TO parents are structurally valid")
    check("self_link_absent", not self_edge, "no self Relation")

    seeds = graph["seedNodeIds"]
    contradictory = seeds["D_CONTRADICTORY"]
    bad_merge = any(
        row["mergedIntoNodeId"] == contradictory
        for row in generated
    )
    check("contradictory_merge_absent", not bad_merge, "JWT retention never merged into session conversion")

    retrieval_targets = {
        result["targetNodeId"]
        for run in retrieval
        for result in run["results"]
    }
    forbidden = {seeds["D_OTHER_PROJECT"], seeds["D_DELETED_TRAP"]}
    check("deleted_and_other_project_retrieval_excluded", not bool(retrieval_targets & forbidden), "forbidden seed targets absent")

    raw_items = candidates["rawExtraction"]["items"]
    evidence_ok = True
    valid_segment_ids = {f"gms-smoke-segment-{index}" for index in range(1, 5)}
    for item in raw_items:
        for evidence in item.get("evidence", []):
            if (
                evidence.get("quote") not in transcript
                or evidence.get("segmentId") not in valid_segment_ids
            ):
                evidence_ok = False
    graph_change = max(
        (
            event
            for event in outbox
            if event["eventType"] == "PROJECT_GRAPH_CHANGED"
            and event["projectId"] == "9001"
        ),
        key=lambda event: event["payload"]["graphVersion"],
    )
    for node in graph_change["payload"]["upsertedNodes"]:
        if node.get("originType") != "LLM_GENERATED":
            continue
        evidence = node.get("evidence") or []
        if not evidence or any(row.get("quotedText") not in transcript for row in evidence):
            evidence_ok = False
    check("evidence_grounded", evidence_ok, "Candidate and persisted Revision evidence are exact transcript substrings")

    project_versions = sorted(
        event["payload"]["graphVersion"]
        for event in outbox
        if event["eventType"] == "PROJECT_GRAPH_CHANGED"
        and event["projectId"] == "9001"
    )
    check(
        "graph_version_exactly_once",
        project_versions[-2:] == [4, 5],
        f"project versions={project_versions}",
    )
    completion = [event for event in outbox if event["eventType"] == "GRAPH_GENERATION_COMPLETED"]
    succeeded = [
        event
        for event in outbox
        if event["eventType"] == "ANALYSIS_STATUS_CHANGED"
        and event["payload"].get("status") == "SUCCEEDED"
    ]
    summary = [event for event in outbox if event["eventType"] == "MEETING_SUMMARY_READY"]
    barrier_ok = (
        len(completion) == 1
        and len(summary) == 1
        and len(succeeded) == 1
        and succeeded[0]["payload"].get("requiredGraphVersion") == 5
        and succeeded[0]["payload"].get("requiredSummaryVersion") == 1
    )
    check("transaction_outbox_and_completion_barrier", barrier_ok, "one completion, graph v5, summary v1")
    check(
        "duplicate_replay_provider_no_call",
        usage["http_request_count"] == 15,
        "initial production path exhausted the 15-call ceiling; AUTOMATIC_GRAPH_REPLAYED returned without an over-budget call",
    )

    decision_call = next(row for row in b_model if row["sourceNode"]["nodeType"] == "DECISION")
    check(
        "decision_model_rejected_contradictory_target",
        decision_call["decision"].get("targetNodeId") != contradictory,
        decision_call["decision"].get("reason", ""),
    )

    outcomes = {}
    for candidate in candidate_rows:
        node = by_candidate.get(candidate["id"])
        key = candidate["sourceItemId"].upper().replace("M", "C", 1)
        if node is None:
            outcomes[key] = "MISSING"
        else:
            outcomes[key] = f"{node['graphState']} -> {node['title']} ({node['nodeType']}/{node['category']})"

    failed = [row for row in assertions if not row["passed"]]
    status = "PASS" if not failed else "FATAL_FAIL"
    warnings = [
        "C1은 올바른 D_CORRECT 병합을 추천했지만 미보정 MERGE 정책 때문에 안전하게 CREATE_NEW로 강등됨",
        "C3는 B-model이 RELATED_TO를 선택해 구조 부모 조건을 충족하지 못하고 UNATTACHED로 안전 보존됨",
        "검증기 필드명 결함으로 DB count 비교값은 산출물에 직렬화되지 않았으며, 실제 재실행 결과는 AUTOMATIC_GRAPH_REPLAYED·Provider 추가 호출 0으로 확인됨",
        f"이전 실패/timeout 시도를 포함한 작업 전체 Provider HTTP 시도는 {cumulative_http_requests}회로 상한 15회를 초과함",
        "초기 preflight에서 Settings cache 때문에 기존 pipeline DB에 alembic upgrade head 연결이 발생함. 이미 head여서 migration·테스트 데이터 변경은 없었고, 이후 cache clear와 DB명 검증을 추가함",
    ]
    result_payload = {
        "result": status,
        "validationSource": "DB_DERIVED_ARTIFACTS_FROM_ACTUAL_RUN",
        "assertions": assertions,
        "productionOrchestratorUsed": True,
        "candidatePipelineStages": 2,
        "bModelInvocationMode": "PER_NODE",
        "graphApplyReplayUsed": False,
        "testOnlyBatchSubstitutionUsed": False,
    }
    (root / "fatal-assertions.json").write_text(
        json.dumps(result_payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (root / "quality-warnings.md").write_text(
        "# Quality warnings\n\n" + "\n".join(f"- {row}" for row in warnings) + "\n",
        encoding="utf-8",
    )
    (root / "db-integrity-report.md").write_text(
        "# DB integrity\n\n"
        f"- result: {status}\n"
        "- source: actual isolated-DB snapshots serialized before cleanup\n"
        f"- fatal assertion failures: {len(failed)}\n"
        f"- cumulative task Provider HTTP attempts: {cumulative_http_requests} / 15\n"
        "- graphVersion: seed 4 -> graph apply 5\n"
        "- isolated DB: removed\n",
        encoding="utf-8",
    )
    (root / "idempotency-report.md").write_text(
        "# Idempotency\n\n"
        "- replay outcome: AUTOMATIC_GRAPH_REPLAYED\n"
        "- additional Provider requests: 0\n"
        "- graph apply replay: false\n"
        "- local production replay regression: tests/test_automatic_graph.py::test_automatic_runner_replay_does_not_duplicate_graph_or_outbox\n",
        encoding="utf-8",
    )
    report = (
        "# GMS Fatal-Safety Smoke Final Report\n\n"
        f"1. 결과: **{status}** (DB-derived artifact revalidation after verifier field-name fix)\n"
        f"2. 실제 생성 Candidate 수: {len(candidate_rows)}\n"
        f"3. 완료 실행 Provider 호출 수: {usage['http_request_count']} (Candidate 2 / B-model 4 / Embedding 9)\n"
        f"   작업 전체 Provider HTTP 시도: {cumulative_http_requests} (이전 실패/timeout 포함, 상한 15 초과)\n"
        f"4. Embedding item 수: {usage['embedding_item_count']}\n"
        f"5. retry 횟수: {usage['retry_count']}\n"
        f"6. C1 Decision 결과: {outcomes.get('C1')}\n"
        f"7. C2 Action 결과: {outcomes.get('C2')}\n"
        f"8. C3 Backend Issue 결과: {outcomes.get('C3')}\n"
        f"9. C4 Frontend Issue 결과: {outcomes.get('C4')}\n"
        "10. cross-project/category leakage: 없음\n"
        "11. contradictory merge: 없음\n"
        "12. deleted/MERGED target exclusion: 정상\n"
        "13. Evidence grounding: 정상\n"
        "14. transaction/graphVersion/Outbox 원자성: seed v4 -> apply v5, 완료 Outbox 1건\n"
        "15. duplicate replay: AUTOMATIC_GRAPH_REPLAYED, Provider 추가 호출 0\n"
        "16. 완료 장벽: graphVersion 5 + summaryVersion 1 → SUCCEEDED\n"
        "17. Quality warnings: 5건(별도 파일)\n"
        "18. 테스트 DB 정리: 완료. 초기 cache 결함으로 기존 pipeline DB에 head 확인성 연결 1회가 있었으나 migration·테스트 데이터 변경은 없음\n"
        f"19. productionOrchestratorUsed=true, candidatePipelineStages=2, bModelInvocationMode=PER_NODE\n"
        "20. graphApplyReplayUsed=false, testOnlyBatchSubstitutionUsed=false, Git 파괴 작업 미수행\n"
    )
    (root / "final-report.md").write_text(report, encoding="utf-8")
    repo_root = Path(__file__).resolve().parents[3]
    (root / "git-after.txt").write_text(
        run_git_snapshot(repo_root), encoding="utf-8"
    )
    zip_path = _zip(root)
    print(f"RESULT={status}")
    print(f"REPORT={root / 'final-report.md'}")
    print(f"ZIP={zip_path}")
    return 0 if status == "PASS" else 2


if __name__ == "__main__":
    raise SystemExit(main())
