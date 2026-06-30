from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

from constants.config import (
    FORBIDDEN_EDGE_COST,
    PARKING_COUNT_MODE_PENALTY,
    PARKING_SCORE_FEE_WEIGHT,
    PARKING_TRANSITION_PENALTY,
    PARKING_WALK_MAX_DISTANCE_M,
)
from optimizer.graph_builder import cluster_by_walk, edge_cost
from optimizer.multimodal_cost import compare_cluster_routing, hub_loop_cost_seconds
from services.map_service import get_travel_times
from services.parking_service import (
    ParkingCoverage,
    get_parking_coverage,
    pick_hub_for_cluster,
    score_parking,
    select_parking_for_cluster,
    hub_cluster_attempt_limit,
)
from utils.optimization_mode import MODE_MINIMIZE_PARKING, normalize_optimization_mode
from utils.geo import estimate_travel_sec
from utils.parking_cost import parse_fee
from utils.walk_limits import walk_sec_for_leg


@dataclass
class ClusterPlan:
    clusters: list[list[int]]
    node_to_cluster: dict[int, int]
    cluster_parking: dict[int, dict[str, Any]] = field(default_factory=dict)
    cluster_use_parking: dict[int, bool] = field(default_factory=dict)
    cluster_routing: dict[int, dict[str, Any]] = field(default_factory=dict)


def _build_parking_first_clusters(
    nodes: list[dict[str, Any]],
    coverage: ParkingCoverage,
    get_leg: Callable[..., dict[str, Any]],
    on_progress: Callable[[str], None] | None = None,
) -> tuple[list[list[int]], dict[int, dict[str, Any]], set[str]]:
    """
    POI별 카카오 겹침 인덱스로 클러스터 구성.
    1) 여러 POI 목록에 공통 등장하는 주차장으로 그룹 후보 생성
    2) 그룹마다 겹치는 hub 상위 N개 중 직선 거리 조건으로 1곳 확정
    """
    by_id = coverage.get("by_id", {})
    covers: list[tuple[float, int, dict[str, Any], list[int]]] = []

    for entry in by_id.values():
        indices = sorted(entry["poi_indices"])
        if len(indices) < 2:
            continue
        parking = entry["parking"]
        center_lat = sum(nodes[i]["lat"] for i in indices) / len(indices)
        center_lng = sum(nodes[i]["lng"] for i in indices) / len(indices)
        score = score_parking(parking, center_lat, center_lng)
        covers.append((score, len(indices), parking, indices))

    covers.sort(key=lambda row: (-row[1], row[0]))

    assigned: set[int] = set()
    clusters: list[list[int]] = []
    cluster_parking: dict[int, dict[str, Any]] = {}
    used_ids: set[str] = set()
    hub_attempt_limit = hub_cluster_attempt_limit(len(nodes))
    hub_attempts = 0

    for _, _count, _parking, indices in covers:
        uncovered = [i for i in indices if i not in assigned]
        if len(uncovered) < 2:
            continue

        if hub_attempts < hub_attempt_limit and on_progress:
            hub_attempts += 1
            on_progress(
                f"2/4 겹치는 주차장 hub 선정 ({hub_attempts}/{hub_attempt_limit})…"
            )

        chosen = pick_hub_for_cluster(
            uncovered,
            nodes,
            coverage,
            used_ids,
            get_leg,
            parking_mode=True,
        )
        if not chosen:
            continue

        cluster_id = len(clusters)
        clusters.append(sorted(uncovered))
        cluster_parking[cluster_id] = chosen
        assigned.update(uncovered)

    for i in range(len(nodes)):
        if i not in assigned:
            clusters.append([i])

    return clusters, cluster_parking, used_ids


