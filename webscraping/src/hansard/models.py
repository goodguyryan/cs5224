"""The parsed response and its original bytes travel together."""

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class FetchedJSON:
    payload: Any
    raw_bytes: bytes
