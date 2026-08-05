"""Deterministic synthetic gold dataset used only by evaluation tooling."""

from .scenarios import (
    DATASET_VERSION,
    ISOLATION_PROJECT_ID,
    MAIN_PROJECT_ID,
    SyntheticCaseSpec,
    SyntheticNodeSpec,
    build_synthetic_cases,
    build_synthetic_nodes,
    stable_uuid,
)
from .seed import SyntheticSeedReport, seed_synthetic_evaluation

__all__ = [
    "DATASET_VERSION",
    "ISOLATION_PROJECT_ID",
    "MAIN_PROJECT_ID",
    "SyntheticCaseSpec",
    "SyntheticNodeSpec",
    "SyntheticSeedReport",
    "build_synthetic_cases",
    "build_synthetic_nodes",
    "seed_synthetic_evaluation",
    "stable_uuid",
]