def build_cluster_plan(
    nodes: list[dict[str, Any]],
    travel_matrix: list[list[dict[str, Any]]],
    travel_region: str,
    congestion_level: str = "normal",
    optimization_mode: str = "minimize_walk",
    on_progress: Callable[[str], None] | None = None,
    get_leg: Callable[..., dict[str, Any]] | None = None,
) -> ClusterPlan:
    mode = normalize_optimization_mode(optimization_mode)
    del travel_region  # POI별 카카오 검색 — 지역 문자열 미사용
    leg_fn = get_leg or get_travel_times

    coverage = get_parking_coverage(nodes, on_progress=on_progress)
    candidates = coverage["union"]
    overlap_groups = sum(
        1 for e in coverage.get("by_id", {}).values() if len(e["poi_indices"]) >= 2
    )
    if on_progress:
        on_progress(
            f"2/4 주차장 {len(candidates)}곳(POI별 합집합) · "
            f"2곳 이상 POI 겹침 {overlap_groups}건"
        )

    if mode == MODE_MINIMIZE_PARKING:
        clusters, pre_parking, _used = _build_parking_first_clusters(
            nodes, coverage, leg_fn, on_progress=on_progress
        )
    else:
        clusters = cluster_by_walk(travel_matrix)
        pre_parking = {}

    node_to_cluster: dict[int, int] = {}
    for cluster_id, indices in enumerate(clusters):
        for idx in indices:
            node_to_cluster[idx] = cluster_id

    used_ids: set[str] = set()
    cluster_parking: dict[int, dict[str, Any]] = {}
    cluster_use_parking: dict[int, bool] = {}
    cluster_routing: dict[int, dict[str, Any]] = {}

    for cluster_id, indices in enumerate(clusters):
        if len(indices) < 2:
            cluster_use_parking[cluster_id] = False
            continue

        if mode == MODE_MINIMIZE_PARKING:
            parking = pre_parking.get(cluster_id)
            if not parking:
                cluster_use_parking[cluster_id] = False
                continue

            hub = hub_loop_cost_seconds(
                indices,
                parking,
                nodes,
                travel_matrix,
                leg_fn,
                congestion_level,
                parking_mode=True,
                max_walk_m=PARKING_WALK_MAX_DISTANCE_M,
            )
            cluster_parking[cluster_id] = parking
            cluster_use_parking[cluster_id] = True
            used_ids.add(parking["id"])
            cluster_routing[cluster_id] = {
                "use_parking": True,
                "direct_cost_sec": None,
                "hub_cost_sec": hub,
                "savings_sec": 0,
                "policy": "parking_first",
            }
            continue

        parking = select_parking_for_cluster(
            indices,
            nodes,
            candidates,
            used_ids,
            leg_fn,
            coverage=coverage,
        )
        comparison = compare_cluster_routing(
            indices,
            parking,
            nodes,
            travel_matrix,
            leg_fn,
            congestion_level,
        )
        cluster_routing[cluster_id] = comparison

        if comparison.get("use_parking") and parking:
            cluster_parking[cluster_id] = parking
            cluster_use_parking[cluster_id] = True
        else:
            cluster_use_parking[cluster_id] = False
            if parking and parking["id"] in used_ids:
                used_ids.discard(parking["id"])

    return ClusterPlan(
        clusters=clusters,
        node_to_cluster=node_to_cluster,
        cluster_parking=cluster_parking,
        cluster_use_parking=cluster_use_parking,
        cluster_routing=cluster_routing,
    )


def _car_edge_cost(car_time_sec: int, minimize_walk: bool) -> int:
    travel = {
        "car_time_sec": car_time_sec,
        "walk_time_sec": None,
        "walk_allowed": False,
    }
    return edge_cost(travel, minimize_walk)


