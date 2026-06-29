from __future__ import annotations

import itertools
from typing import Any, Callable

from utils.parking_event import parking_event_seconds


def _walk_sec(leg: dict[str, Any]) -> int | None:
    if leg.get("walk_allowed") and leg.get("walk_time_sec") is not None:
        return int(leg["walk_time_sec"])
    return None


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

    # Greedy nearest-neighbor (car)
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
) -> list[int] | None:
    """주차장에서 출발하는 도보 방문 순서 (greedy)."""
    if not indices:
        return []
    remaining = set(indices)
    order: list[int] = []
    plat, plng = parking["lat"], parking["lng"]
    current = None

    while remaining:
        if current is None:
            nxt = min(
                remaining,
                key=lambda i: int(
                    get_leg(plat, plng, nodes[i]["lat"], nodes[i]["lng"]).get("walk_time_sec") or 999999
                ),
            )
        else:
            nxt = min(
                remaining,
                key=lambda i: int(
                    get_leg(
                        nodes[current]["lat"],
                        nodes[current]["lng"],
                        nodes[i]["lat"],
                        nodes[i]["lng"],
                    ).get("walk_time_sec")
                    or 999999
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
) -> int | None:
    """
    D → A → B → C → D 형태 도보 루프 + 주차 이벤트 비용(초).
    도보 불가 구간이 있으면 None.
    """
    if len(indices) < 2:
        return None

    order = _walk_order_from_parking(parking, indices, nodes, get_leg)
    if order is None:
        return None

    plat, plng = parking["lat"], parking["lng"]
    total = 0

    first = order[0]
    leg = get_leg(plat, plng, nodes[first]["lat"], nodes[first]["lng"])
    walk = _walk_sec(leg)
    if walk is None:
        return None
    total += walk
    total += parking_event_seconds(nodes[first], congestion_level)

    for a, b in zip(order, order[1:]):
        leg = travel_matrix[a][b]
        walk = _walk_sec(leg)
        if walk is None:
            return None
        total += walk
        total += parking_event_seconds(nodes[b], congestion_level)

    last = order[-1]
    leg = get_leg(nodes[last]["lat"], nodes[last]["lng"], plat, plng)
    walk = _walk_sec(leg)
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
    주차 거점 vs 직접 차량 이동 비용 비교.
    Returns: {use_parking, direct_cost_sec, hub_cost_sec, savings_sec}
    """
    if len(indices) < 2:
        return {
            "use_parking": False,
            "direct_cost_sec": 0,
            "hub_cost_sec": None,
            "savings_sec": 0,
        }

    direct = min_car_path_cost(indices, travel_matrix)
    if not parking:
        return {
            "use_parking": False,
            "direct_cost_sec": direct,
            "hub_cost_sec": None,
            "savings_sec": 0,
        }

    hub = hub_loop_cost_seconds(indices, parking, nodes, travel_matrix, get_leg, congestion_level)
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
