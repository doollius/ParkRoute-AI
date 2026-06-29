from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from constants.config import PARKING_SCORE_FEE_WEIGHT, PARKING_TRANSITION_PENALTY
from optimizer.graph_builder import cluster_by_walk, edge_cost
from optimizer.multimodal_cost import compare_cluster_routing
from services.map_service import get_travel_times
from services.parking_service import get_parking_candidates, select_parking_for_cluster
from utils.parking_cost import parse_fee
from utils.parking_event import parking_event_seconds


@dataclass
class ClusterPlan:
    clusters: list[list[int]]
    node_to_cluster: dict[int, int]
    cluster_parking: dict[int, dict[str, Any]] = field(default_factory=dict)
    cluster_use_parking: dict[int, bool] = field(default_factory=dict)
    cluster_routing: dict[int, dict[str, Any]] = field(default_factory=dict)


def build_cluster_plan(
    nodes: list[dict[str, Any]],
    travel_matrix: list[list[dict[str, Any]]],
    travel_region: str,
    congestion_level: str = "normal",
) -> ClusterPlan:
    clusters = cluster_by_walk(travel_matrix)
    node_to_cluster: dict[int, int] = {}
    for cluster_id, indices in enumerate(clusters):
        for idx in indices:
            node_to_cluster[idx] = cluster_id

    candidates = get_parking_candidates(nodes, travel_region)
    used_ids: set[str] = set()
    cluster_parking: dict[int, dict[str, Any]] = {}
    cluster_use_parking: dict[int, bool] = {}
    cluster_routing: dict[int, dict[str, Any]] = {}

    for cluster_id, indices in enumerate(clusters):
        if len(indices) < 2:
            cluster_use_parking[cluster_id] = False
            continue

        parking = select_parking_for_cluster(
            indices,
            nodes,
            candidates,
            used_ids,
            get_travel_times,
        )
        comparison = compare_cluster_routing(
            indices,
            parking,
            nodes,
            travel_matrix,
            get_travel_times,
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


def _parking_event_cost_for_node(
    node_idx: int,
    nodes: list[dict[str, Any]],
    congestion_level: str,
) -> int:
    return parking_event_seconds(nodes[node_idx], congestion_level)


def _inter_cluster_car_sec(
    from_idx: int,
    to_idx: int,
    nodes: list[dict[str, Any]],
    cluster_plan: ClusterPlan,
) -> int:
    ci = cluster_plan.node_to_cluster.get(from_idx)
    cj = cluster_plan.node_to_cluster.get(to_idx)
    pi = cluster_plan.cluster_parking.get(ci) if ci is not None else None
    pj = cluster_plan.cluster_parking.get(cj) if cj is not None else None

    use_pi = cluster_plan.cluster_use_parking.get(ci, False) if ci is not None else False
    use_pj = cluster_plan.cluster_use_parking.get(cj, False) if cj is not None else False

    if use_pi and use_pj and pi and pj:
        leg = get_travel_times(pi["lat"], pi["lng"], pj["lat"], pj["lng"])
        return int(leg.get("car_time_sec") or 0)

    a, b = nodes[from_idx], nodes[to_idx]
    leg = get_travel_times(a["lat"], a["lng"], b["lat"], b["lng"])
    return int(leg.get("car_time_sec") or 0)


def build_cluster_aware_cost_matrix(
    travel_matrix: list[list[dict[str, Any]]],
    cluster_plan: ClusterPlan,
    nodes: list[dict[str, Any]],
    minimize_walk: bool,
    congestion_level: str = "normal",
) -> list[list[int]]:
    """Place-node cost matrix — 주차 거점 vs 직행 비교 결과 반영."""
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
                    cost = edge_cost(leg, minimize_walk)
                    if i != j:
                        cost += _parking_event_cost_for_node(j, nodes, congestion_level) // max(
                            1, len(cluster_plan.clusters[ci]) - 1
                        )
                    matrix[i][j] = cost
                else:
                    matrix[i][j] = edge_cost(travel_matrix[i][j], minimize_walk)
                continue

            car_sec = _inter_cluster_car_sec(i, j, nodes, cluster_plan)
            cost = _car_edge_cost(car_sec, minimize_walk) + PARKING_TRANSITION_PENALTY

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
    return cluster_plan.cluster_use_parking.get(cluster_id, False)
