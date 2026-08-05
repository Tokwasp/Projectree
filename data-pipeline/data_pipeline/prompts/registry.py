"""Version-locked prompt assets.

Prompt text is part of the model's behavior, not ordinary copy.  Assets are loaded
from a manifest and verified by SHA-256 before they can be rendered.  This keeps
semantic prompt changes separate from server-contract refactors.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


class PromptRegistryError(RuntimeError):
    """Base error for prompt registry failures."""


class PromptAssetNotFoundError(PromptRegistryError):
    """Raised when a requested prompt name is not registered."""


class PromptIntegrityError(PromptRegistryError):
    """Raised when a prompt file no longer matches its locked SHA-256."""


@dataclass(frozen=True)
class PromptAsset:
    name: str
    kind: str
    version: str
    change_type: str
    path: Path
    sha256: str
    renderer_version: str

    def read_verified(self) -> str:
        try:
            text = self.path.read_text(encoding="utf-8")
        except FileNotFoundError as exc:
            raise PromptRegistryError(f"Prompt asset file not found: {self.path}") from exc
        actual = hashlib.sha256(text.encode("utf-8")).hexdigest()
        if actual != self.sha256:
            raise PromptIntegrityError(
                f"Prompt asset SHA mismatch for {self.name}: expected={self.sha256}, actual={actual}"
            )
        return text


class PromptRegistry:
    def __init__(self, assets: dict[str, PromptAsset], *, schema_version: str, renderer_version: str) -> None:
        self._assets = dict(assets)
        self.schema_version = schema_version
        self.renderer_version = renderer_version

    @classmethod
    def from_manifest(cls, manifest_path: str | Path) -> "PromptRegistry":
        manifest = Path(manifest_path)
        raw = json.loads(manifest.read_text(encoding="utf-8"))
        renderer_version = str(raw["rendererVersion"])
        base = manifest.parent
        assets: dict[str, PromptAsset] = {}
        for row in raw.get("assets", []):
            asset = PromptAsset(
                name=str(row["name"]),
                kind=str(row["kind"]),
                version=str(row["version"]),
                change_type=str(row["changeType"]),
                path=(base / str(row["path"])).resolve(),
                sha256=str(row["sha256"]),
                renderer_version=renderer_version,
            )
            if asset.name in assets:
                raise PromptRegistryError(f"Duplicate prompt asset name: {asset.name}")
            assets[asset.name] = asset
        return cls(
            assets,
            schema_version=str(raw.get("schemaVersion", "1")),
            renderer_version=renderer_version,
        )

    def get(self, name: str) -> PromptAsset:
        try:
            return self._assets[name]
        except KeyError as exc:
            raise PromptAssetNotFoundError(f"Unknown prompt asset: {name}") from exc

    def load_text(self, name: str) -> str:
        return self.get(name).read_verified()

    def verify_all(self) -> None:
        for asset in self._assets.values():
            asset.read_verified()

    @property
    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._assets))


DEFAULT_MANIFEST_PATH = Path(__file__).with_name("assets") / "manifest.json"
DEFAULT_PROMPT_REGISTRY = PromptRegistry.from_manifest(DEFAULT_MANIFEST_PATH)


__all__ = [
    "PromptAsset",
    "PromptRegistry",
    "PromptRegistryError",
    "PromptAssetNotFoundError",
    "PromptIntegrityError",
    "DEFAULT_MANIFEST_PATH",
    "DEFAULT_PROMPT_REGISTRY",
]
