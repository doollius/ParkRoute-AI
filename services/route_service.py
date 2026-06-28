from __future__ import annotations

from typing import Any

from constants.config import MAX_GRAPH_NODES
from optimizer.graph_builder import build_cost_matrix, cluster_by_walk
from optimizer.ortools_solver import solve_route_order
from optimizer.scoring import build_route_summary, choose_segment_mode
from services.explanation_service import generate_explanation
from services.map_service import build_travel_matrix
from services.parking_service import assign_parking_to_clusters


class RouteOptimizationError(Exception):
    pass


def _place_name(place: dict[str, Any]) -> str:
    return place.get("normalized_address") or place.get("raw_input") or "장소"


def optimize_route(
    places: list[dict[str, Any]],
    start_place_id: str,
    end_place_id: str,
    travel_region: str,
    optimization_mode: str = "minimize_walk",
) -> dict[str, Any]:
    nodes = [p for p in places if p.get("lat") is not None and p.get("lng") is not None]
    if len(nodes) > MAX_GRAPH_NODES:
        raise RouteOptimizationError(f"장소는 최대 {MAX_GRAPH_NODES}개까지 지원합니다.")

    id_to_index = {p["id"]: i for i, p in enumerate(nodes)}
    if start_place_id not in id_to_index or end_place_id not in id_to_index:
        raise RouteOptimizationError("출발지 또는 도착지 좌표가 없습니다.")

    start_idx = id_to_index[start_place_id]
    end_idx = id_to_index[end_place_id]

    travel_matrix = build_travel_matrix(nodes)
    minimize_walk = optimization_mode != "minimize_time"
    cost_matrix = build_cost_matrix(travel_matrix, minimize_walk)

    order = solve_route_order(cost_matrix, start_idx, end_idx)
    if not order:
        raise RouteOptimizationError("조건을 만족하는 경로를 찾을 수 없습니다.")

    clusters = cluster_by_walk(travel_matrix)
    parkings = assign_parking_to_clusters(nodes, clusters, travel_region)

    segments: list[dict[str, Any]] = []
    stops: list[dict[str, Any]] = []
    visit_num = 0

    for pos, node_idx in enumerate(order):
        node = nodes[node_idx]
        is_start = node_idx == start_idx and pos == 0
        is_end = node_idx == end_idx and pos == len(order) - 1

        if is_start:
            label = "S"
        elif is_end:
            label = "E"
        else:
            visit_num += 1
            label = str(visit_num)

        stops.append(
            {
                "id": node["id"],
                "label": label,
                "name": _place_name(node),
                "type": node.get("type"),
                "lat": node["lat"],
                "lng": node["lng"],
                "reservation_time": node.get("reservation_time"),
            }
        )

        if pos == 0:
            continue

        prev_idx = order[pos - 1]
        travel = travel_matrix[prev_idx][node_idx]
        mode = choose_segment_mode(travel)
        time_sec = int(travel["walk_time_sec"] if mode == "walk" else travel["car_time_sec"])
        dist = travel.get("walk_distance_m") if mode == "walk" else travel.get("car_distance_m")

        segments.append(
            {
                "from_id": nodes[prev_idx]["id"],
                "to_id": node["id"],
                "mode": mode,
                "time_sec": time_sec,
                "distance_m": dist or 0,
            }
        )

    summary = build_route_summary(segments, len(parkings))
    route: dict[str, Any] = {
        "order": [nodes[i]["id"] for i in order],
        "stops": stops,
        "segments": segments,
        "parkings": [
            {
                "label": f"P{i + 1}",
                "name": p["name"],
                "address": p.get("address", ""),
                "lat": p["lat"],
                "lng": p["lng"],
                "distance_m": p.get("distance_m"),
                "place_ids": p.get("place_ids", []),
            }
            for i, p in enumerate(parkings)
        ],
        "summary": summary,
        "message": "최적 경로가 생성되었습니다.",
    }
    route["explanation"] = generate_explanation(route)
    return route
