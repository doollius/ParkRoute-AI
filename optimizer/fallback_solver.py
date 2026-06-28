from __future__ import annotations

from typing import Any

from models.visit_rule import RULE_IMMEDIATE


def greedy_route_order(
    cost_matrix: list[list[int]],
    start_index: int,
    end_index: int,
    mapped_rules: list[dict[str, Any]] | None = None,
) -> list[int] | None:
    """Nearest-neighbor fallback when OR-Tools finds no solution (ER-007)."""
    n = len(cost_matrix)
    if n <= 1:
        return [0]

    immediate: dict[int, int] = {}
    for rule in mapped_rules or []:
        if rule.get("rule_type") == RULE_IMMEDIATE:
            immediate[rule["from_index"]] = rule["to_index"]

    middle = [i for i in range(n) if i not in (start_index, end_index)]
    order = [start_index]
    current = start_index
    remaining = set(middle)

    while remaining:
        if current in immediate and immediate[current] in remaining:
            nxt = immediate[current]
        else:
            nxt = min(remaining, key=lambda j: cost_matrix[current][j])
        order.append(nxt)
        remaining.remove(nxt)
        current = nxt

    if end_index != start_index:
        order.append(end_index)

    if len(order) != n or order[0] != start_index or order[-1] != end_index:
        return None
    return order
