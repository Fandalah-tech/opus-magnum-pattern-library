from __future__ import annotations

import io
import struct
from pathlib import Path


class ParseError(ValueError):
    """Raised when an Opus Magnum binary file is malformed or unsupported."""


class BinaryReader:
    def __init__(self, data: bytes):
        self._stream = io.BytesIO(data)

    @property
    def offset(self) -> int:
        return self._stream.tell()

    def remaining(self) -> int:
        current = self.offset
        self._stream.seek(0, io.SEEK_END)
        end = self.offset
        self._stream.seek(current)
        return end - current

    def read_exact(self, size: int) -> bytes:
        data = self._stream.read(size)
        if len(data) != size:
            raise ParseError(f"Unexpected end of file at byte {self.offset}; wanted {size} bytes")
        return data

    def unpack(self, fmt: str):
        size = struct.calcsize(fmt)
        return struct.unpack(fmt, self.read_exact(size))[0]

    def int32(self) -> int:
        return self.unpack("<i")

    def uint64(self) -> int:
        return self.unpack("<Q")

    def byte(self) -> int:
        return self.unpack("<B")

    def sbyte(self) -> int:
        return self.unpack("<b")

    def boolean(self) -> bool:
        value = self.byte()
        if value not in (0, 1):
            raise ParseError(f"Invalid boolean {value} at byte {self.offset - 1}")
        return bool(value)

    def seven_bit_int(self) -> int:
        result = 0
        shift = 0
        for _ in range(5):
            value = self.byte()
            result |= (value & 0x7F) << shift
            if value & 0x80 == 0:
                return result
            shift += 7
        raise ParseError("Invalid 7-bit encoded integer")

    def string(self) -> str:
        length = self.seven_bit_int()
        try:
            return self.read_exact(length).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ParseError(f"Invalid UTF-8 string at byte {self.offset - length}") from exc


def read_bytes(source: str | Path | bytes | bytearray) -> bytes:
    if isinstance(source, (bytes, bytearray)):
        return bytes(source)
    return Path(source).read_bytes()
