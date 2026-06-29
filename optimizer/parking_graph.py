from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from constants.config import (
    PARKING_COUNT_MODE_PENALTY,
    PARKING_SCORE_FEE_WEIGHT,
    PARKING_TRANSITION_PENALTY,
)
from optimizer.graph_builder import cluster_by_walk, edge_cost
from optimizer.multimodal_cost import compare_cluster_routing, hub_loop_cost_seconds
from services.map_service import get_travel_times
from services.parking_service import get_parking_candidates, score_parking, select_parking_for_cluster
from utils.optimization_mode import MODE_MINIMIZE_PARKING, normalize_optimization_mode
from utils.parking_cost import parse_fee
from utils.parking_event import parking_event_seconds


@dataclass
class ClusterPlan:
    clusters: list[list[int]]
    node_to_cluster: dict[int, int]
    cluster_parking: dict[int, dict[str, Any]] = field(default_factory=dict)
    cluster_use_parking: dict[int, bool] = field(default_factory=dict)
    cluster_routing: dict[int, dict[str, Any]] = field(default_factory=dict)


def _indices_within_walk_of_parking(
    parking: dict[str, Any],
    nodes: list[dict[str, Any]],
    get_leg,
) -> list[int]:
    indices: list[int] = []
    plat, plng = parking["lat"], parking["lng"]
    for i, node in enumerate(nodes):
        leg = get_leg(plat, plng, node["lat"], node["lng"])
        if leg.get("walk_allowed"):
            indices.append(i)
    return indices


def _build_parking_first_clusters(
    nodes: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    get_leg,
) -> tuple[list[list[int]], dict[int, dict[str, Any]], set[str]]:
    """
    주차 횟수 최소화: 공영주차장 기준 도보 9분 이내 POI 2개 이상이면 클러스터.
    겹치면 가장 많은 POI를 포함하는 주차장을 우선 선택.
    """
    covers: list[tuple[float, int, dict[str, Any], list[int]]] = []
    for parking in candidates:
        indices = _indices_within_walk_of_parking(parking, nodes, get_leg)
        if len(indices) >= 2:
            center_lat = sum(nodes[i]["lat"] for i in indices) / len(indices)
            center_lng = sum(nodes[i]["lng"] for i in indices) / len(indices)
            score = score_parking(parking, center_lat, center_lng)
            covers.append((score, len(indices), parking, indices))

    covers.sort(key=lambda row: (-row[1], row[0]))

    assigned: set[int] = set()
    clusters: list[list[int]] = []
    cluster_parking: dict[int, dict[str, Any]] = {}
    used_ids: set[str] = set()

    for _, _count, parking, indices in covers:
        uncovered = [i for i in indices if i not in assigned]
        if len(uncovered) < 2:
            continue
        if parking["id"] in used_ids:
            continue

        cluster_id = len(clusters)
        clusters.append(sorted(uncovered))
        cluster_parking[cluster_id] = {
            **parking,
            "place_ids": [nodes[i]["id"] for i in uncovered],
        }
        assigned.update(uncovered)
        used_ids.add(parking["id"])

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
) -> ClusterPlan:
    mode = normalize_optimization_mode(optimization_mode)
    candidates = get_parking_candidates(nodes, travel_region)

    if mode == MODE_MINIMIZE_PARKING:
        clusters, pre_parking, _used = _build_parking_first_clusters(
            nodes, candidates, get_travel_times
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
                get_travel_times,
                congestion_level,
            )
            cluster_routing[cluster_id] = {
                "use_parking": hub is not None,
                "direct_cost_sec": None,
                "hub_cost_sec": hub,
                "savings_sec": 0,
                "policy": "parking_first",
            }
            if hub is not None:
                cluster_parking[cluster_id] = parking
                cluster_use_parking[cluster_id] = True
                used_ids.add(parking["id"])
            else:
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
    optimization_mode: str = "minimize_walk",
    congestion_level: str = "normal",
) -> list[list[int]]:
    """Place-node cost matrix — 모드별 가중치 반영."""
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
                        walk = leg.get("walk_time_sec")
                        if leg.get("walk_allowed") and walk is not None:
                            cost = int(walk)
                        else:
                            cost = edge_cost(leg, minimize_walk=False)
                    else:
                        cost = edge_cost(leg, minimize_walk)
                    if i != j:
                        cost += _parking_event_cost_for_node(j, nodes, congestion_level) // max(
                            1, len(cluster_plan.clusters[ci]) - 1
                        )
                    matrix[i][j] = cost
                else:
                    matrix[i][j] = edge_cost(
                        travel_matrix[i][j],
                        minimize_walk if not minimize_parking else False,
                    )
                continue

            car_sec = _inter_cluster_car_sec(i, j, nodes, cluster_plan)
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
