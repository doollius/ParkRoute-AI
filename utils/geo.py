from __future__ import annotations

import math


def haversine_m(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dlng / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def coord_key(lat: float, lng: float) -> str:
    return f"{lat:.5f},{lng:.5f}"


# Rules.md ER-009 fallback speeds
CAR_SPEED_KMH = 40
WALK_SPEED_KMH = 4


def estimate_travel_sec(
    lat1: float,
    lng1: float,
    lat2: float,
    lng2: float,
    mode: str,
) -> dict[str, int]:
    distance_m = int(haversine_m(lat1, lng1, lat2, lng2))
    speed_kmh = WALK_SPEED_KMH if mode == "walk" else CAR_SPEED_KMH
    speed_mps = speed_kmh * 1000 / 3600
    time_sec = max(60, int(distance_m / speed_mps)) if speed_mps > 0 else 60
    return {"time_sec": time_sec, "distance_m": distance_m}

