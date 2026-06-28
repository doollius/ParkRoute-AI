from __future__ import annotations

import uuid
from typing import Any

PLACE_TYPES = ["숙소", "맛집", "카페", "관광지"]


def create_place() -> dict[str, Any]:
    return {
        "id": uuid.uuid4().hex[:8],
        "raw_input": "",
        "normalized_address": "",
        "lat": None,
        "lng": None,
        "type": "맛집",
        "reservation_time": None,
        "geocode_error": None,
    }


def place_label(place: dict[str, Any], index: int) -> str:
    addr = place.get("normalized_address") or place.get("raw_input") or f"장소 {index + 1}"
    if len(addr) > 40:
        addr = addr[:37] + "..."
    return f"{index + 1}. [{place.get('type', '?')}] {addr}"
