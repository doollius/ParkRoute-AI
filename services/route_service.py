from __future__ import annotations

from typing import Any, Callable

from constants.config import MAX_GRAPH_NODES, WALK_TIME_FALLBACK_MINUTES, WALK_TIME_LIMIT_MINUTES
from models.visit_rule import RULE_IMMEDIATE
from optimizer.constraint_builder import map_rules_to_indices
from optimizer.fallback_solver import greedy_route_order
from optimizer.parking_graph import build_cluster_aware_cost_matrix, build_cluster_plan
from optimizer.ortools_solver import solve_route_order
from optimizer.route_reconstruction import _split_order_into_legs, build_parking_aware_route
from optimizer.scoring import build_route_summary
from services.explanation_service import generate_explanation
from services.map_service import apply_walk_limit, build_travel_matrix
from utils.time_utils import check_reservation_feasible, hhmm_to_minutes


class RouteOptimizationError(Exception):
    pass


def _immediate_rules_only(mapped_rules: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [r for r in mapped_rules if r.get("rule_type") == RULE_IMMEDIATE]


def _solve_order(
    cost_matrix: list[list[int]],
    start_idx: int,
    end_idx: int,
    travel_matrix: list[list[dict[str, Any]]],
    mapped_rules: list[dict[str, Any]],
    reservation_by_index: dict[int, int] | None,
    trip_start_minutes: int,
) -> list[int] | None:
    return solve_route_order(
        cost_matrix,
        start_idx,
        end_idx,
        mapped_rules=mapped_rules or None,
        travel_matrix=travel_matrix,
        reservation_by_index=reservation_by_index or None,
        trip_start_minutes=trip_start_minutes,
    )


def _parking_warnings(
    order: list[int],
    travel_matrix: list[list[dict[str, Any]]],
    parkings: list[dict[str, Any]],
) -> list[str]:
    legs = _split_order_into_legs(order, travel_matrix)
    walk_legs = [leg for leg in legs if len(leg) >= 2]
    if not walk_legs:
        return []
    if not parkings:
        return ["근처 공영주차장을 찾지 못해 주차 없이 경로를 표시합니다. (ER-008)"]
    if len(parkings) < len(walk_legs):
        missing = len(walk_legs) - len(parkings)
        return [f"도보 그룹 {missing}곳에서 주차장을 찾지 못했습니다. 해당 구간은 차량·도보로 연결합니다."]
    return []


def optimize_route(
    places: list[dict[str, Any]],
    start_place_id: str,
    end_place_id: str,
    travel_region: str,
    optimization_mode: str = "minimize_walk",
    visit_rules: list[dict[str, Any]] | None = None,
    trip_start_time: str = "09:00",
    on_progress: Callable[[str], None] | None = None,
    input_warnings: list[str] | None = None,
    excluded_places: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    def progress(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    warnings: list[str] = list(input_warnings or [])
    nodes = [p for p in places if p.get("lat") is not None and p.get("lng") is not None]
    if len(nodes) > MAX_GRAPH_NODES:
        raise RouteOptimizationError(f"장소는 최대 {MAX_GRAPH_NODES}개까지 지원합니다.")

    id_to_index = {p["id"]: i for i, p in enumerate(nodes)}
    if start_place_id not in id_to_index or end_place_id not in id_to_index:
        raise RouteOptimizationError("출발지 또는 도착지 좌표가 없습니다.")

    start_idx = id_to_index[start_place_id]
    end_idx = id_to_index[end_place_id]
    minimize_walk = optimization_mode != "minimize_time"

    progress("이동시간 계산 중...")
    travel_matrix = build_travel_matrix(nodes, on_progress=on_progress)
    estimated_legs = sum(
        1
        for row in travel_matrix
        for leg in row
        if leg.get("estimated") and int(leg.get("car_time_sec") or 0) > 0
    )
    if estimated_legs:
        warnings.append(
            f"TMAP API 오류로 {estimated_legs}개 구간을 직선 거리 기반으로 추정했습니다. (ER-009)"
        )

    progress("주차장 탐색 중...")
    cluster_plan = build_cluster_plan(nodes, travel_matrix, travel_region)
    cost_matrix = build_cluster_aware_cost_matrix(
        travel_matrix, cluster_plan, nodes, minimize_walk
    )

    trip_start_minutes = hhmm_to_minutes(trip_start_time) or 9 * 60
    reservation_by_index: dict[int, int] = {}
    for i, node in enumerate(nodes):
        res = node.get("reservation_time")
        if res:
            res_min = hhmm_to_minutes(res)
            if res_min is not None:
                reservation_by_index[i] = res_min

    mapped_rules = map_rules_to_indices(visit_rules or [], id_to_index)

    progress("OR-Tools 실행 중...")
    order = _solve_order(
        cost_matrix,
        start_idx,
        end_idx,
        travel_matrix,
        mapped_rules,
        reservation_by_index or None,
        trip_start_minutes,
    )

    if not order:
        relaxed_matrix = apply_walk_limit(travel_matrix, WALK_TIME_FALLBACK_MINUTES)
        relaxed_plan = build_cluster_plan(nodes, relaxed_matrix, travel_region)
        relaxed_cost = build_cluster_aware_cost_matrix(
            relaxed_matrix, relaxed_plan, nodes, minimize_walk
        )
        order = _solve_order(
            relaxed_cost,
            start_idx,
            end_idx,
            relaxed_matrix,
            mapped_rules,
            reservation_by_index or None,
            trip_start_minutes,
        )
        if order:
            travel_matrix = relaxed_matrix
            cluster_plan = relaxed_plan
            cost_matrix = relaxed_cost
            warnings.append(
                f"도보 {WALK_TIME_LIMIT_MINUTES}분 제한으로 경로를 찾지 못해 "
                f"{WALK_TIME_FALLBACK_MINUTES}분으로 완화했습니다. (ER-006)"
            )

    if not order and len(mapped_rules) > len(_immediate_rules_only(mapped_rules)):
        immediate_only = _immediate_rules_only(mapped_rules)
        order = _solve_order(
            cost_matrix,
            start_idx,
            end_idx,
            travel_matrix,
            immediate_only,
            reservation_by_index or None,
            trip_start_minutes,
        )
        if order:
            mapped_rules = immediate_only
            warnings.append(
                "「다음(순서만)」 방문 규칙을 완화하고 「바로 다음」 규칙만 적용했습니다. (ER-006)"
            )

    if not order:
        order = greedy_route_order(cost_matrix, start_idx, end_idx, mapped_rules)
        if order:
            warnings.append(
                "OR-Tools 최적화에 실패해 가까운 순서(휴리스틱) 경로를 사용했습니다. (ER-007)"
            )

    if not order:
        raise RouteOptimizationError(
            "조건을 만족하는 경로를 찾을 수 없습니다. "
            "방문 규칙·예약 시간·장소 간 거리를 확인해 주세요. (ER-006)"
        )

    res_errors = check_reservation_feasible(order, nodes, travel_matrix, trip_start_minutes)
    if res_errors:
        raise RouteOptimizationError("\n".join(res_errors))

    progress("경로 재구성 중...")
    stops, segments, parkings = build_parking_aware_route(
        order,
        nodes,
        travel_matrix,
        start_idx,
        end_idx,
        travel_region,
        trip_start_minutes,
        cluster_plan=cluster_plan,
    )

    warnings.extend(_parking_warnings(order, travel_matrix, parkings))

    summary = build_route_summary(segments, parkings)
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
                "unit_fee": p.get("unit_fee"),
                "stay_minutes": p.get("stay_minutes"),
                "estimated_cost": p.get("estimated_cost"),
                "cost_detail": p.get("cost_detail"),
            }
            for i, p in enumerate(parkings)
        ],
        "summary": summary,
        "warnings": warnings,
        "excluded_places": [
            {
                "id": p.get("id"),
                "raw_input": p.get("raw_input"),
                "geocode_error": p.get("geocode_error"),
            }
            for p in (excluded_places or [])
        ],
        "message": "최적 경로가 생성되었습니다.",
        "trip_start_time": trip_start_time,
        "visit_rules_applied": len(mapped_rules),
    }
    if warnings:
        route["message"] = "조건을 일부 완화하여 경로를 생성했습니다."
    route["explanation"] = generate_explanation(route)
    return route
