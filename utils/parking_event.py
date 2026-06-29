from __future__ import annotations

from typing import Any

from utils.poi_category import (
    congestion_extra_minutes,
    default_parking_minutes,
    parking_event_minutes as _parking_event_minutes,
)


def parking_event_minutes(
    node: dict[str, Any],
    congestion_level: str = "normal",
) -> int:
    """주차 이벤트 비용(분): POI 유형 Base Time + 혼잡도 보정."""
    return _parking_event_minutes(node, congestion_level)


def parking_lot_event_minutes(congestion_level: str = "normal") -> int:
    """거점 주차장에 차량으로 도착해 주차할 때 기본 소요(분)."""
    return default_parking_minutes() + congestion_extra_minutes(congestion_level)


def parking_lot_event_seconds(congestion_level: str = "normal") -> int:
    return parking_lot_event_minutes(congestion_level) * 60


def parking_event_seconds(
    node: dict[str, Any],
    congestion_level: str = "normal",
) -> int:
    return parking_event_minutes(node, congestion_level) * 60
