"""PoC v3 채점기.

1단계(Minutes Extraction): 예측 items ↔ gold items 가중 이분 매칭(type 하드 조건).
2단계(Graph Judgment): 매칭된 항목에 대해서만 판정 지표를 계산.

scipy 의존성을 피하려고 linear_sum_assignment(Hungarian)를 순수 파이썬으로 구현한다
(회의당 항목 수가 작아 O(n^3)로 충분). 문자 유사도는 difflib.SequenceMatcher.ratio.
"""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import Any

from node_extraction.schemas.v3 import GRAPH_RESULTS, ItemType, JudgmentResult

# 매칭 점수 가중치. reserved 성분은 아직 미구현(값 0)이며 슬롯만 예약한다.
W_EVIDENCE = 0.45
W_TITLE = 0.25
W_CONTENT = 0.15
W_RESERVED = 0.15  # TODO(v3): 예약 성분(현재 0). 향후 화자/카테고리 등 추가 여지.
MATCH_THRESHOLD = 0.30
# Fallback: 근거 겹침 0이라 가중점수가 임계 미달이어도 제목이 충분히 유사하면 매칭 허용.
# (evidence 과의존으로 인한 FP·FN 이중 처벌 방지 — 가중식/헝가리안/titleSim(difflib) 계산은 불변)
# 채택된 기본 게이트: fallbackSim(문자 bigram 자카드) >= 0.22. titleSim(difflib)은 점수에만 쓰인다.
# 근거: dev 1런에서 difflib@0.45와 동률(오탐 0, 회복 동일)이나 잠재 오탐(예: m14↔m8 difflib 0.500)에
# 구조적으로 더 안전. 표본이 얇으므로(n=2) fallback 쌍을 리포트에 상시 노출해 감시한다.
TITLE_FALLBACK_THRESHOLD = 0.60  # difflib 게이트용(트라이얼/명시 지정 시)
FALLBACK_METRIC_DEFAULT = "jaccard"
FALLBACK_THRESHOLD_DEFAULT = 0.22
_BIG = 1e6

_NEW_DECISION = JudgmentResult.NEW_DECISION.value
_ATTACH = JudgmentResult.ATTACH.value
_UPDATE = JudgmentResult.UPDATE_ACTION.value
_MINUTES_ONLY = JudgmentResult.MINUTES_ONLY.value
_RESULTS = (_NEW_DECISION, _ATTACH, _MINUTES_ONLY)
_ACTION_RESULTS = (_UPDATE, _ATTACH, _MINUTES_ONLY)  # PoC 2차 생명주기 (UPDATE vs CREATE vs 제외)


# --- Hungarian (min-cost, square) --------------------------------------------
def linear_sum_assignment(cost: list[list[float]]) -> list[int]:
    """정사각 비용행렬의 최소비용 완전매칭. result[i] = row i에 배정된 col j."""
    n = len(cost)
    if n == 0:
        return []
    inf = float("inf")
    u = [0.0] * (n + 1)
    v = [0.0] * (n + 1)
    p = [0] * (n + 1)
    way = [0] * (n + 1)
    for i in range(1, n + 1):
        p[0] = i
        j0 = 0
        minv = [inf] * (n + 1)
        used = [False] * (n + 1)
        while True:
            used[j0] = True
            i0 = p[j0]
            delta = inf
            j1 = 0
            for j in range(1, n + 1):
                if not used[j]:
                    cur = cost[i0 - 1][j - 1] - u[i0] - v[j]
                    if cur < minv[j]:
                        minv[j] = cur
                        way[j] = j0
                    if minv[j] < delta:
                        delta = minv[j]
                        j1 = j
            for j in range(n + 1):
                if used[j]:
                    u[p[j]] += delta
                    v[j] -= delta
                else:
                    minv[j] -= delta
            j0 = j1
            if p[j0] == 0:
                break
        while j0:
            j1 = way[j0]
            p[j0] = p[j1]
            j0 = j1
    result = [-1] * n
    for j in range(1, n + 1):
        if p[j] != 0:
            result[p[j] - 1] = j - 1
    return result


