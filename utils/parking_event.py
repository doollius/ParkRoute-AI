from __future__ import annotations

from typing import Any

from utils.poi_category import (
    base_parking_event_minutes,
    congestion_extra_minutes,
    resolve_service_category,
)


def parking_event_minutes(
    node: dict[str, Any],
    congestion_level: str = "normal",
) -> int:
    """주차 이벤트 비용(분): Base Time + 혼잡도 보정."""
    category = resolve_service_category(
        tmap_category=node.get("poi_category"),
        place_name=node.get("type") or node.get("matched_name"),
        explicit=node.get("service_category"),
    )
    base = base_parking_event_minutes(category)
    extra = congestion_extra_minutes(congestion_level)
    return base + extra


def parking_event_seconds(
    node: dict[str, Any],
    congestion_level: str = "normal",
) -> int:
    return parking_event_minutes(node, congestion_level) * 60
