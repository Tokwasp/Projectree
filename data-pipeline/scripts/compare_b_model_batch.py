"""Shadow comparison of per-Node and batched B-model inference.

The script never opens a database and never applies decisions.  It replays four
small, synthetic cases derived from the live node-review E2E and writes only an
evaluation report under ``outputs/b-model-batch-comparison``.

Run:
    python scripts/compare_b_model_batch.py --live
"""

from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

from data_pipeline.b_model.gms import (
    GmsBModelClient,
    load_b_model_client_settings,
    render_b_model_prompt,
)
from data_pipeline.contracts.dto import BModelDecision


EC2_DECISION_ID = "11111111-1111-4111-8111-111111111111"
RDS_DECISION_ID = "22222222-2222-4222-8222-222222222222"
PR_DECISION_ID = "33333333-3333-4333-8333-333333333333"


def _target(
    *,
    node_id: str,
    title: str,
    content: str,
    rank: int,
    similarity: float,
    suggested_parent: bool = False,
) -> dict[str, Any]:
    row: dict[str, Any] = {
        "nodeId": node_id,
        "nodeVersion": 1,
        "nodeType": "DECISION",
        "category": "INFRA",
        "title": title,
        "content": content,
        "graphState": "ACTIVE",
        "rank": rank,
        "similarity": similarity,
    }
    if suggested_parent:
        row["sameMeetingSuggestedParent"] = True
        row["parentHintOrigin"] = "SAME_MEETING_CANDIDATE"
    return row


def _source(
    *,
    node_id: str,
    node_type: str,
    title: str,
    content: str,
    quote: str,
) -> dict[str, Any]:
    return {
        "nodeId": node_id,
        "nodeVersion": 1,
        "nodeType": node_type,
        "category": "INFRA",
        "title": title,
        "content": content,
        "evidence": [{"segmentId": f"seg-{node_id[:8]}", "quote": quote}],
    }


def build_cases() -> list[dict[str, Any]]:
    """Cases lock the four decisions observed in the live E2E."""

    unrelated = _target(
        node_id=PR_DECISION_ID,
        title="코드 리뷰는 PR 단위로 진행한다",
        content="모든 변경은 Pull Request 단위로 리뷰 후 병합한다.",
        rank=3,
        similarity=0.18,
    )
    return [
        {
            "itemId": "decision-exact-merge",
            "description": "동일한 EC2 운영 Decision 병합",
            "source": _source(
                node_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa1",
                node_type="DECISION",
                title="회의 처리 서버를 Lambda 대신 EC2로 구성",
                content="회의 녹음 처리 서버는 Lambda가 아니라 EC2 인스턴스에서 운영하기로 결정했다.",
                quote="회의 처리 서버는 EC2로 구성하는 것으로 결정하겠습니다.",
            ),
            "candidates": [
                _target(
                    node_id=EC2_DECISION_ID,
                    title="회의 처리 서버는 EC2에서 운영한다",
                    content="회의 처리 및 녹음 처리 서버는 EC2 인스턴스에서 운영하기로 했다.",
                    rank=1,
                    similarity=0.94,
                ),
                _target(
                    node_id=RDS_DECISION_ID,
                    title="RDS는 프라이빗 서브넷에 배치한다",
                    content="RDS 접근은 보안그룹으로 제한한다.",
                    rank=2,
                    similarity=0.43,
                ),
                unrelated,
            ],
            "expected": {
                "recommendation": "MERGE",
                "targetNodeId": EC2_DECISION_ID,
                "relationType": None,
            },
        },
        {
            "itemId": "action-parent-link",
            "description": "Decision 병합 후 Action의 정본 부모 연결",
            "source": _source(
                node_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa2",
                node_type="ACTION",
                title="EC2에서 RDS 연결 구성",
                content="EC2 환경에서 RDS에 접근할 수 있도록 네트워크와 보안 설정을 구성한다.",
                quote="EC2에서 RDS에 붙을 수 있도록 연결 설정을 진행하겠습니다.",
            ),
            "candidates": [
                _target(
                    node_id=EC2_DECISION_ID,
                    title="회의 처리 서버는 EC2에서 운영한다",
                    content="회의 처리 및 녹음 처리 서버는 EC2 인스턴스에서 운영하기로 했다.",
                    rank=1,
                    similarity=0.86,
                    suggested_parent=True,
                ),
                _target(
                    node_id=RDS_DECISION_ID,
                    title="RDS는 프라이빗 서브넷에 배치한다",
                    content="RDS 접근은 보안그룹으로 제한한다.",
                    rank=2,
                    similarity=0.79,
                ),
                unrelated,
            ],
            "expected": {
                "recommendation": "LINK",
                "targetNodeId": EC2_DECISION_ID,
                "relationType": "ATTACHED_TO",
            },
        },
        {
            "itemId": "issue-related-link",
            "description": "RDS 접근 Issue와 보안 Decision의 비구조적 연결",
            "source": _source(
                node_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa3",
                node_type="ISSUE",
                title="Lambda에서 RDS 접근 및 VPC 설정이 어렵다",
                content="Lambda에서 RDS 접근이 원활하지 않고 VPC 설정 복잡도로 연결 구성이 어렵다.",
                quote="Lambda에서 RDS 접근이 안 되고 VPC 설정도 너무 복잡합니다.",
            ),
            "candidates": [
                _target(
                    node_id=RDS_DECISION_ID,
                    title="RDS는 프라이빗 서브넷에 배치한다",
                    content="RDS 인스턴스는 프라이빗 서브넷에 배치하고 보안그룹으로 접근을 제한한다.",
                    rank=1,
                    similarity=0.89,
                ),
                _target(
                    node_id=EC2_DECISION_ID,
                    title="회의 처리 서버는 EC2에서 운영한다",
                    content="회의 처리 및 녹음 처리 서버는 EC2 인스턴스에서 운영하기로 했다.",
                    rank=2,
                    similarity=0.61,
                ),
                unrelated,
            ],
            "expected": {
                "recommendation": "LINK",
                "targetNodeId": RDS_DECISION_ID,
                "relationType": "RELATED_TO",
            },
        },
        {
            "itemId": "decision-keyword-false-merge",
            "description": "EC2 키워드는 같지만 목적이 다른 Decision의 false merge 방지",
            "source": _source(
                node_id="aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaa4",
                node_type="DECISION",
                title="프론트 정적 파일은 EC2 대신 S3로 배포",
                content="프론트 정적 파일 배포는 EC2가 아니라 S3 정적 호스팅을 사용하기로 결정했다.",
                quote="프론트는 EC2에 두지 말고 S3 정적 호스팅으로 배포하겠습니다.",
            ),
            "candidates": [
                _target(
                    node_id=EC2_DECISION_ID,
                    title="회의 처리 서버는 EC2에서 운영한다",
                    content="회의 처리 및 녹음 처리 서버는 EC2 인스턴스에서 운영하기로 했다.",
                    rank=1,
                    similarity=0.82,
                ),
                _target(
                    node_id=RDS_DECISION_ID,
                    title="RDS는 프라이빗 서브넷에 배치한다",
                    content="RDS 접근은 보안그룹으로 제한한다.",
                    rank=2,
                    similarity=0.31,
                ),
                unrelated,
            ],
            "expected": {
                "recommendation": "CREATE_NEW",
                "targetNodeId": None,
                "relationType": None,
            },
        },
    ]


