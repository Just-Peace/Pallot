"""Read some members of TEC's ~1 GB campaign finance zip, over HTTP or from a file.

RemoteZip asks for the end of the file first: the zip's central directory, with every
member's offset, size and CRC (and the ETag, so a refresh can tell nothing changed from
that one small request). It then streams the file from the first member it needs to the
last in ONE request, inflating those members as they pass and skipping the rest. TEC
stores its members in no particular order, so fetching just the needed ones would take
about twenty ranges, and TEC's CloudFront blocks a burst like that ("Request blocked",
for hours); one long download is what it tolerates. That request carries If-Range, so a
zip TEC rebuilds mid-read is noticed rather than mixed with the old one, and a 403 or 429
stops everything (BlockedError).

LocalZip reads the same members from a zip downloaded in a browser.
"""

from __future__ import annotations

import io
import struct
import time
import zipfile
import zlib
from dataclasses import dataclass
from email.utils import formatdate
from pathlib import Path
from typing import Iterable, Iterator

import httpx

from .errors import BlockedError, FetchError, ZipChangedError

TAIL = 128 * 1024  # enough for the central directory of ~150 members
CHUNK = 1024 * 1024


@dataclass(frozen=True)
class Member:
    name: str
    offset: int  # of its local file header
    compressed: int
    size: int
    crc: int
    method: int  # zipfile.ZIP_STORED or ZIP_DEFLATED


@dataclass(frozen=True)
class Directory:
    members: dict[str, Member]
    etag: str | None
    last_modified: str | None
    size: int


def _directory(infos: Iterable[zipfile.ZipInfo], etag: str | None, last_modified: str | None, size: int) -> Directory:
    members = {
        info.filename: Member(info.filename, info.header_offset, info.compress_size, info.file_size, info.CRC, info.compress_type)
        for info in infos
        if not info.is_dir()
    }
    return Directory(members, etag, last_modified, size)


def _decompress(compressed: Iterator[bytes], member: Member) -> Iterator[bytes]:
    """Inflate a member's bytes as they arrive, checking its size and CRC at the end."""
    if member.method not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
        raise FetchError(f"{member.name}: unsupported compression method {member.method}")
    inflater = zlib.decompressobj(-zlib.MAX_WBITS) if member.method == zipfile.ZIP_DEFLATED else None
    crc = size = 0
    try:
        for block in compressed:
            data = inflater.decompress(block) if inflater else block
            if data:
                crc, size = zlib.crc32(data, crc), size + len(data)
                yield data
        if inflater:
            data = inflater.flush()
            if data:
                crc, size = zlib.crc32(data, crc), size + len(data)
                yield data
    except zlib.error as exc:
        raise FetchError(f"{member.name} arrived damaged ({exc})") from exc
    if crc != member.crc or size != member.size:
        raise FetchError(f"{member.name} arrived damaged (its size or CRC doesn't match the zip's directory)")


class _Tail(io.RawIOBase):
    """The last part of a remote file, posing as the whole file for zipfile, which only
    reads the end-of-directory records and the central directory."""

    def __init__(self, data: bytes, size: int):
        self._data, self._size, self._start, self._pos = data, size, size - len(data), 0

    def readable(self) -> bool:
        return True

    def seekable(self) -> bool:
        return True

    def tell(self) -> int:
        return self._pos

    def seek(self, offset: int, whence: int = io.SEEK_SET) -> int:
        base = {io.SEEK_SET: 0, io.SEEK_CUR: self._pos, io.SEEK_END: self._size}[whence]
        self._pos = base + offset
        return self._pos

    def readinto(self, buffer) -> int:
        if self._pos < self._start:
            raise FetchError("the zip's central directory is bigger than expected")
        data = self._data[self._pos - self._start : self._pos - self._start + len(buffer)]
        buffer[: len(data)] = data
        self._pos += len(data)
        return len(data)


class _Stream:
    """One ranged response, read forward only, knowing each byte's offset in the file."""

    def __init__(self, chunks: Iterator[bytes], position: int, owner: RemoteZip):
        self._chunks = chunks
        self._buffer = b""
        self._owner = owner
        self.position = position

    def _more(self) -> bool:
        try:
            chunk = next(self._chunks, None)
        except httpx.HTTPError as exc:  # raised while the caller reads a member, outside _span's try
            raise FetchError(f"the download from TEC failed ({type(exc).__name__}: {exc})") from exc
        if chunk is None:
            return False
        self._owner.downloaded += len(chunk)
        self._buffer += chunk
        return True

    def read(self, n: int) -> bytes:
        while len(self._buffer) < n and self._more():
            pass
        data, self._buffer = self._buffer[:n], self._buffer[n:]
        self.position += len(data)
        return data

    def chunks(self, n: int) -> Iterator[bytes]:
        """The next n bytes, as they arrive."""
        while n > 0:
            if not self._buffer and not self._more():
                raise FetchError("the download ended early")
            data, self._buffer = self._buffer[:n], self._buffer[n:]
            self.position += len(data)
            n -= len(data)
            yield data

    def skip_to(self, offset: int) -> None:
        if offset < self.position:
            raise FetchError("zip members out of order")
        for _ in self.chunks(offset - self.position):
            pass

    def member(self, member: Member) -> Iterator[bytes]:
        """The member at the current position: skip its local header, inflate its data."""
        header = self.read(30)
        if len(header) < 30 or header[:4] != b"PK\x03\x04":
            raise FetchError(f"{member.name}: expected a zip member header at byte {member.offset}")
        name_length, extra_length = struct.unpack("<HH", header[26:30])
        self.read(name_length + extra_length)
        return _decompress(self.chunks(member.compressed), member)


