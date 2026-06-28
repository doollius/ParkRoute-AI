from __future__ import annotations

from ortools.constraint_solver import pywrapcp, routing_enums_pb2

from constants.config import OPTIMIZATION_TIMEOUT_SEC


def solve_route_order(
    cost_matrix: list[list[int]],
    start_index: int,
    end_index: int,
) -> list[int] | None:
    """Return node visit order indices (includes start...end)."""
    n = len(cost_matrix)
    if n <= 1:
        return [0]
    if start_index == end_index and n == 1:
        return [start_index]

    manager = pywrapcp.RoutingIndexManager(n, 1, [start_index], [end_index])
    routing = pywrapcp.RoutingModel(manager)

    def transit_callback(from_index: int, to_index: int) -> int:
        from_node = manager.IndexToNode(from_index)
        to_node = manager.IndexToNode(to_index)
        return int(cost_matrix[from_node][to_node])

    transit_idx = routing.RegisterTransitCallback(transit_callback)
    routing.SetArcCostEvaluatorOfAllVehicles(transit_idx)

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
