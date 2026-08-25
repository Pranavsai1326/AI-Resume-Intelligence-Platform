"""Bounded upload reading: streaming size enforcement and guaranteed cleanup."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.core.errors import EmptyFileError, FileTooLargeError
from app.documents.tempfile_scope import SPOOL_THRESHOLD_BYTES, bounded_spool, read_upload_bounded


class _FakeUpload:
    """Minimal stand-in for Starlette's UploadFile: chunked async reads."""

    def __init__(self, data: bytes, chunk_size: int = 1024) -> None:
        self._data = data
        self._chunk_size = chunk_size
        self._offset = 0

    async def read(self, size: int = -1) -> bytes:
        read_size = self._chunk_size if size < 0 else size
        chunk = self._data[self._offset : self._offset + read_size]
        self._offset += len(chunk)
        return chunk


async def test_reads_small_upload_fully(settings) -> None:
    data = b"hello world" * 100
    result = await read_upload_bounded(_FakeUpload(data), settings)
    assert result == data


async def test_rejects_empty_upload(settings) -> None:
    with pytest.raises(EmptyFileError):
        await read_upload_bounded(_FakeUpload(b""), settings)


async def test_aborts_mid_stream_when_oversized(settings) -> None:
    """The check happens as bytes arrive - the full oversized file is never fully buffered."""
    oversized = b"x" * (settings.max_upload_bytes + 1024)
    with pytest.raises(FileTooLargeError):
        await read_upload_bounded(_FakeUpload(oversized, chunk_size=4096), settings)


async def test_exactly_at_the_limit_is_accepted(settings) -> None:
    data = b"y" * settings.max_upload_bytes
    result = await read_upload_bounded(_FakeUpload(data), settings)
    assert len(result) == settings.max_upload_bytes


async def test_small_upload_never_touches_disk(settings) -> None:
    data = b"small file" * 10
    await read_upload_bounded(_FakeUpload(data), settings)
    temp_dir = Path(settings.temp_dir)
    assert list(temp_dir.iterdir()) == []  # noqa: ASYNC240


async def test_large_upload_spills_to_the_controlled_temp_dir_and_is_cleaned_up(
    settings,
) -> None:
    """Bytes past the spool threshold land in our own temp dir, then vanish when done."""
    data = b"z" * (SPOOL_THRESHOLD_BYTES + 1024)
    with bounded_spool(settings) as spooled:
        spooled.write(data)
        spooled.seek(0)
        temp_dir = Path(settings.temp_dir)
        assert any(temp_dir.iterdir()), "expected a spilled file while the scope is open"  # noqa: ASYNC240

    assert list(Path(settings.temp_dir).iterdir()) == []  # noqa: ASYNC240


async def test_temp_file_is_removed_even_on_exception(settings) -> None:
    temp_dir = Path(settings.temp_dir)
    with pytest.raises(RuntimeError):
        with bounded_spool(settings) as spooled:
            spooled.write(b"a" * (SPOOL_THRESHOLD_BYTES + 1024))
            raise RuntimeError("boom")
    assert list(temp_dir.iterdir()) == []  # noqa: ASYNC240
