from __future__ import annotations

from dataclasses import dataclass

@dataclass(frozen=True, slots=True)
class KeyPayloadPair:
    key: str
    payload: dict