# --- 유사도 성분 --------------------------------------------------------------
def _ratio(a: str, b: str) -> float:
    return SequenceMatcher(None, a or "", b or "").ratio()


def _char_bigrams(text: str) -> set[str]:
    """공백 제거 후 문자 bigram 집합. 한국어 조사 변형에 difflib보다 강함."""
    collapsed = "".join((text or "").split())
    if len(collapsed) < 2:
        return {collapsed} if collapsed else set()
    return {collapsed[i : i + 2] for i in range(len(collapsed) - 1)}


def _jaccard(a: str, b: str) -> float:
    """fallback 자격 판정 '전용' 지표(fallbackSim). 가중 점수의 titleSim(difflib)과 무관."""
    ga, gb = _char_bigrams(a), _char_bigrams(b)
    if not ga and not gb:
        return 1.0
    if not ga or not gb:
        return 0.0
    return len(ga & gb) / len(ga | gb)


def _segids(item: dict[str, Any]) -> set[str]:
    return {ev.get("segmentId") for ev in (item.get("evidence") or []) if ev.get("segmentId")}


def _prf(inter: int, pred: int, gold: int) -> dict[str, float | None]:
    precision = inter / pred if pred else None
    recall = inter / gold if gold else None
    if precision and recall and (precision + recall):
        f1 = 2 * precision * recall / (precision + recall)
    elif pred == 0 and gold == 0:
        precision = recall = f1 = 1.0
    else:
        f1 = 0.0
    return {"precision": _round(precision), "recall": _round(recall), "f1": _round(f1)}


def _evidence_f1(pred_ids: set[str], gold_ids: set[str]) -> float:
    if not pred_ids and not gold_ids:
        return 1.0
    if not pred_ids or not gold_ids:
        return 0.0
    inter = len(pred_ids & gold_ids)
    if inter == 0:
        return 0.0
    precision = inter / len(pred_ids)
    recall = inter / len(gold_ids)
    return 2 * precision * recall / (precision + recall)


def _round(value: float | None) -> float | None:
    return None if value is None else round(value, 4)


def _type(item: dict[str, Any]) -> str:
    return str(item.get("type")).upper()


def _result(judgment: dict[str, Any] | None) -> str:
    return str((judgment or {}).get("result") or _MINUTES_ONLY)


# --- 1단계 매칭 ---------------------------------------------------------------
def _fallback_value(metric: str, title_sim: float, fallback_sim: float) -> float:
    return fallback_sim if metric == "jaccard" else title_sim


