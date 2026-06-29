from __future__ import annotations

import itertools
from typing import Any, Callable

from constants.config import PARKING_SEARCH_PENALTY_SEC, PARKING_WALK_MAX_DISTANCE_M
from utils.parking_event import parking_event_seconds
from utils.walk_limits import walk_sec_for_leg


def _car_sec(leg: dict[str, Any]) -> int:
    return int(leg.get("car_time_sec") or 0)


def min_car_path_cost(indices: list[int], travel_matrix: list[list[dict[str, Any]]]) -> int:
    """클러스터 내 장소를 차량만으로 연결할 때 최소 비용(초)."""
    if len(indices) <= 1:
        return 0
    if len(indices) <= 6:
        best = float("inf")
        for perm in itertools.permutations(indices):
            cost = 0
            for a, b in zip(perm, perm[1:]):
                cost += _car_sec(travel_matrix[a][b])
            best = min(best, cost)
        return int(best)

    remaining = set(indices)
    start = indices[0]
    current = start
    remaining.discard(current)
    cost = 0
    while remaining:
        nxt = min(remaining, key=lambda j: _car_sec(travel_matrix[current][j]))
        cost += _car_sec(travel_matrix[current][nxt])
        current = nxt
        remaining.discard(nxt)
    return cost


def _walk_order_from_parking(
    parking: dict[str, Any],
    indices: list[int],
    nodes: list[dict[str, Any]],
    get_leg: Callable[..., dict[str, Any]],
    *,
    parking_mode: bool = False,
) -> list[int] | None:
    """주차장에서 출발하는 도보 방문 순서 (greedy)."""
    if not indices:
        return []
    remaining = set(indices)
    order: list[int] = []
    plat, plng = parking["lat"], parking["lng"]
    current = None

    def leg_time(a_lat, a_lng, b_lat, b_lng) -> int:
        leg = get_leg(a_lat, a_lng, b_lat, b_lng)
        sec = walk_sec_for_leg(leg, parking_mode=parking_mode)
        return sec if sec is not None else 999_999

    while remaining:
        if current is None:
            nxt = min(
                remaining,
                key=lambda i: leg_time(plat, plng, nodes[i]["lat"], nodes[i]["lng"]),
            )
        else:
            nxt = min(
                remaining,
                key=lambda i: leg_time(
                    nodes[current]["lat"],
                    nodes[current]["lng"],
                    nodes[i]["lat"],
                    nodes[i]["lng"],
                ),
            )
        order.append(nxt)
        remaining.discard(nxt)
        current = nxt
    return order


def hub_loop_cost_seconds(
    indices: list[int],
    parking: dict[str, Any],
    nodes: list[dict[str, Any]],
    travel_matrix: list[list[dict[str, Any]]],
    get_leg: Callable[..., dict[str, Any]],
    congestion_level: str,
    *,
    parking_mode: bool = False,
    max_walk_m: int = PARKING_WALK_MAX_DISTANCE_M,
) -> int | None:
    """
    P → A → B → C → P 도보 루프 + 주차 이벤트 비용(초).
    parking_mode: TMAP 도보 거리 ≤ max_walk_m 인 구간만 허용 (9분 규칙 미사용).
    """
    if len(indices) < 2:
        return None

    order = _walk_order_from_parking(
        parking, indices, nodes, get_leg, parking_mode=parking_mode
    )
    if order is None:
        return None

    plat, plng = parking["lat"], parking["lng"]
    total = 0

    first = order[0]
    leg = get_leg(plat, plng, nodes[first]["lat"], nodes[first]["lng"])
    walk = walk_sec_for_leg(leg, parking_mode=parking_mode, max_walk_m=max_walk_m)
    if walk is None:
        return None
    total += walk
    total += parking_event_seconds(nodes[first], congestion_level)

    for a, b in zip(order, order[1:]):
        leg = travel_matrix[a][b]
        walk = walk_sec_for_leg(leg, parking_mode=parking_mode, max_walk_m=max_walk_m)
        if walk is None:
            return None
        total += walk
        total += parking_event_seconds(nodes[b], congestion_level)

    last = order[-1]
    leg = get_leg(nodes[last]["lat"], nodes[last]["lng"], plat, plng)
    walk = walk_sec_for_leg(leg, parking_mode=parking_mode, max_walk_m=max_walk_m)
    if walk is None:
        return None
    total += walk

    return total


def compare_cluster_routing(
    indices: list[int],
    parking: dict[str, Any] | None,
    nodes: list[dict[str, Any]],
    travel_matrix: list[list[dict[str, Any]]],
    get_leg: Callable[..., dict[str, Any]],
    congestion_level: str = "normal",
) -> dict[str, Any]:
    """
    주차 거점 vs 직접 차량 이동 비용 비교 (도보 이동시간 최소화 모드).
    직행 경로에는 목적지마다 주차 탐색 부담을 가산.
    """
    if len(indices) < 2:
        return {
            "use_parking": False,
            "direct_cost_sec": 0,
            "hub_cost_sec": None,
            "savings_sec": 0,
        }

    direct = min_car_path_cost(indices, travel_matrix)
    direct += len(indices) * PARKING_SEARCH_PENALTY_SEC

    if not parking:
        return {
            "use_parking": False,
            "direct_cost_sec": direct,
            "hub_cost_sec": None,
            "savings_sec": 0,
        }

    hub = hub_loop_cost_seconds(
        indices, parking, nodes, travel_matrix, get_leg, congestion_level, parking_mode=False
    )
    if hub is None:
        return {
            "use_parking": False,
            "direct_cost_sec": direct,
            "hub_cost_sec": None,
            "savings_sec": 0,
        }

    use_parking = hub < direct
    return {
        "use_parking": use_parking,
        "direct_cost_sec": direct,
        "hub_cost_sec": hub,
        "savings_sec": max(0, direct - hub) if use_parking else 0,
    }