def _payload(model: str, prompt: str, temperature: float | None) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "response_format": {"type": "json_object"},
    }
    if temperature is not None:
        payload["temperature"] = temperature
    return payload


def _usage(data: dict[str, Any]) -> dict[str, int | None]:
    raw = data.get("usage")
    raw = raw if isinstance(raw, dict) else {}
    input_tokens = raw.get("prompt_tokens", raw.get("input_tokens"))
    output_tokens = raw.get("completion_tokens", raw.get("output_tokens"))
    total_tokens = raw.get("total_tokens")
    if total_tokens is None and isinstance(input_tokens, int) and isinstance(output_tokens, int):
        total_tokens = input_tokens + output_tokens
    return {
        "inputTokens": input_tokens if isinstance(input_tokens, int) else None,
        "outputTokens": output_tokens if isinstance(output_tokens, int) else None,
        "totalTokens": total_tokens if isinstance(total_tokens, int) else None,
    }


def _request(
    client: GmsBModelClient,
    *,
    prompt: str,
    model: str,
) -> tuple[dict[str, Any], dict[str, int | None], float]:
    started = time.perf_counter()
    data = client._post_with_retry(  # noqa: SLF001 - deliberate shadow harness
        _payload(model, prompt, client.settings.temperature)
    )
    elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
    return data, _usage(data), elapsed_ms


def _decision_dict(raw: dict[str, Any]) -> dict[str, Any]:
    decision = BModelDecision.model_validate(raw)
    return decision.model_dump(mode="json", by_alias=True)


def _matches_expected(decision: dict[str, Any], expected: dict[str, Any]) -> bool:
    return all(decision.get(key) == value for key, value in expected.items())


def _validate_membership(decision: dict[str, Any], case: dict[str, Any]) -> None:
    target = decision.get("targetNodeId")
    if target is None:
        return
    offered = {row["nodeId"] for row in case["candidates"]}
    if target not in offered:
        raise ValueError(f"{case['itemId']}: target is outside its candidate list")