def match_items(
    pred_items: list[dict[str, Any]],
    gold_items: list[dict[str, Any]],
    *,
    fallback_metric: str = FALLBACK_METRIC_DEFAULT,
    fallback_threshold: float = FALLBACK_THRESHOLD_DEFAULT,
) -> dict[str, Any]:
    """가중 점수·헝가리안·titleSim(difflib)은 불변. fallback '자격'만 확장한다.

    fallback_metric='difflib'면 titleSim(difflib)로, 'jaccard'면 fallbackSim(문자 bigram
    자카드)로 자격을 판정한다. 어느 경우든 가중 점수의 titleSim은 difflib 그대로다.
    """
    n_pred, n_gold = len(pred_items), len(gold_items)
    pairs: list[dict[str, Any]] = []
    if n_pred and n_gold:
        size = max(n_pred, n_gold)
        cost = [[0.0] * size for _ in range(size)]
        score_cache: dict[tuple[int, int], dict[str, float]] = {}
        for i in range(size):
            for j in range(size):
                if i >= n_pred or j >= n_gold:
                    cost[i][j] = 0.0  # dummy row/col
                    continue
                pred, gold = pred_items[i], gold_items[j]
                if _type(pred) != _type(gold):  # 하드 조건: type 동일
                    cost[i][j] = _BIG
                    continue
                ef1 = _evidence_f1(_segids(pred), _segids(gold))
                title = _ratio(pred.get("title", ""), gold.get("title", ""))
                content = _ratio(pred.get("content", ""), gold.get("content", ""))
                fb_sim = _jaccard(pred.get("title", ""), gold.get("title", ""))
                score = W_EVIDENCE * ef1 + W_TITLE * title + W_CONTENT * content + W_RESERVED * 0.0
                score_cache[(i, j)] = {"score": score, "evidenceF1": ef1, "titleSim": title, "contentSim": content, "fallbackSim": fb_sim}
                # eligibility = type 동일 AND (score>=0.3 OR fallbackValue>=threshold)
                eligible = score >= MATCH_THRESHOLD or _fallback_value(fallback_metric, title, fb_sim) >= fallback_threshold
                cost[i][j] = -score if eligible else _BIG
        assignment = linear_sum_assignment(cost)
        for i, j in enumerate(assignment):
            if i >= n_pred or j < 0 or j >= n_gold:
                continue
            components = score_cache.get((i, j))
            if components is None:
                continue
            fb_value = _fallback_value(fallback_metric, components["titleSim"], components["fallbackSim"])
            eligible = components["score"] >= MATCH_THRESHOLD or fb_value >= fallback_threshold
            if not eligible:  # 강제 배정된 부적격 쌍은 버린다
                continue
            pairs.append({
                "predIndex": i,
                "goldIndex": j,
                "predId": pred_items[i].get("id"),
                "goldId": gold_items[j].get("id"),
                "type": _type(pred_items[i]),
                "score": _round(components["score"]),
                "evidenceF1": _round(components["evidenceF1"]),
                "titleSim": _round(components["titleSim"]),
                "contentSim": _round(components["contentSim"]),
                "fallbackSim": _round(components["fallbackSim"]),
                # score가 임계 미달이라 fallback 자격으로만 성사된 쌍 (남용 감시용)
                "fallback": components["score"] < MATCH_THRESHOLD,
                "fallbackMetric": fallback_metric if components["score"] < MATCH_THRESHOLD else None,
            })

    matched_pred = {pair["predIndex"] for pair in pairs}
    matched_gold = {pair["goldIndex"] for pair in pairs}
    return {
        "pairs": pairs,
        "predCount": n_pred,
        "goldCount": n_gold,
        "matchedCount": len(pairs),
        "unmatchedPred": [i for i in range(n_pred) if i not in matched_pred],
        "unmatchedGold": [j for j in range(n_gold) if j not in matched_gold],
    }


def coverage_metrics(
    pred_items: list[dict[str, Any]],
    gold_items: list[dict[str, Any]],
    *,
    fallback_metric: str = FALLBACK_METRIC_DEFAULT,
    fallback_threshold: float = FALLBACK_THRESHOLD_DEFAULT,
) -> dict[str, Any]:
    """1:N coverage 보조 지표 (1:1 제약 없이 eligibility만으로 계산).

    granularity 불일치(gold 1개를 2~3개로 쪼개거나 합침)로 인한 1:1 매칭의 이중 처벌
    인공물을 걷어내고, 내용 자체를 잡았는지로 추출 품질을 본다. eligibility 기준은 1:1
    매칭과 동일: type 동일 AND (score>=0.3 OR fallbackValue>=threshold).
    """
    n_pred, n_gold = len(pred_items), len(gold_items)
    pred_covered = [False] * n_pred
    gold_covered = [False] * n_gold
    for i, pred in enumerate(pred_items):
        for j, gold in enumerate(gold_items):
            if _type(pred) != _type(gold):
                continue
            ef1 = _evidence_f1(_segids(pred), _segids(gold))
            title = _ratio(pred.get("title", ""), gold.get("title", ""))
            content = _ratio(pred.get("content", ""), gold.get("content", ""))
            fb = _jaccard(pred.get("title", ""), gold.get("title", ""))
            score = W_EVIDENCE * ef1 + W_TITLE * title + W_CONTENT * content
            if score >= MATCH_THRESHOLD or _fallback_value(fallback_metric, title, fb) >= fallback_threshold:
                pred_covered[i] = True
                gold_covered[j] = True
    precision = sum(pred_covered) / n_pred if n_pred else None
    recall = sum(gold_covered) / n_gold if n_gold else None
    if n_pred == 0 and n_gold == 0:
        f1 = precision = recall = 1.0
    elif precision and recall and (precision + recall):
        f1 = 2 * precision * recall / (precision + recall)
    else:
        f1 = 0.0
    return {
        "predCount": n_pred,
        "goldCount": n_gold,
        "coveredPred": sum(pred_covered),
        "coveredGold": sum(gold_covered),
        "precision": _round(precision),
        "recall": _round(recall),
        "f1": _round(f1),
    }


