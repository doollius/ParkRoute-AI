from __future__ import annotations

import re
from typing import Any


def hhmm_to_minutes(value: str) -> int | None:
    if not value:
        return None
    m = re.fullmatch(r"(\d{2}):(\d{2})", value.strip())
    if not m:
        return None
    hour, minute = int(m.group(1)), int(m.group(2))
    if hour > 23 or minute > 59:
        return None
    return hour * 60 + minute


def minutes_to_hhmm(minutes: int) -> str:
    minutes = max(0, min(minutes, 23 * 60 + 59))
    h, m = divmod(minutes, 60)
    return f"{h:02d}:{m:02d}"


def minutes_to_seconds(minutes: int) -> int:
    return minutes * 60


def simulate_arrival_times(
    order: list[int],
    travel_matrix: list[list[dict[str, Any]]],
    trip_start_minutes: int,
) -> list[int]:
    if not order:
        return []
    arrivals = [trip_start_minutes]
    current = trip_start_minutes
    for i in range(1, len(order)):
        prev_node = order[i - 1]
        node = order[i]
        leg = travel_matrix[prev_node][node]
        if leg.get("walk_allowed") and leg.get("walk_time_sec") is not None:
            if int(leg["walk_time_sec"]) <= int(leg.get("car_time_sec") or 999999):
                travel_min = max(1, int(leg["walk_time_sec"]) // 60)
            else:
                travel_min = max(1, int(leg["car_time_sec"]) // 60)
        else:
            travel_min = max(1, int(leg.get("car_time_sec") or 0) // 60)
        current += travel_min
        arrivals.append(current)
    return arrivals


def check_reservation_feasible(
    order: list[int],
    nodes: list[dict],
    travel_matrix: list[list[dict[str, Any]]],
    trip_start_minutes: int,
) -> list[str]:
    arrivals = simulate_arrival_times(order, travel_matrix, trip_start_minutes)
    errors: list[str] = []
    for node_idx, arrival_min in zip(order, arrivals):
        res = nodes[node_idx].get("reservation_time")
        if not res:
            continue
        res_min = hhmm_to_minutes(res)
        if res_min is None:
            continue
        if arrival_min > res_min:
            name = nodes[node_idx].get("normalized_address") or nodes[node_idx].get("raw_input")
            errors.append(
                f"예약 시간 위반: {name} (예약 {res}, 예상 도착 {minutes_to_hhmm(arrival_min)})"
            )
    return errors
