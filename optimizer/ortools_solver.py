from __future__ import annotations

from typing import Any

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from constants.config import OPTIMIZATION_TIMEOUT_SEC
from utils.time_utils import minutes_to_seconds


def solve_route_order(
    cost_matrix: list[list[int]],
    start_index: int,
    end_index: int,
    mapped_rules: list[dict[str, Any]] | None = None,
    travel_matrix: list[list[dict[str, Any]]] | None = None,
    reservation_by_index: dict[int, int] | None = None,
    trip_start_minutes: int = 9 * 60,
) -> list[int] | None:
    n = len(cost_matrix)
    if n <= 1:
        return [0]

    manager = pywrapcp.RoutingIndexManager(n, 1, [start_index], [end_index])
    routing = pywrapcp.RoutingModel(manager)

    def cost_callback(from_index: int, to_index: int) -> int:
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return int(cost_matrix[from_node][to_node])

    cost_idx = routing.RegisterTransitCallback(cost_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(cost_idx)

    solver = routing.solver()
    mapped_rules = mapped_rules or []

    for rule in mapped_rules:
        if rule["rule_type"] == "immediate":
            from_idx = manager.NodeToIndex(rule["from_index"])
            to_idx = manager.NodeToIndex(rule["to_index"])
            solver.Add(routing.NextVar(from_idx) == to_idx)

    before_rules = [r for r in mapped_rules if r["rule_type"] == "before"]
    if before_rules:

        def position_callback(from_index: int, to_index: int) -> int:
            return 1

        pos_idx = routing.RegisterTransitCallback(position_callback)
        routing.AddDimension(pos_idx, 0, n, True, "Position")
        position = routing.GetDimensionOrDie("Position")
        for rule in before_rules:
            from_idx = manager.NodeToIndex(rule["from_index"])
            to_idx = manager.NodeToIndex(rule["to_index"])
            solver.Add(position.CumulVar(to_idx) > position.CumulVar(from_idx))

    if travel_matrix and reservation_by_index:

        def time_callback(from_index: int, to_index: int) -> int:
            from_node = manager.IndexToNode(from_index)
            to_node = manager.IndexToNode(to_index)
            leg = travel_matrix[from_node][to_node]
            if leg.get("walk_allowed") and leg.get("walk_time_sec") is not None:
                walk = int(leg["walk_time_sec"])
                car = int(leg.get("car_time_sec") or 999999)
                if walk <= car:
                    return walk
            return int(leg.get("car_time_sec") or 0)

        time_idx = routing.RegisterTransitCallback(time_callback)
        horizon = 24 * 3600
        routing.AddDimension(time_idx, horizon, horizon, False, "Time")
        time_dim = routing.GetDimensionOrDie("Time")
        start_sec = minutes_to_seconds(trip_start_minutes)
        time_dim.CumulVar(routing.Start(0)).SetRange(start_sec, start_sec)
        for node, res_minutes in reservation_by_index.items():
            idx = manager.NodeToIndex(node)
            time_dim.CumulVar(idx).SetMax(minutes_to_seconds(res_minutes))

    params = pywrapcp.DefaultRoutingSearchParameters()
    params.first_solution_strategy = (
        routing_enums_pb2.FirstSolutionStrategy.PATH_CHEAPEST_ARC
    )
    params.local_search_metaheuristic = (
        routing_enums_pb2.LocalSearchMetaheuristic.GUIDED_LOCAL_SEARCH
    )
    params.time_limit.seconds = OPTIMIZATION_TIMEOUT_SEC

    solution = routing.SolveWithParameters(params)
    if not solution:
        return None

    index = routing.Start(0)
    order: list[int] = []
    while not routing.IsEnd(index):
        order.append(manager.IndexToNode(index))
        index = solution.Value(routing.NextVar(index))
    order.append(manager.IndexToNode(index))
    return order