def _stage1_metrics(match: dict[str, Any], pred_items, gold_items, coverage: dict[str, Any]) -> dict[str, Any]:
    pairs = match["pairs"]
    minutes = _prf(len(pairs), match["predCount"], match["goldCount"])
    by_type: dict[str, Any] = {}
    for type_name in (ItemType.DECISION.value, ItemType.ACTION.value, ItemType.ISSUE.value):
        pred_n = sum(1 for it in pred_items if _type(it) == type_name)
        gold_n = sum(1 for it in gold_items if _type(it) == type_name)
        matched_n = sum(1 for pair in pairs if pair["type"] == type_name)
        by_type[type_name] = {"pred": pred_n, "gold": gold_n, "matched": matched_n, **_prf(matched_n, pred_n, gold_n)}
    # Evidence P/R/F1: 매칭된 쌍의 segmentId 집합 micro 비교.
    inter = pred_total = gold_total = 0
    for pair in pairs:
        pred_ids = _segids(pred_items[pair["predIndex"]])
        gold_ids = _segids(gold_items[pair["goldIndex"]])
        inter += len(pred_ids & gold_ids)
        pred_total += len(pred_ids)
        gold_total += len(gold_ids)
    return {
        "predCount": match["predCount"],
        "goldCount": match["goldCount"],
        "matchedCount": match["matchedCount"],
        "fallbackCount": sum(1 for pair in pairs if pair.get("fallback")),
        "minutes": minutes,
        "coverage": coverage,
        "byType": by_type,
        "evidence": _prf(inter, pred_total, gold_total),
    }


# --- 2단계 판정 채점 ----------------------------------------------------------
def _classify_gold(gold_judgment: dict[str, Any], gold_item_ids: set[str]) -> str:
    result = _result(gold_judgment)
    if result == _NEW_DECISION:
        return "A"
    if result == _ATTACH:
        target = str(gold_judgment.get("attachTo") or "")
        # 회의 내 item 참조(=새 결정 묶음)면 A, registry 결정 참조면 B.
        return "A" if target in gold_item_ids else "B"
    return "C"


def _attachment_correct(
    pred_j, gold_j, pred_to_gold: dict[str, str], gold_item_ids: set[str], pred_item_ids: set[str]
) -> bool:
    if _result(pred_j) != _ATTACH:
        return False
    gold_target = str(gold_j.get("attachTo") or "")
    pred_target = str(pred_j.get("attachTo") or "")
    if gold_target in gold_item_ids:
        # 회의 내 결정에 붙는 경우: 대상 item끼리 1단계 매칭에서 대응하는지로 판정.
        return pred_target in pred_item_ids and pred_to_gold.get(pred_target) == gold_target
    # registry(D-*) 결정에 붙는 경우: ID 문자열 정확 비교.
    return pred_target == gold_target


