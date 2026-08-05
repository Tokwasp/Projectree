"""Runtime quarantine for legacy graph mutation entry points."""

from __future__ import annotations

import os

from .errors import LegacyGraphMutationDisabledError

_TEST_FLAG = "DATA_PIPELINE_UNSAFE_ENABLE_LEGACY_GRAPH_MUTATION_FOR_TESTS"
_MANUAL_MERGE_FLAG = "ENABLE_LEGACY_MANUAL_MERGE_API"


def require_legacy_graph_mutation_test_mode(entry_point: str) -> None:
    """Allow historical regression tests, but never default product calls."""

    enabled_for_tests = os.getenv(_TEST_FLAG) == "1"
    running_under_pytest = bool(os.getenv("PYTEST_CURRENT_TEST"))
    if enabled_for_tests and running_under_pytest:
        return
    raise LegacyGraphMutationDisabledError(
        f"{entry_point} is a quarantined legacy graph mutation path; "
        "use complete_initial_review and the separate final-approval services"
    )


def require_legacy_manual_merge_enabled(entry_point: str) -> None:
    """Keep reversible legacy merge code, but disable product API by default."""

    if os.getenv(_MANUAL_MERGE_FLAG, "false").strip().lower() in {
        "1",
        "true",
        "yes",
    }:
        return
    raise LegacyGraphMutationDisabledError(
        f"{entry_point} is disabled; automatic absorptive MERGE is the product path"
    )


__all__ = [
    "require_legacy_graph_mutation_test_mode",
    "require_legacy_manual_merge_enabled",
]
