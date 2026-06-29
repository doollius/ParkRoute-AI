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
from services.map_service import apply_walk_limit, build_travel_matrix
from utils.optimization_mode import MODE_MINIMIZE_PARKING, normalize_optimization_mode
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


def _solve_order_flexible(
    cost_matrix: list[list[int]],
    start_idx: int | None,
    end_idx: int | None,
    travel_matrix: list[list[dict[str, Any]]],
    mapped_rules: list[dict[str, Any]],
    reservation_by_index: dict[int, int] | None,
    trip_start_minutes: int,
) -> tuple[list[int] | None, int | None, int | None]:
    n = len(cost_matrix)
    if n <= 1:
        idx = 0
        return [idx], start_idx if start_idx is not None else idx, end_idx if end_idx is not None else idx

    def route_cost(order: list[int]) -> int:
        return sum(int(cost_matrix[order[i]][order[i + 1]]) for i in range(len(order) - 1))

    if start_idx is not None and end_idx is not None:
        order = _solve_order(
            cost_matrix,
            start_idx,
            end_idx,
            travel_matrix,
            mapped_rules,
            reservation_by_index,
            trip_start_minutes,
        )
        return order, start_idx, end_idx

    candidates: list[tuple[int, int]] = []
    if start_idx is not None and end_idx is None:
        candidates = [(start_idx, e) for e in range(n) if e != start_idx]
    elif start_idx is None and end_idx is not None:
        candidates = [(s, end_idx) for s in range(n) if s != end_idx]
    else:
        candidates = [(s, e) for s in range(n) for e in range(n) if s != e]

    best_order: list[int] | None = None
    best_pair: tuple[int, int] | None = None
    best_cost = float("inf")
    for s, e in candidates:
        order = _solve_order(
            cost_matrix,
            s,
            e,
            travel_matrix,
            mapped_rules,
            reservation_by_index,
            trip_start_minutes,
        )
        if not order:
            continue
        cost = route_cost(order)
        if cost < best_cost:
            best_cost = cost
            best_order = order
            best_pair = (s, e)

    if best_order and best_pair:
        resolved_start = start_idx if start_idx is not None else best_pair[0]
        resolved_end = end_idx if end_idx is not None else best_pair[1]
        return best_order, resolved_start, resolved_end
    return None, start_idx, end_idx


def _greedy_order_flexible(
    cost_matrix: list[list[int]],
    start_idx: int | None,
    end_idx: int | None,
    mapped_rules: list[dict[str, Any]] | None,
) -> tuple[list[int] | None, int | None, int | None]:
    n = len(cost_matrix)
    if n <= 1:
        idx = 0
        return [idx], start_idx if start_idx is not None else idx, end_idx if end_idx is not None else idx

    def route_cost(order: list[int]) -> int:
        return sum(int(cost_matrix[order[i]][order[i + 1]]) for i in range(len(order) - 1))

    if start_idx is not None and end_idx is not None:
        order = greedy_route_order(cost_matrix, start_idx, end_idx, mapped_rules)
        return order, start_idx, end_idx

    candidates: list[tuple[int, int]] = []
    if start_idx is not None and end_idx is None:
        candidates = [(start_idx, e) for e in range(n) if e != start_idx]
    elif start_idx is None and end_idx is not None:
        candidates = [(s, end_idx) for s in range(n) if s != end_idx]
    else:
        candidates = [(s, e) for s in range(n) for e in range(n) if s != e]

    best_order: list[int] | None = None
    best_pair: tuple[int, int] | None = None
    best_cost = float("inf")
    for s, e in candidates:
        order = greedy_route_order(cost_matrix, s, e, mapped_rules)
        if not order:
            continue
        cost = route_cost(order)
        if cost < best_cost:
            best_cost = cost
            best_order = order
            best_pair = (s, e)

    if best_order and best_pair:
        resolved_start = start_idx if start_idx is not None else best_pair[0]
        resolved_end = end_idx if end_idx is not None else best_pair[1]
        return best_order, resolved_start, resolved_end
    return None, start_idx, end_idx