def _stage2_metrics(
    match: dict[str, Any], pred_items, pred_judgments, gold_judgments, retrieval_enabled: bool,
    pred_item_ids: set[str], gold_item_ids: set[str],
) -> dict[str, Any]:
    pred_map = {str(j.get("itemId")): j for j in pred_judgments}
    gold_map = {str(j.get("itemId")): j for j in gold_judgments}
    pred_to_gold = {str(pair["predId"]): str(pair["goldId"]) for pair in match["pairs"]}

    confusion = {g: {p: 0 for p in _RESULTS} for g in _RESULTS}
    op_correct = 0
    dec_gold = dec_hit = 0
    graph_pred = graph_hit = 0
    attach_gold = attach_hit = 0
    reason_gold = reason_hit = 0
    outcome = {key: {"count": 0, "correct": 0} for key in ("A", "B", "C")}

    for pair in match["pairs"]:
        pred_j = pred_map.get(str(pair["predId"]))
        gold_j = gold_map.get(str(pair["goldId"]))
        pred_r, gold_r = _result(pred_j), _result(gold_j)
        if pred_r in confusion.get(gold_r, {}):
            confusion[gold_r][pred_r] += 1
        if pred_r == gold_r:
            op_correct += 1
        if gold_r == _NEW_DECISION:
            dec_gold += 1
            dec_hit += pred_r == _NEW_DECISION
        if pred_r in GRAPH_RESULTS:
            graph_pred += 1
            graph_hit += gold_r in GRAPH_RESULTS
        if gold_r == _ATTACH:
            attach_gold += 1
            attach_hit += _attachment_correct(pred_j, gold_j, pred_to_gold, gold_item_ids, pred_item_ids)
        if gold_r == _MINUTES_ONLY and pred_r == _MINUTES_ONLY:
            reason_gold += 1
            reason_hit += str((pred_j or {}).get("reason")) == str((gold_j or {}).get("reason"))

        klass = _classify_gold(gold_j or {}, gold_item_ids)
        outcome[klass]["count"] += 1
        if klass in ("A", "B") and _result(gold_j) == _ATTACH:
            correct = _attachment_correct(pred_j, gold_j, pred_to_gold, gold_item_ids, pred_item_ids)
        elif klass == "C":
            correct = pred_r == _MINUTES_ONLY
        else:  # A with gold NEW_DECISION
            correct = pred_r == gold_r
        outcome[klass]["correct"] += bool(correct)

    # 그래프 오염: 미매칭 예측 항목 중 최종 판정이 그래프 진입(NEW_DECISION/ATTACH)인 건.
    unmatched_graph_details: list[dict[str, Any]] = []
    for index in match.get("unmatchedPred", []):
        item = pred_items[index]
        pred_r = _result(pred_map.get(str(item.get("id"))))
        if pred_r in GRAPH_RESULTS:
            unmatched_graph_details.append(
                {"predId": item.get("id"), "title": item.get("title"), "result": pred_r}
            )
    unmatched_graph = len(unmatched_graph_details)

    scored = match["matchedCount"]
    by_outcome = {
        "A_new_decision_cluster": _outcome_cell(outcome["A"]),
        "B_existing_decision_attach": {**_outcome_cell(outcome["B"]), "structurallyLimited": not retrieval_enabled},
        "C_minutes_only": _outcome_cell(outcome["C"]),
    }
    return {
        "scoredPairs": scored,
        "graphOperationAccuracy": _safe(op_correct, scored),
        "decisionRecall": _safe(dec_hit, dec_gold),
        "graphPrecision": _safe(graph_hit, graph_pred),
        # strict: 분모 = 매칭된 그래프 진입 + 미매칭 그래프 진입(전부 오답 취급).
        "graphPrecisionStrict": _safe(graph_hit, graph_pred + unmatched_graph),
        "unmatchedGraphEntries": unmatched_graph,
        "unmatchedGraphEntryDetails": unmatched_graph_details,
        "attachmentAccuracy": _safe(attach_hit, attach_gold),
        "minutesReasonMatch": _safe(reason_hit, reason_gold),
        "confusion": confusion,
        "byOutcomeType": by_outcome,
    }


