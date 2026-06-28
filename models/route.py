from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class RouteStop:
    id: str
    label: str
    name: str
    lat: float
    lng: float
    kind: str = "place"
    type: str | None = None
    arrival_time: str | None = None
    reservation_time: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RouteStop:
        return cls(
            id=data["id"],
            label=data.get("label", "?"),
            name=data.get("name", ""),
            lat=float(data["lat"]),
            lng=float(data["lng"]),
            kind=data.get("kind", "place"),
            type=data.get("type"),
            arrival_time=data.get("arrival_time"),
            reservation_time=data.get("reservation_time"),
        )


@dataclass
class RouteSegment:
    from_label: str
    to_label: str
    mode: str
    time_sec: int
    distance_m: int = 0
    from_id: str = ""
    to_id: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RouteSegment:
        return cls(
            from_label=data.get("from_label", "?"),
            to_label=data.get("to_label", "?"),
            mode=data.get("mode", "car"),
            time_sec=int(data.get("time_sec") or 0),
            distance_m=int(data.get("distance_m") or 0),
            from_id=data.get("from_id", ""),
            to_id=data.get("to_id", ""),
        )


@dataclass
class RouteResult:
    stops: list[RouteStop] = field(default_factory=list)
    segments: list[RouteSegment] = field(default_factory=list)
    summary: dict[str, Any] = field(default_factory=dict)
    warnings: list[str] = field(default_factory=list)
    explanation: str = ""
    message: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> RouteResult:
        return cls(
            stops=[RouteStop.from_dict(s) for s in data.get("stops", [])],
            segments=[RouteSegment.from_dict(s) for s in data.get("segments", [])],
            summary=dict(data.get("summary") or {}),
            warnings=list(data.get("warnings") or []),
            explanation=data.get("explanation") or "",
            message=data.get("message") or "",
        )
