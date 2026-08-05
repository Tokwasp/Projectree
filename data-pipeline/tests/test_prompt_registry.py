from __future__ import annotations

import json
from pathlib import Path

import pytest

from data_pipeline.adapters import IdentityJudgmentContractAdapter
from data_pipeline.prompts import (
    DEFAULT_PROMPT_REGISTRY,
    EXTRACTION_ASSET,
    JUDGMENT_ASSET,
    get_prompt_profile,
    PromptIntegrityError,
    PromptRegistry,
)


def test_default_prompt_assets_are_hash_locked():
    DEFAULT_PROMPT_REGISTRY.verify_all()
    assert EXTRACTION_ASSET.read_verified()
    assert JUDGMENT_ASSET.read_verified()
    lts = get_prompt_profile("poc-v4-lts")
    assert lts.extraction_asset.read_verified()
    assert lts.judgment_asset.read_verified()
    assert lts.extraction_asset.sha256 == "d719d6bcfbf544268bede4a79b17cf04eeffd2ce81f50c86eb624db3482b7b1d"
    assert lts.judgment_asset.sha256 == "258e5b42b74f2f1a25960e9eaf4f15d5894f77e48088b6938eaaf481d4f1c352"


def test_prompt_registry_rejects_tampered_asset(tmp_path: Path):
    prompt_file = tmp_path / "prompt.md"
    prompt_file.write_text("original", encoding="utf-8")
    manifest = {
        "schemaVersion": "1",
        "rendererVersion": "test",
        "assets": [
            {
                "name": "test-prompt",
                "kind": "JUDGMENT",
                "version": "1",
                "changeType": "CONTRACT",
                "path": "prompt.md",
                "sha256": "0682c5f2076f099c34f96e3b4f8b9f07131f5d43d2b7f51c63c17dce3f7f719d",
            }
        ],
    }
    # Use the actual hash first, then tamper with the file.
    import hashlib

    manifest["assets"][0]["sha256"] = hashlib.sha256(b"original").hexdigest()
    manifest_path = tmp_path / "manifest.json"
    manifest_path.write_text(json.dumps(manifest), encoding="utf-8")
    registry = PromptRegistry.from_manifest(manifest_path)
    assert registry.load_text("test-prompt") == "original"

    prompt_file.write_text("tampered", encoding="utf-8")
    with pytest.raises(PromptIntegrityError):
        registry.load_text("test-prompt")


def test_identity_judgment_adapter_preserves_value_but_not_reference():
    source = [{"itemId": "m1", "result": "NEW_DECISION", "category": "BACKEND"}]
    adapted = IdentityJudgmentContractAdapter().adapt(items=[], judgments=source)
    assert adapted == source
    assert adapted is not source
    assert adapted[0] is not source[0]


def test_default_profile_is_complete_poc_pair_and_candidate_is_explicit():
    from data_pipeline.prompts import (
        DEFAULT_PIPELINE_PROFILE_NAME,
        get_pipeline_profile,
    )

    assert DEFAULT_PIPELINE_PROFILE_NAME == "poc-lts"
    default = get_pipeline_profile()
    assert default.name == "poc-lts"
    assert default.extraction_asset.name == "extraction-poc-v3-lts"
    assert default.judgment_asset.name == "judgment-poc-v4-lts"
    assert default.judgment_adapter_kind == "POC_V4_TO_SERVER"

    candidate = get_pipeline_profile("m2-current-candidate")
    assert candidate.extraction_asset.name == "extraction-m2-current"
    assert candidate.judgment_asset.name == "judgment-m2-current"
    assert candidate.status == "CANDIDATE"


def test_step2_profile_aliases_resolve_to_canonical_pairs():
    from data_pipeline.prompts import get_pipeline_profile

    assert get_pipeline_profile("poc-v4-lts").name == "poc-lts"
    assert get_pipeline_profile("m2-current").name == "m2-current-candidate"