def _lifecycle_metrics(match: dict[str, Any], pred_judgments, gold_judgments) -> dict[str, Any]:
    """PoC 2차: UPDATE vs CREATE 분류·entity resolution·changes 키집합·이슈→액션 ATTACH."""
    pred_map = {str(j.get("itemId")): j for j in pred_judgments}
    gold_map = {str(j.get("itemId")): j for j in gold_judgments}
    confusion = {g: {p: 0 for p in _ACTION_RESULTS} for g in _ACTION_RESULTS}
    action_correct = action_total = 0
    gold_update = pred_update = 0
    er_num = er_den = 0
    ck_num = ck_den = 0
    issue_num = issue_den = 0
    for pair in match["pairs"]:
        pred_j = pred_map.get(str(pair["predId"]))
        gold_j = gold_map.get(str(pair["goldId"]))
        pred_r, gold_r = _result(pred_j), _result(gold_j)
        if pair["type"] == "ACTION":
            if gold_r in confusion and pred_r in confusion[gold_r]:
                confusion[gold_r][pred_r] += 1
            action_total += 1
            action_correct += pred_r == gold_r
            gold_update += gold_r == _UPDATE
            pred_update += pred_r == _UPDATE
            if gold_r == _UPDATE and pred_r == _UPDATE:
                er_den += 1
                er_num += str((pred_j or {}).get("targetActionId")) == str((gold_j or {}).get("targetActionId"))
                ck_den += 1
                pred_keys = set((pred_j or {}).get("changes") or {})
                gold_keys = set((gold_j or {}).get("changes") or {})
                ok = pred_keys == gold_keys
                if ok and "status" in gold_keys:  # status 값만 예외적으로 비교 (dueDate 값은 자리표시자)
                    ok = (pred_j or {}).get("changes", {}).get("status") == (gold_j or {}).get("changes", {}).get("status")
                ck_num += bool(ok)
        # 이슈 → 기존 액션(A-*) ATTACH 정확도 (별도 표기)
        if pair["type"] == "ISSUE" and gold_r == _ATTACH and str((gold_j or {}).get("attachTo") or "").startswith("A-"):
            issue_den += 1
            issue_num += pred_r == _ATTACH and str((pred_j or {}).get("attachTo")) == str((gold_j or {}).get("attachTo"))
    return {
        "actionConfusion": confusion,
        "actionCount": action_total,
        "updateVsCreateAccuracy": _safe(action_correct, action_total),
        "goldUpdateCount": gold_update,
        "predUpdateCount": pred_update,
        "entityResolutionAccuracy": _safe(er_num, er_den),
        "entityResolutionDenom": er_den,
        "changesKeySetAccuracy": _safe(ck_num, ck_den),
        "changesDenom": ck_den,
        "issueToActionAttachAccuracy": _safe(issue_num, issue_den),
        "issueToActionDenom": issue_den,
    }


def _outcome_cell(cell: dict[str, int]) -> dict[str, Any]:
    return {"count": cell["count"], "correct": cell["correct"], "accuracy": _safe(cell["correct"], cell["count"])}


def _safe(num: int, den: int) -> float | None:
    return _round(num / den) if den else None


def evaluate_v3_case(
    pred_items: list[dict[str, Any]],
    pred_judgments: list[dict[str, Any]],
    gold_items: list[dict[str, Any]],
    gold_judgments: list[dict[str, Any]],
    *,
    retrieval_enabled: bool = False,
    extra_counts: dict[str, Any] | None = None,
    fallback_metric: str = FALLBACK_METRIC_DEFAULT,
    fallback_threshold: float = FALLBACK_THRESHOLD_DEFAULT,
) -> dict[str, Any]:
    match = match_items(pred_items, gold_items, fallback_metric=fallback_metric, fallback_threshold=fallback_threshold)
    coverage = coverage_metrics(pred_items, gold_items, fallback_metric=fallback_metric, fallback_threshold=fallback_threshold)
    pred_item_ids = {str(item.get("id")) for item in pred_items}
    gold_item_ids = {str(item.get("id")) for item in gold_items}
    return {
        "retrievalEnabled": retrieval_enabled,
        "stage1": _stage1_metrics(match, pred_items, gold_items, coverage),
        "stage2": _stage2_metrics(
            match, pred_items, pred_judgments, gold_judgments, retrieval_enabled, pred_item_ids, gold_item_ids
        ),
        "lifecycle": _lifecycle_metrics(match, pred_judgments, gold_judgments),
        "match": {"pairs": match["pairs"], "unmatchedPred": match["unmatchedPred"], "unmatchedGold": match["unmatchedGold"]},
        "counts": extra_counts or {},
    }


