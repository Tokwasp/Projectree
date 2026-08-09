"""Download one validated S3 object to a disposable local audio path."""

from __future__ import annotations

import hashlib
import tempfile
from contextlib import contextmanager
from pathlib import Path
from typing import Any, BinaryIO, Iterator, Protocol

from .errors import S3DownloadError
from .s3_events import S3ObjectRecord


class S3DownloadClient(Protocol):
    def download_fileobj(
        self,
        bucket: str,
        key: str,
        fileobj: BinaryIO,
        **kwargs: Any,
    ) -> None: ...


def _looks_like_audio(path: Path) -> bool:
    with path.open("rb") as audio:
        header = audio.read(16)
    suffix = path.suffix.lower()
    if suffix == ".wav":
        return len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WAVE"
    if suffix == ".flac":
        return header.startswith(b"fLaC")
    if suffix == ".ogg":
        return header.startswith(b"OggS")
    if suffix == ".m4a":
        return len(header) >= 8 and header[4:8] == b"ftyp"
    if suffix == ".mp3":
        return header.startswith(b"ID3") or (
            len(header) >= 2 and header[0] == 0xFF and header[1] & 0xE0 == 0xE0
        )
    if suffix == ".aac":
        return len(header) >= 2 and header[0] == 0xFF and header[1] & 0xF6 == 0xF0
    return False


def _md5(path: Path) -> str:
    digest = hashlib.md5(usedforsecurity=False)  # noqa: S324 - S3 ETag check
    with path.open("rb") as audio:
        for chunk in iter(lambda: audio.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class S3TemporaryDownloader:
    def __init__(
        self,
        client: S3DownloadClient,
        *,
        max_audio_bytes: int,
        temp_directory: Path | None = None,
    ):
        if max_audio_bytes <= 0:
            raise ValueError("max_audio_bytes must be positive")
        self._client = client
        self._max_audio_bytes = max_audio_bytes
        self._temp_directory = temp_directory

    @contextmanager
    def download(self, record: S3ObjectRecord) -> Iterator[Path]:
        if record.size > self._max_audio_bytes:
            raise S3DownloadError("S3 audio object exceeds the configured limit")
        suffix = Path(record.filename).suffix.lower()
        temp = tempfile.NamedTemporaryFile(
            prefix="data-pipeline-audio-",
            suffix=suffix,
            dir=self._temp_directory,
            delete=False,
        )
        path = Path(temp.name)
        try:
            extra_args = (
                {"ExtraArgs": {"VersionId": record.version_id}}
                if record.version_id
                else {}
            )
            try:
                with temp:
                    self._client.download_fileobj(
                        record.bucket,
                        record.object_key,
                        temp,
                        **extra_args,
                    )
            except Exception as exc:
                raise S3DownloadError("S3 audio download failed") from exc

            size = path.stat().st_size
            if size <= 0:
                raise S3DownloadError("Downloaded audio file is empty")
            if size > self._max_audio_bytes:
                raise S3DownloadError(
                    "Downloaded audio file exceeds the configured limit"
                )
            if size != record.size:
                raise S3DownloadError(
                    "Downloaded audio size does not match the S3 event"
                )
            if (
                record.version_id is None
                and record.etag is not None
                and len(record.etag) == 32
                and all(value in "0123456789abcdefABCDEF" for value in record.etag)
            ):
                digest = _md5(path)
                if digest.lower() != record.etag.lower():
                    raise S3DownloadError(
                        "Downloaded audio does not match the S3 event eTag"
                    )
            if not _looks_like_audio(path):
                raise S3DownloadError(
                    "Downloaded file does not match its allowed audio extension"
                )
            yield path
        finally:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass


__all__ = ["S3DownloadClient", "S3TemporaryDownloader"]