def render_batch_prompt(cases: list[dict[str, Any]]) -> str:
    """Reuse the locked judgment rules, replacing only the single-item envelope."""

    rendered_single = render_b_model_prompt(source_node={}, retrieval_candidates=[])
    rules = rendered_single.split("### source 노드", 1)[0].rstrip()
    batch_input = [
        {
            "itemId": case["itemId"],
            "source": case["source"],
            "candidates": case["candidates"],
        }
        for case in cases
    ]
    return (
        f"{rules}\n\n"
        "## Batch 처리 규칙\n"
        "- 각 item은 서로 독립적으로 판단한다. 다른 item의 source나 candidates를 섞지 않는다.\n"
        "- 각 itemId를 정확히 한 번 반환한다. 누락·중복·새 itemId를 만들지 않는다.\n"
        "- targetNodeId는 반드시 해당 item의 candidates 안에 있는 nodeId만 사용한다.\n"
        "- recommendation과 relationType 규칙은 위 단일 노드 규칙을 각 item에 그대로 적용한다.\n\n"
        "### Batch 입력\n"
        "<<<BATCH_START>>>\n"
        f"{json.dumps(batch_input, ensure_ascii=False, indent=2)}\n"
        "<<<BATCH_END>>>\n\n"
        "## 출력 형식\n"
        "JSON 객체 하나만 반환한다.\n"
        '{"results":[{"itemId":"입력 itemId","recommendation":"CREATE_NEW | LINK | MERGE",'
        '"targetNodeId":"후보 nodeId 또는 null","relationType":"ATTACHED_TO | RELATED_TO 또는 null",'
        '"suggestedTitle":"한 문장 제목","suggestedContent":"1~2문장 설명",'
        '"reason":"판정 근거 1~3문장","metadata":{}}]}'
    )


def _sum_usage(rows: list[dict[str, int | None]]) -> dict[str, int | None]:
    result: dict[str, int | None] = {}
    for key in ("inputTokens", "outputTokens", "totalTokens"):
        values = [row[key] for row in rows]
        result[key] = sum(values) if all(isinstance(value, int) for value in values) else None
    return result


def _reduction(before: int | None, after: int | None) -> float | None:
    if before is None or after is None or before <= 0:
        return None
    return round((before - after) / before * 100, 2)


def run_live() -> dict[str, Any]:
    cases = build_cases()
    settings = load_b_model_client_settings()
    client = GmsBModelClient(settings)

    node_rows: list[dict[str, Any]] = []
    for case in cases:
        prompt = render_b_model_prompt(
            source_node=case["source"],
            retrieval_candidates=case["candidates"],
        )
        data, usage, elapsed_ms = _request(client, prompt=prompt, model=settings.model)
        raw_decision = client._extract_decision(data)  # noqa: SLF001
        client._check_target_membership(raw_decision, case["candidates"])  # noqa: SLF001
        decision = _decision_dict(raw_decision)
        _validate_membership(decision, case)
        node_rows.append(
            {
                "itemId": case["itemId"],
                "description": case["description"],
                "decision": decision,
                "expected": case["expected"],
                "qualityPass": _matches_expected(decision, case["expected"]),
                "usage": usage,
                "elapsedMs": elapsed_ms,
            }
        )

    batch_prompt = render_batch_prompt(cases)
    batch_data, batch_usage, batch_elapsed_ms = _request(
        client, prompt=batch_prompt, model=settings.model
    )
    extracted = client._extract_decision(batch_data)  # noqa: SLF001
    raw_results = extracted.get("results")
    if not isinstance(raw_results, list):
        raise ValueError("Batch response must contain a results array")
    by_item: dict[str, dict[str, Any]] = {}
    for raw in raw_results:
        if not isinstance(raw, dict):
            raise ValueError("Every Batch result must be an object")
        item_id = raw.get("itemId")
        if not isinstance(item_id, str) or item_id in by_item:
            raise ValueError("Batch result itemId is missing or duplicated")
        by_item[item_id] = raw
    expected_ids = {case["itemId"] for case in cases}
    if set(by_item) != expected_ids:
        raise ValueError("Batch response itemIds do not exactly match the input")

    batch_rows: list[dict[str, Any]] = []
    node_by_id = {row["itemId"]: row for row in node_rows}
    for case in cases:
        raw = dict(by_item[case["itemId"]])
        raw.pop("itemId", None)
        decision = _decision_dict(raw)
        _validate_membership(decision, case)
        batch_rows.append(
            {
                "itemId": case["itemId"],
                "description": case["description"],
                "decision": decision,
                "expected": case["expected"],
                "qualityPass": _matches_expected(decision, case["expected"]),
                "agreesWithNode": all(
                    decision.get(key) == node_by_id[case["itemId"]]["decision"].get(key)
                    for key in ("recommendation", "targetNodeId", "relationType")
                ),
            }
        )

    node_usage = _sum_usage([row["usage"] for row in node_rows])
    node_latency = round(sum(row["elapsedMs"] for row in node_rows), 1)
    return {
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "mode": "SHADOW_NO_DB_WRITES",
        "model": settings.model,
        "caseCount": len(cases),
        "nodeMode": {
            "callCount": len(cases),
            "qualityPassed": sum(row["qualityPass"] for row in node_rows),
            "usage": node_usage,
            "sequentialElapsedMs": node_latency,
            "results": node_rows,
        },
        "batchMode": {
            "callCount": 1,
            "qualityPassed": sum(row["qualityPass"] for row in batch_rows),
            "agreementWithNode": sum(row["agreesWithNode"] for row in batch_rows),
            "usage": batch_usage,
            "elapsedMs": batch_elapsed_ms,
            "results": batch_rows,
        },
        "comparison": {
            "callReductionPercent": _reduction(len(cases), 1),
            "inputTokenReductionPercent": _reduction(
                node_usage["inputTokens"], batch_usage["inputTokens"]
            ),
            "outputTokenReductionPercent": _reduction(
                node_usage["outputTokens"], batch_usage["outputTokens"]
            ),
            "totalTokenReductionPercent": _reduction(
                node_usage["totalTokens"], batch_usage["totalTokens"]
            ),
            "sequentialLatencyReductionPercent": _reduction(
                round(node_latency), round(batch_elapsed_ms)
            ),
        },
    }