_OUTCOME_KEYS = ("A_new_decision_cluster", "B_existing_decision_attach", "C_minutes_only")


def _mean(values: list[float | None]) -> float | None:
    present = [value for value in values if value is not None]
    return round(sum(present) / len(present), 4) if present else None


def aggregate_by_condition(evaluations: list[dict[str, Any]]) -> dict[str, Any]:
    """조건별 macro 평균(회의 간 단순 평균, None 제외)과 카운트 합계를 낸다."""
    grouped: dict[str, list[dict[str, Any]]] = {}
    for evaluation in evaluations:
        grouped.setdefault(evaluation["condition"], []).append(evaluation)
    aggregates: dict[str, Any] = {}
    for condition, items in grouped.items():
        aggregates[condition] = {
            "meetings": [item["meetingId"] for item in items],
            "retrievalEnabled": items[0]["retrievalEnabled"],
            "minutes": {
                key: _mean([item["stage1"]["minutes"][key] for item in items])
                for key in ("precision", "recall", "f1")
            },
            "evidenceF1": _mean([item["stage1"]["evidence"]["f1"] for item in items]),
            "coverage": {
                key: _mean([item["stage1"]["coverage"][key] for item in items])
                for key in ("precision", "recall", "f1")
            },
            "graphOperationAccuracy": _mean([item["stage2"]["graphOperationAccuracy"] for item in items]),
            "decisionRecall": _mean([item["stage2"]["decisionRecall"] for item in items]),
            "graphPrecision": _mean([item["stage2"]["graphPrecision"] for item in items]),
            "graphPrecisionStrict": _mean([item["stage2"]["graphPrecisionStrict"] for item in items]),
            "unmatchedGraphEntries": sum(item["stage2"]["unmatchedGraphEntries"] for item in items),
            "fallbackCount": sum(item["stage1"]["fallbackCount"] for item in items),
            "attachmentAccuracy": _mean([item["stage2"]["attachmentAccuracy"] for item in items]),
            "minutesReasonMatch": _mean([item["stage2"]["minutesReasonMatch"] for item in items]),
            "byOutcomeType": {
                key: {
                    "accuracy": _mean([item["stage2"]["byOutcomeType"][key]["accuracy"] for item in items]),
                    "count": sum(item["stage2"]["byOutcomeType"][key]["count"] for item in items),
                    "structurallyLimited": bool(items[0]["stage2"]["byOutcomeType"][key].get("structurallyLimited")),
                }
                for key in _OUTCOME_KEYS
            },
            "demoted": sum(item["counts"].get("demoted", 0) for item in items),
            "invalidItems": sum(item["counts"].get("invalidItems", 0) for item in items),
            "lifecycle": _aggregate_lifecycle([item["lifecycle"] for item in items if "lifecycle" in item]),
        }
    return aggregates


def _aggregate_lifecycle(cells: list[dict[str, Any]]) -> dict[str, Any]:
    if not cells:
        return {}
    confusion = {g: {p: 0 for p in _ACTION_RESULTS} for g in _ACTION_RESULTS}
    for cell in cells:
        for g in _ACTION_RESULTS:
            for p in _ACTION_RESULTS:
                confusion[g][p] += cell.get("actionConfusion", {}).get(g, {}).get(p, 0)
    return {
        "updateVsCreateAccuracy": _mean([c["updateVsCreateAccuracy"] for c in cells]),
        "entityResolutionAccuracy": _mean([c["entityResolutionAccuracy"] for c in cells]),
        "changesKeySetAccuracy": _mean([c["changesKeySetAccuracy"] for c in cells]),
        "issueToActionAttachAccuracy": _mean([c["issueToActionAttachAccuracy"] for c in cells]),
        "goldUpdateCount": sum(c["goldUpdateCount"] for c in cells),
        "predUpdateCount": sum(c["predUpdateCount"] for c in cells),
        "actionConfusion": confusion,
        "runs": len(cells),
    }
