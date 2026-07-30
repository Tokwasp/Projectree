"""Runtime quarantine for legacy graph mutation entry points."""

from __future__ import annotations

import os

from .errors import LegacyGraphMutationDisabledError

_TEST_FLAG = "DATA_PIPELINE_UNSAFE_ENABLE_LEGACY_GRAPH_MUTATION_FOR_TESTS"


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


__all__ = ["require_legacy_graph_mutation_test_mode"]