def _write_report(report: dict[str, Any], output_root: Path) -> Path:
    run_id = datetime.now().strftime("%Y%m%d-%H%M%S")
    output_dir = output_root / run_id
    output_dir.mkdir(parents=True, exist_ok=False)
    (output_dir / "report.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    node = report["nodeMode"]
    batch = report["batchMode"]
    comparison = report["comparison"]
    lines = [
        "# B 모델 Node별 vs Batch Shadow 비교",
        "",
        f"- 모델: `{report['model']}`",
        f"- 케이스: {report['caseCount']}개",
        f"- DB 반영: 없음 (`{report['mode']}`)",
        "",
        "| 지표 | Node별 | Batch |",
        "|---|---:|---:|",
        f"| 호출 수 | {node['callCount']} | {batch['callCount']} |",
        f"| 정답 통과 | {node['qualityPassed']}/{report['caseCount']} | {batch['qualityPassed']}/{report['caseCount']} |",
        f"| 입력 토큰 | {node['usage']['inputTokens']} | {batch['usage']['inputTokens']} |",
        f"| 출력 토큰 | {node['usage']['outputTokens']} | {batch['usage']['outputTokens']} |",
        f"| 총 토큰 | {node['usage']['totalTokens']} | {batch['usage']['totalTokens']} |",
        f"| 순차 지연(ms) | {node['sequentialElapsedMs']} | {batch['elapsedMs']} |",
        "",
        f"- 호출 감소: {comparison['callReductionPercent']}%",
        f"- 총 토큰 감소: {comparison['totalTokenReductionPercent']}%",
        f"- Node별 결과와 Batch 일치: {batch['agreementWithNode']}/{report['caseCount']}",
        "",
        "## 케이스별 결과",
        "",
    ]
    batch_by_id = {row["itemId"]: row for row in batch["results"]}
    for row in node["results"]:
        batch_row = batch_by_id[row["itemId"]]
        lines.extend(
            [
                f"### {row['description']}",
                "",
                f"- Node별: `{row['decision']['recommendation']}` / `{row['decision'].get('targetNodeId')}` / `{row['decision'].get('relationType')}`",
                f"- Batch: `{batch_row['decision']['recommendation']}` / `{batch_row['decision'].get('targetNodeId')}` / `{batch_row['decision'].get('relationType')}`",
                f"- 정답 통과: Node별={row['qualityPass']}, Batch={batch_row['qualityPass']}",
                "",
            ]
        )
    (output_dir / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return output_dir


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--live",
        action="store_true",
        help="Perform five real B-model calls. Without this flag only validates the fixture.",
    )
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path("outputs") / "b-model-batch-comparison",
    )
    args = parser.parse_args()
    load_dotenv()
    cases = build_cases()
    if not args.live:
        batch_prompt = render_batch_prompt(cases)
        print(
            json.dumps(
                {
                    "status": "DRY_RUN_OK",
                    "caseCount": len(cases),
                    "nodePromptCharacters": sum(
                        len(
                            render_b_model_prompt(
                                source_node=case["source"],
                                retrieval_candidates=case["candidates"],
                            )
                        )
                        for case in cases
                    ),
                    "batchPromptCharacters": len(batch_prompt),
                },
                ensure_ascii=False,
            )
        )
        return 0
    report = run_live()
    output_dir = _write_report(report, args.output_root)
    print(json.dumps({"status": "OK", "outputDir": str(output_dir)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
