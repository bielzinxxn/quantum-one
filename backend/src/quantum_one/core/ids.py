"""UUIDv7 (RFC 9562): ordenável por tempo. Python 3.12 não tem `uuid.uuid7` nativo.

Layout (128 bits): unix_ts_ms(48) | ver=7(4) | rand_a(12) | var=0b10(2) | rand_b(62)
"""

from __future__ import annotations

import os
import time
import uuid


def uuid7(now_ms: int | None = None) -> uuid.UUID:
    ms = int(time.time() * 1000) if now_ms is None else now_ms
    rand = int.from_bytes(os.urandom(10), "big")  # 80 bits
    rand_a = rand >> 68  # 12 bits
    rand_b = rand & ((1 << 62) - 1)  # 62 bits
    value = ((ms & ((1 << 48) - 1)) << 80) | (0x7 << 76) | (rand_a << 64) | (0b10 << 62) | rand_b
    return uuid.UUID(int=value)