class RemoteZip:
    """A zip on a server that honours Range requests, read with two of them (the directory,
    then one stream), ``pause`` seconds apart."""

    def __init__(self, url: str, *, client: httpx.Client | None = None, pause: float = 10.0, user_agent: str | None = None):
        self.url = url
        self._client = client or httpx.Client(
            timeout=httpx.Timeout(60.0, read=120.0),
            follow_redirects=True,
            headers={"User-Agent": user_agent or "tec_cache (VoteBot personal ballot helper)"},
        )
        self._owns_client = client is None
        self._pause = pause
        self._last: float | None = None
        self._directory: Directory | None = None
        self.requests = 0
        self.downloaded = 0

    @property
    def source(self) -> str:
        return self.url

    def __enter__(self) -> RemoteZip:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._client.close()

    def _wait(self) -> None:
        if self._last is not None:
            delay = self._last + self._pause - time.monotonic()
            if delay > 0:
                time.sleep(delay)
        self._last = time.monotonic()
        self.requests += 1

    def _check(self, response: httpx.Response) -> None:
        if response.status_code in (403, 429):
            raise BlockedError(
                f"TEC's download server refused the request (HTTP {response.status_code}). It blocks bursts of "
                f"requests: try again in a few hours, or download {self.url} in a browser and use it with --zip."
            )
        if response.status_code >= 400:
            raise FetchError(f"HTTP {response.status_code} from {self.url}")

    def directory(self) -> Directory:
        if self._directory is not None:
            return self._directory
        self._wait()
        try:
            with self._client.stream("GET", self.url, headers={"Range": f"bytes=-{TAIL}"}) as response:
                self._check(response)
                if response.status_code != 206:
                    raise FetchError("TEC's server ignored the byte range; download the zip in a browser and use --zip")
                data = response.read()
        except httpx.HTTPError as exc:
            raise FetchError(f"couldn't download from TEC ({type(exc).__name__}: {exc})") from exc
        self.downloaded += len(data)
        total = response.headers.get("content-range", "").rpartition("/")[2]
        if not total.isdigit():
            raise FetchError("TEC's server didn't say how big the zip is")
        try:
            with zipfile.ZipFile(_Tail(data, int(total))) as archive:
                infos = archive.infolist()
        except zipfile.BadZipFile as exc:
            raise FetchError(f"TEC's file isn't a readable zip ({exc})") from exc
        self._directory = _directory(infos, response.headers.get("etag"), response.headers.get("last-modified"), int(total))
        return self._directory

    def read(self, names: Iterable[str]) -> Iterator[tuple[Member, Iterator[bytes]]]:
        """(member, its inflated bytes) in file order, from one request. Read each member's
        bytes before asking for the next."""
        directory = self.directory()
        by_offset = sorted(directory.members.values(), key=lambda m: m.offset)
        ends = {m.name: nxt.offset for m, nxt in zip(by_offset, by_offset[1:])}
        wanted = sorted((directory.members[name] for name in set(names)), key=lambda m: m.offset)
        if wanted:
            yield from self._span(wanted, ends.get(wanted[-1].name, directory.size), directory)

    def _span(self, members: list[Member], end: int, directory: Directory) -> Iterator[tuple[Member, Iterator[bytes]]]:
        start = members[0].offset
        headers = {"Range": f"bytes={start}-{end - 1}"}
        if directory.etag:
            headers["If-Range"] = directory.etag
        self._wait()
        try:
            with self._client.stream("GET", self.url, headers=headers) as response:
                self._check(response)
                if response.status_code != 206:
                    raise ZipChangedError("TEC replaced its zip during the refresh; nothing was written, so run it again")
                stream = _Stream(response.iter_bytes(CHUNK), start, self)
                for member in members:
                    stream.skip_to(member.offset)
                    yield member, stream.member(member)
        except httpx.HTTPError as exc:
            raise FetchError(f"the download from TEC failed ({type(exc).__name__}: {exc})") from exc


class LocalZip:
    """TEC's zip downloaded in a browser: the same members, no network."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self.requests = 0
        self.downloaded = 0
        try:
            self._archive = zipfile.ZipFile(self.path)
        except (OSError, zipfile.BadZipFile) as exc:
            raise FetchError(f"can't open {self.path} as a zip ({exc})") from exc

    @property
    def source(self) -> str:
        return str(self.path)

    def __enter__(self) -> LocalZip:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._archive.close()

    def directory(self) -> Directory:
        stat = self.path.stat()
        return _directory(
            self._archive.infolist(), f'"local-{stat.st_size}-{int(stat.st_mtime)}"',
            formatdate(stat.st_mtime, usegmt=True), stat.st_size,
        )

    def read(self, names: Iterable[str]) -> Iterator[tuple[Member, Iterator[bytes]]]:
        members = self.directory().members
        for member in sorted((members[name] for name in set(names)), key=lambda m: m.offset):
            yield member, self._chunks(member.name)

    def _chunks(self, name: str) -> Iterator[bytes]:
        try:
            with self._archive.open(name) as fh:  # zipfile checks the CRC
                while block := fh.read(CHUNK):
                    yield block
        except (OSError, zipfile.BadZipFile) as exc:
            raise FetchError(f"{name} in {self.path} is damaged ({exc})") from exc
