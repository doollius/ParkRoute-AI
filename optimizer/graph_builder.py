from __future__ import annotations

from typing import Any

WALK_LIMIT_SEC = 9 * 60


def edge_cost(travel: dict[str, Any], minimize_walk: bool) -> int:
    """Weighted edge cost for OR-Tools (seconds scale)."""
    car = int(travel.get("car_time_sec") or 0)
    walk = travel.get("walk_time_sec")
    walk_allowed = travel.get("walk_allowed")

    if walk_allowed and walk is not None:
        walk_i = int(walk)
        if minimize_walk:
            return walk_i * 10 + car // 10
        return min(walk_i * 9, car * 7 // 10 + walk_i)
    return car * 10 if car > 0 else 999999


def build_cost_matrix(
    travel_matrix: list[list[dict[str, Any]]],
    minimize_walk: bool,
) -> list[list[int]]:
    n = len(travel_matrix)
    return [
        [0 if i == j else edge_cost(travel_matrix[i][j], minimize_walk) for j in range(n)]
        for i in range(n)
    ]


def cluster_by_walk(
    travel_matrix: list[list[dict[str, Any]]],
) -> list[list[int]]:
    """Group indices connected by <=9min walk."""
    n = len(travel_matrix)
    parent = list(range(n))

    def find(x: int) -> int:
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a: int, b: int) -> None:
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    for i in range(n):
        for j in range(i + 1, n):
            if travel_matrix[i][j].get("walk_allowed"):
                union(i, j)

    groups: dict[int, list[int]] = {}
    for i in range(n):
        groups.setdefault(find(i), []).append(i)
    return list(groups.values())
