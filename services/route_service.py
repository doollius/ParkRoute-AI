from __future__ import annotations

from typing import Any

from constants.config import MAX_GRAPH_NODES
from optimizer.constraint_builder import map_rules_to_indices
from optimizer.graph_builder import build_cost_matrix
from optimizer.ortools_solver import solve_route_order
from optimizer.route_reconstruction import build_parking_aware_route
from optimizer.scoring import build_route_summary
from services.explanation_service import generate_explanation
from services.map_service import build_travel_matrix
from utils.time_utils import check_reservation_feasible, hhmm_to_minutes


class RouteOptimizationError(Exception):
    pass


def optimize_route(
    places: list[dict[str, Any]],
    start_place_id: str,
    end_place_id: str,
    travel_region: str,
    optimization_mode: str = "minimize_walk",
    visit_rules: list[dict[str, Any]] | None = None,
    trip_start_time: str = "09:00",
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

    trip_start_minutes = hhmm_to_minutes(trip_start_time) or 9 * 60
    reservation_by_index: dict[int, int] = {}
    for i, node in enumerate(nodes):
        res = node.get("reservation_time")
        if res:
            res_min = hhmm_to_minutes(res)
            if res_min is not None:
                reservation_by_index[i] = res_min

    mapped_rules = map_rules_to_indices(visit_rules or [], id_to_index)

    order = solve_route_order(
        cost_matrix,
        start_idx,
        end_idx,
        mapped_rules=mapped_rules,
        travel_matrix=travel_matrix,
        reservation_by_index=reservation_by_index or None,
        trip_start_minutes=trip_start_minutes,
    )
    if not order:
        raise RouteOptimizationError("조건을 만족하는 경로를 찾을 수 없습니다.")

    res_errors = check_reservation_feasible(order, nodes, travel_matrix, trip_start_minutes)
    if res_errors:
        raise RouteOptimizationError("\n".join(res_errors))

    stops, segments, parkings = build_parking_aware_route(
        order,
        nodes,
        travel_matrix,
        start_idx,
        end_idx,
        travel_region,
        trip_start_minutes,
    )

    summary = build_route_summary(segments, len(parkings))
    route: dict[str, Any] = {
        "order": [nodes[i]["id"] for i in order],
        "stops": stops,
        "segments": segments,
        "parkings": [
            {
                "label": p.get("label", f"P{i + 1}"),
                "name": p["name"],
                "address": p.get("address", ""),
                "lat": p["lat"],
                "lng": p["lng"],
                "place_ids": p.get("place_ids", []),
                "base_fee": p.get("base_fee"),
            }
            for i, p in enumerate(parkings)
        ],
        "summary": summary,
        "message": "최적 경로가 생성되었습니다.",
        "trip_start_time": trip_start_time,
        "visit_rules_applied": len(mapped_rules),
    }
    route["explanation"] = generate_explanation(route)
    return route
