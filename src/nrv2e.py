# SPDX-License-Identifier: GPL-2.0
"""Mały, izolowany dekompresor NRV2E dla prototypu.

Implementacja Python jest portem algorytmu UCL NRV2E i pozostaje objęta
GPL-2.0. Szczegóły pochodzenia, skutków licencji i zamiany backendu opisuje
README. Moduł nie zna modelu aplikacji ani formatu dowodu.
"""

from __future__ import annotations

from dataclasses import dataclass

from .errors import DecompressionError


@dataclass(slots=True)
class _BitReader:
    data: bytes
    buffer_bits: int = 8
    offset: int = 0
    bits_left: int = 0
    control: int = 0

    def read_byte(self) -> int:
        if self.offset >= len(self.data):
            raise DecompressionError("unexpected end of NRV2E stream")
        value = self.data[self.offset]
        self.offset += 1
        return value

    def read_bit(self) -> int:
        if self.bits_left == 0:
            self.control = 0
            for _ in range(self.buffer_bits // 8):
                self.control = (self.control << 8) | self.read_byte()
            self.bits_left = self.buffer_bits
        self.bits_left -= 1
        return (self.control >> self.bits_left) & 1


def decompress_nrv2e(
    compressed: bytes,
    expected_size: int,
    buffer_bits: int = 8,
) -> bytes:
    """Dekompresuje NRV2E z buforem sterującym 8, 16 albo 32 bit.

    Rozmiar z nagłówka payloadu jest granicą wyjścia. Każdy offset i zapis
    podlega kontroli, więc uszkodzony kod nie może rozszerzać bufora bez limitu.
    """

    if not compressed or expected_size <= 0:
        raise DecompressionError("empty NRV2E input or output")
    if buffer_bits not in (8, 16, 32):
        raise DecompressionError("unsupported NRV2E control buffer size")

    reader = _BitReader(compressed, buffer_bits=buffer_bits)
    output = bytearray()
    last_offset = 1
    operations = 0
    max_operations = expected_size * 16 + 1_024

    while len(output) < expected_size:
        operations += 1
        if operations > max_operations:
            raise DecompressionError("NRV2E operation limit exceeded")

        if reader.read_bit() == 1:
            output.append(reader.read_byte())
            continue

        offset_code = 1
        offset_steps = 0
        while True:
            offset_steps += 1
            if offset_steps > 32:
                raise DecompressionError("invalid NRV2E offset")
            offset_code = offset_code * 2 + reader.read_bit()
            if reader.read_bit() == 1:
                break
            offset_code = (offset_code - 1) * 2 + reader.read_bit()

        if offset_code == 2:
            offset = last_offset
            length = reader.read_bit()
        else:
            encoded_offset = (offset_code - 3) * 0x100 + reader.read_byte()
            if encoded_offset == 0xFFFFFFFF:
                raise DecompressionError("NRV2E stream ended before declared size")
            length = (~encoded_offset) & 1
            offset = (encoded_offset >> 1) + 1
            last_offset = offset

        if length:
            length = 1 + reader.read_bit()
        elif reader.read_bit() == 1:
            length = 3 + reader.read_bit()
        else:
            length = 1
            while True:
                length = length * 2 + reader.read_bit()
                if reader.read_bit() == 1:
                    break
                if length > expected_size:
                    raise DecompressionError("invalid NRV2E match length")
            length += 3

        if offset > 0x500:
            length += 1

        copy_count = length + 1
        source_pos = len(output) - offset
        if source_pos < 0:
            raise DecompressionError("invalid NRV2E back-reference")
        if len(output) + copy_count > expected_size:
            raise DecompressionError("NRV2E output exceeds declared size")

        for _ in range(copy_count):
            output.append(output[source_pos])
            source_pos += 1

    return bytes(output)