def optimize_route(
    nodes: list[dict[str, Any]],
    start_idx: int | None,
    end_idx: int | None,
    travel_region: str,
    optimization_mode: str = "minimize_walk",
    visit_rules: list[dict[str, Any]] | None = None,
    trip_start_time: str = "09:00",
    on_progress: Callable[[str], None] | None = None,
    input_warnings: list[str] | None = None,
    excluded_places: list[dict[str, Any]] | None = None,
    congestion_level: str = "normal",
) -> dict[str, Any]:
    def progress(msg: str) -> None:
        if on_progress:
            on_progress(msg)

    warnings: list[str] = list(input_warnings or [])
    if len(nodes) > MAX_GRAPH_NODES:
        raise RouteOptimizationError(f"장소는 최대 {MAX_GRAPH_NODES}개까지 지원합니다.")

    id_to_index = {p["id"]: i for i, p in enumerate(nodes)}
    if start_idx is not None and (start_idx < 0 or start_idx >= len(nodes)):
        raise RouteOptimizationError("출발지 좌표가 없습니다.")
    if end_idx is not None and (end_idx < 0 or end_idx >= len(nodes)):
        raise RouteOptimizationError("도착지 좌표가 없습니다.")
    if start_idx is not None and end_idx is not None and start_idx == end_idx and len(nodes) > 1:
        raise RouteOptimizationError("출발지와 도착지는 달라야 합니다.")

    mode = normalize_optimization_mode(optimization_mode)
    user_start_fixed = start_idx is not None
    user_end_fixed = end_idx is not None
    congestion_level = congestion_level or "normal"

    progress("1/4 이동시간 계산 중…")
    travel_matrix = build_travel_matrix(nodes, on_progress=on_progress)
    car_estimated_legs = sum(
        1
        for row in travel_matrix
        for leg in row
        if leg.get("car_estimated") and int(leg.get("car_time_sec") or 0) > 0
    )
    walk_estimated_legs = sum(
        1
        for row in travel_matrix
        for leg in row
        if leg.get("walk_estimated") and int(leg.get("walk_time_sec") or 0) > 0
    )
    if car_estimated_legs:
        sample_err = next(
            (
                leg.get("walk_error")
                for row in travel_matrix
                for leg in row
                if leg.get("car_estimated") and leg.get("walk_error")
            ),
            None,
        )
        hint = ""
        if sample_err and "429" in sample_err:
            hint = " TMAP 호출 한도(429)에 걸린 경우 잠시 후 다시 시도해 주세요."
        warnings.append(
            f"TMAP 차량 경로 API 오류로 {car_estimated_legs}개 구간을 직선 거리 기반으로 추정했습니다. (ER-009){hint}"
        )
    elif walk_estimated_legs:
        warnings.append(
            f"TMAP 도보 경로 API 오류로 {walk_estimated_legs}개 구간을 직선 거리 기반으로 추정했습니다."
        )

    cluster_plan = build_cluster_plan(
        nodes, travel_matrix, travel_region, congestion_level, mode, on_progress=on_progress
    )
    cost_matrix = build_cluster_aware_cost_matrix(
        travel_matrix, cluster_plan, nodes, mode, congestion_level
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

    progress("4/4 경로 최적화 (OR-Tools)…")
    order, resolved_start, resolved_end = _solve_order_flexible(
        cost_matrix,
        start_idx,
        end_idx,
        travel_matrix,
        mapped_rules,
        reservation_by_index or None,
        trip_start_minutes,
    )
    start_idx = resolved_start if resolved_start is not None else start_idx
    end_idx = resolved_end if resolved_end is not None else end_idx

    if not order:
        relaxed_matrix = apply_walk_limit(travel_matrix, WALK_TIME_FALLBACK_MINUTES)
        relaxed_plan = build_cluster_plan(
            nodes, relaxed_matrix, travel_region, congestion_level, mode, on_progress=on_progress
        )
        relaxed_cost = build_cluster_aware_cost_matrix(
            relaxed_matrix, relaxed_plan, nodes, mode, congestion_level
        )
        order, _, _ = _solve_order_flexible(
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
        order, _, _ = _solve_order_flexible(
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
        order, g_start, g_end = _greedy_order_flexible(
            cost_matrix, start_idx, end_idx, mapped_rules
        )
        if order:
            start_idx = g_start if g_start is not None else start_idx
            end_idx = g_end if g_end is not None else end_idx
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

    if start_idx is None and order:
        start_idx = order[0]
    if end_idx is None and order:
        end_idx = order[-1]

    if user_start_fixed and not user_end_fixed:
        end_name = nodes[end_idx].get("type") or nodes[end_idx].get("normalized_address") or "종료 지점"
        warnings.append(f"도착지를 지정하지 않아 **{end_name}** 에서 종료하는 경로를 선택했습니다.")
    elif user_end_fixed and not user_start_fixed:
        start_name = nodes[start_idx].get("type") or nodes[start_idx].get("normalized_address") or "출발 지점"
        warnings.append(f"출발지를 지정하지 않아 **{start_name}** 에서 시작하는 경로를 선택했습니다.")

    # 주차 거점 경로 안내
    hub_savings = sum(
        r.get("savings_sec", 0)
        for r in cluster_plan.cluster_routing.values()
        if r.get("use_parking")
    )
    if mode == MODE_MINIMIZE_PARKING and cluster_plan.cluster_use_parking:
        hub_count = sum(1 for v in cluster_plan.cluster_use_parking.values() if v)
        if hub_count:
            warnings.append(
                f"주차 횟수 최소화 모드: 공영주차장 {hub_count}곳을 거점으로 "
                "도보 방문 동선을 구성했습니다."
            )
    elif hub_savings > 0:
        warnings.append(
            f"공영주차장 거점 경로가 직접 차량 이동보다 약 {hub_savings // 60}분 유리하여 주차 중심 동선을 적용했습니다."
        )

    progress("4/4 경로 재구성 중…")
    stops, segments, parkings = build_parking_aware_route(
        order,
        nodes,
        travel_matrix,
        start_idx,
        end_idx,
        travel_region,
        trip_start_minutes,
        cluster_plan=cluster_plan,
        mark_start=user_start_fixed,
        mark_end=user_end_fixed,
        congestion_level=congestion_level,
        optimization_mode=mode,
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
        "start_fixed": user_start_fixed,
        "end_fixed": user_end_fixed,
        "optimization_mode": mode,
    }
    if warnings:
        route["message"] = "조건을 일부 완화하여 경로를 생성했습니다."
    return route
