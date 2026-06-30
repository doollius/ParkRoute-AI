from __future__ import annotations

from typing import Any, Callable

from api.tmap_api import TmapApiError, get_car_route_matrix
from constants.config import PARKING_HAVERSINE_PREFILTER_M, WALK_TIME_LIMIT_MINUTES
from optimizer.parking_graph import ClusterPlan
from services import map_service
from utils.geo import estimate_travel_sec, haversine_m, zero_route_metrics

WALK_LIMIT_SEC = WALK_TIME_LIMIT_MINUTES * 60


def _collect_refine_walk_targets(
    order: list[int],
    nodes: list[dict[str, Any]],
    cluster_plan: ClusterPlan | None,
) -> tuple[set[tuple[int, int]], list[tuple[float, float, float, float]]]:
    index_pairs: set[tuple[int, int]] = set()
    for i in range(len(order) - 1):
        index_pairs.add((order[i], order[i + 1]))

    coord_pairs: list[tuple[float, float, float, float]] = []
    if cluster_plan:
        for cid, parking in cluster_plan.cluster_parking.items():
            if not cluster_plan.cluster_use_parking.get(cid):
                continue
            plat, plng = float(parking["lat"]), float(parking["lng"])
            for idx in cluster_plan.clusters[cid]:
                nlat, nlng = float(nodes[idx]["lat"]), float(nodes[idx]["lng"])
                coord_pairs.append((plat, plng, nlat, nlng))
                coord_pairs.append((nlat, nlng, plat, plng))

    return index_pairs, coord_pairs


def refine_travel_matrix(
    nodes: list[dict[str, Any]],
    order: list[int],
    cluster_plan: ClusterPlan | None,
    base_matrix: list[list[dict[str, Any]]],
    on_progress: Callable[[str], None] | None = None,
) -> list[list[dict[str, Any]]]:
    """Pass 2 — 차량 Matrix 1회 + 확정 경로·hub 구간만 TMAP 도보."""
    n = len(nodes)
    coords = [(float(node["lat"]), float(node["lng"])) for node in nodes]
    matrix = [[dict(leg) for leg in row] for row in base_matrix]
    car_matrix_error: str | None = None
    car_matrix_estimated = False

    if on_progress:
        on_progress("3/4 TMAP 차량 이동시간 일괄 계산…")

    try:
        car_grid = get_car_route_matrix(coords)
    except TmapApiError as exc:
        car_matrix_estimated = True
        car_matrix_error = str(exc)
        car_grid = [
            [
                zero_route_metrics()
                if i == j
                else estimate_travel_sec(coords[i][0], coords[i][1], coords[j][0], coords[j][1], "car")
                for j in range(n)
            ]
            for i in range(n)
        ]

    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            matrix[i][j]["car_time_sec"] = int(car_grid[i][j].get("time_sec") or 0)
            matrix[i][j]["car_distance_m"] = int(car_grid[i][j].get("distance_m") or 0)
            matrix[i][j]["car_estimated"] = car_matrix_estimated or bool(car_grid[i][j].get("estimated"))

    index_pairs, coord_pairs = _collect_refine_walk_targets(order, nodes, cluster_plan)

    walk_jobs: list[tuple[str, int, int] | tuple[str, float, float, float, float]] = []
    for i, j in index_pairs:
        a, b = nodes[i], nodes[j]
        if haversine_m(float(a["lat"]), float(a["lng"]), float(b["lat"]), float(b["lng"])) <= PARKING_HAVERSINE_PREFILTER_M:
            walk_jobs.append(("idx", i, j))
    for flat, flng, tlat, tlng in coord_pairs:
        walk_jobs.append(("coord", flat, flng, tlat, tlng))

    total_walk = max(1, len(walk_jobs))
    for done, job in enumerate(walk_jobs, start=1):
        if on_progress:
            pct = min(99, int(done / total_walk * 100))
            on_progress(f"3/4 TMAP 도보 이동시간 계산… ({pct}%)")

        if job[0] == "idx":
            _, i, j = job
            a, b = nodes[i], nodes[j]
            flat, flng = float(a["lat"]), float(a["lng"])
            tlat, tlng = float(b["lat"]), float(b["lng"])
            walk, walk_est, walk_err = map_service._fetch_walk_leg(flat, flng, tlat, tlng)
            matrix[i][j] = map_service._merge_walk_into_leg(
                matrix[i][j],
                walk,
                walk_est,
                walk_err or car_matrix_error,
            )
            map_service._cache_leg(flat, flng, tlat, tlng, matrix[i][j])
        else:
            _, flat, flng, tlat, tlng = job
            walk, walk_est, walk_err = map_service._fetch_walk_leg(flat, flng, tlat, tlng)
            cached = map_service._cache().get(map_service._leg_key(flat, flng, tlat, tlng))
            car = {
                "time_sec": int(cached.get("car_time_sec") or 0) if cached else 0,
                "distance_m": int(cached.get("car_distance_m") or 0) if cached else 0,
            }
            leg = map_service._leg_from_parts(
                car,
                car_estimated=bool(cached and cached.get("car_estimated")),
                walk=walk,
                walk_estimated=walk_est,
                walk_allowed=int(walk["time_sec"]) <= WALK_LIMIT_SEC,
                error=walk_err or car_matrix_error,
            )
            map_service._cache_leg(flat, flng, tlat, tlng, leg)

    for i in range(n):
        for j in range(n):
            if i != j:
                a, b = nodes[i], nodes[j]
                map_service._cache_leg(
                    float(a["lat"]),
                    float(a["lng"]),
                    float(b["lat"]),
                    float(b["lng"]),
                    matrix[i][j],
                )

    if on_progress:
        on_progress("3/4 TMAP 이동시간 계산 완료")
    return matrix
