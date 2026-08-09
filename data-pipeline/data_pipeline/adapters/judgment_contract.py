"""Judgment-output contract boundaries.

The frozen PoC prompt emits only NEW_DECISION/ATTACH/UPDATE_ACTION/MINUTES_ONLY.
UNATTACHED is deliberately not part of that LLM contract.  The server adapter
may derive the internal UNATTACHED command from a narrow, explicit reason rule.
"""

from __future__ import annotations

from copy import deepcopy
from enum import Enum
from typing import Protocol


class PocJudgmentResult(str, Enum):
    NEW_DECISION = "NEW_DECISION"
    ATTACH = "ATTACH"
    UPDATE_ACTION = "UPDATE_ACTION"
    MINUTES_ONLY = "MINUTES_ONLY"


class JudgmentContractAdapter(Protocol):
    version: str

    def adapt(self, *, items: list[dict], judgments: list[dict]) -> list[dict]: ...


class IdentityJudgmentContractAdapter:
    """Return an isolated copy of the current M2 contract without semantic changes."""

    version = "identity-v1"

    def adapt(self, *, items: list[dict], judgments: list[dict]) -> list[dict]:
        del items
        return deepcopy(judgments)


class PocV4JudgmentContractAdapter:
    """Translate frozen PoC v4 output into the current deterministic server contract.

    Policy v1:
      * ACTION/ISSUE + MINUTES_ONLY(NO_RELATED_DECISION) -> UNATTACHED
      * DECISION MINUTES_ONLY never becomes UNATTACHED; an unconfirmed decision is
        minutes-only, because preserving it as a graph node would weaken the
        confirmation boundary.
      * LOW_CONFIDENCE/NOT_CONFIRMED/unknown reasons remain MINUTES_ONLY.
    """

    version = "poc-v4-to-server-v1"
    _GRAPH_RESULTS = {
        PocJudgmentResult.NEW_DECISION.value,
        PocJudgmentResult.ATTACH.value,
        PocJudgmentResult.UPDATE_ACTION.value,
    }

    def adapt(self, *, items: list[dict], judgments: list[dict]) -> list[dict]:
        item_types = {
            str(item.get("id")): str(item.get("type", "")).upper()
            for item in items
        }
        adapted: list[dict] = []
        for raw in judgments:
            judgment = deepcopy(raw)
            item_id = str(judgment.get("itemId"))
            result = str(judgment.get("result"))

            if result in self._GRAPH_RESULTS:
                adapted.append(judgment)
                continue

            if result != PocJudgmentResult.MINUTES_ONLY.value:
                # Preserve unknown values for the server validator to reject/demote.
                adapted.append(judgment)
                continue

            reason = str(judgment.get("reason") or "LOW_CONFIDENCE")
            item_type = item_types.get(item_id)
            if reason == "NO_RELATED_DECISION" and item_type in {"ACTION", "ISSUE"}:
                adapted.append({
                    "itemId": item_id,
                    "result": "UNATTACHED",
                    "reason": reason,
                })
            else:
                normalized_reason = (
                    reason if reason in {"NO_RELATED_DECISION", "LOW_CONFIDENCE", "NOT_CONFIRMED"}
                    else "LOW_CONFIDENCE"
                )
                adapted.append({
                    "itemId": item_id,
                    "result": "MINUTES_ONLY",
                    "reason": normalized_reason,
                })
        return adapted


def adapter_for_kind(kind: str) -> JudgmentContractAdapter:
    if kind == "IDENTITY":
        return IdentityJudgmentContractAdapter()
    if kind == "POC_V4_TO_SERVER":
        return PocV4JudgmentContractAdapter()
    raise ValueError(f"Unknown judgment adapter kind: {kind!r}")


__all__ = [
    "PocJudgmentResult",
    "JudgmentContractAdapter",
    "IdentityJudgmentContractAdapter",
    "PocV4JudgmentContractAdapter",
    "adapter_for_kind",
]
