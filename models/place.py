from __future__ import annotations

import uuid
from typing import Any


def create_place() -> dict[str, Any]:
    return {
        "id": uuid.uuid4().hex[:8],
        "raw_input": "",
        "normalized_address": "",
        "lat": None,
        "lng": None,
        "type": "",
        "reservation_time": None,
        "geocode_error": None,
        "use_manual_address": False,
        "geocode_status": "pending",
        "poi_candidates": [],
        "matched_name": "",
        "poi_category": "",
    }


def place_display_name(place: dict[str, Any], index: int) -> str:
    name = str(place.get("type", "")).strip()
    if name:
        return name
    return f"장소 {index + 1}"


def place_selection_label(
    place: dict[str, Any],
    index: int,
    all_places: list[dict[str, Any]] | None = None,
) -> str:
    """Selectbox / 방문 규칙용 — 사용자가 입력한 장소명 표시."""
    name = place_display_name(place, index)
    if all_places:
        same_count = sum(
            1
            for j, p in enumerate(all_places)
            if place_display_name(p, j) == name
        )
        if same_count > 1:
            return f"{name} (장소 {index + 1})"
    return name


def place_label(place: dict[str, Any], index: int) -> str:
    return place_selection_label(place, index, None)
