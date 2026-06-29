from __future__ import annotations

from typing import Any

from utils.poi_category import parking_event_minutes as _parking_event_minutes


def parking_event_minutes(
    node: dict[str, Any],
    congestion_level: str = "normal",
) -> int:
    """주차 이벤트 비용(분): Base Time + 혼잡도 보정."""
    return _parking_event_minutes(node, congestion_level)


def parking_event_seconds(
    node: dict[str, Any],
    congestion_level: str = "normal",
) -> int:
    return parking_event_minutes(node, congestion_level) * 60