def _inter_cluster_car_sec(
    from_idx: int,
    to_idx: int,
    nodes: list[dict[str, Any]],
    cluster_plan: ClusterPlan,
    travel_matrix: list[list[dict[str, Any]]],
) -> int:
    ci = cluster_plan.node_to_cluster.get(from_idx)
    cj = cluster_plan.node_to_cluster.get(to_idx)
    pi = cluster_plan.cluster_parking.get(ci) if ci is not None else None
    pj = cluster_plan.cluster_parking.get(cj) if cj is not None else None

    use_pi = cluster_plan.cluster_use_parking.get(ci, False) if ci is not None else False
    use_pj = cluster_plan.cluster_use_parking.get(cj, False) if cj is not None else False

    if use_pi and use_pj and pi and pj:
        est = estimate_travel_sec(pi["lat"], pi["lng"], pj["lat"], pj["lng"], "car")
        return int(est["time_sec"])

    return int(travel_matrix[from_idx][to_idx].get("car_time_sec") or 0)


def build_cluster_aware_cost_matrix(
    travel_matrix: list[list[dict[str, Any]]],
    cluster_plan: ClusterPlan,
    nodes: list[dict[str, Any]],
    optimization_mode: str = "minimize_walk",
    congestion_level: str = "normal",
) -> list[list[int]]:
    """Place-node cost matrix — 모드별 가중치 반영."""
    del congestion_level
    mode = normalize_optimization_mode(optimization_mode)
    minimize_walk = mode == "minimize_walk"
    minimize_parking = mode == MODE_MINIMIZE_PARKING
    transition_penalty = (
        PARKING_COUNT_MODE_PENALTY if minimize_parking else PARKING_TRANSITION_PENALTY
    )

    n = len(travel_matrix)
    matrix: list[list[int]] = [[0] * n for _ in range(n)]

    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            ci = cluster_plan.node_to_cluster.get(i)
            cj = cluster_plan.node_to_cluster.get(j)

            if ci is not None and ci == cj:
                use_parking = cluster_plan.cluster_use_parking.get(ci, False)
                if use_parking and len(cluster_plan.clusters[ci]) >= 2:
                    leg = travel_matrix[i][j]
                    if minimize_parking:
                        walk = walk_sec_for_leg(
                            leg,
                            parking_mode=True,
                            max_walk_m=PARKING_WALK_MAX_DISTANCE_M,
                        )
                        if i != j:
                            matrix[i][j] = (
                                walk if walk is not None else FORBIDDEN_EDGE_COST
                            )
                        else:
                            matrix[i][j] = 0
                    else:
                        matrix[i][j] = (
                            edge_cost(leg, minimize_walk) if i != j else 0
                        )
                else:
                    matrix[i][j] = edge_cost(
                        travel_matrix[i][j],
                        minimize_walk if not minimize_parking else False,
                    )
                continue

            car_sec = _inter_cluster_car_sec(i, j, nodes, cluster_plan, travel_matrix)
            cost = _car_edge_cost(car_sec, minimize_walk) + transition_penalty

            parking_i = cluster_plan.cluster_parking.get(ci) if ci is not None else None
            if parking_i and cluster_plan.cluster_use_parking.get(ci, False):
                fee = parse_fee(parking_i.get("base_fee")) or 0
                cost += int(fee * PARKING_SCORE_FEE_WEIGHT)

            matrix[i][j] = cost

    return matrix


def parking_for_leg_indices(
    leg_indices: list[int],
    cluster_plan: ClusterPlan,
) -> dict[str, Any] | None:
    if len(leg_indices) < 2:
        return None
    cluster_id = cluster_plan.node_to_cluster.get(leg_indices[0])
    if cluster_id is None:
        return None
    if not cluster_plan.cluster_use_parking.get(cluster_id, False):
        return None
    return cluster_plan.cluster_parking.get(cluster_id)


def cluster_uses_parking(cluster_plan: ClusterPlan, leg_indices: list[int]) -> bool:
    if len(leg_indices) < 2:
        return False
    cluster_id = cluster_plan.node_to_cluster.get(leg_indices[0])
    if cluster_id is None:
        return False
    if not all(cluster_plan.node_to_cluster.get(i) == cluster_id for i in leg_indices):
        return False
    return cluster_plan.cluster_use_parking.get(cluster_id, False)
