from __future__ import annotations

from typing import Any

from optimizer.parking_graph import ClusterPlan, parking_for_leg_indices
from optimizer.scoring import choose_segment_mode
from services.map_service import get_travel_times
from services.parking_service import get_parking_candidates, pick_parking_for_places
from utils.parking_cost import calculate_parking_cost
from utils.time_utils import minutes_to_hhmm


def _split_order_into_legs(order: list[int], travel_matrix: list[list[dict[str, Any]]]) -> list[list[int]]:
    if not order:
        return []
    legs: list[list[int]] = [[order[0]]]
    for i in range(1, len(order)):
        prev, curr = order[i - 1], order[i]
        if choose_segment_mode(travel_matrix[prev][curr]) == "walk":
            legs[-1].append(curr)
        else:
            legs.append([curr])
    return legs


def _node_stop(node: dict[str, Any], label: str, arrival_min: int | None = None) -> dict[str, Any]:
    stop = {
        "id": node["id"],
        "label": label,
        "name": node.get("normalized_address") or node.get("raw_input") or "장소",
        "type": node.get("type"),
        "kind": "place",
        "lat": node["lat"],
        "lng": node["lng"],
        "reservation_time": node.get("reservation_time"),
    }
    if arrival_min is not None:
        stop["arrival_time"] = minutes_to_hhmm(arrival_min)
    return stop


def _parking_stop(parking: dict[str, Any], label: str, arrival_min: int | None = None) -> dict[str, Any]:
    stop = {
        "id": f"parking_{parking['id']}",
        "label": label,
        "name": parking["name"],
        "type": "주차장",
        "kind": "parking",
        "lat": parking["lat"],
        "lng": parking["lng"],
        "address": parking.get("address", ""),
    }
    if arrival_min is not None:
        stop["arrival_time"] = minutes_to_hhmm(arrival_min)
    return stop


def _append_segment(
    segments: list[dict[str, Any]],
    from_stop: dict[str, Any],
    to_stop: dict[str, Any],
    leg: dict[str, Any],
    mode: str,
) -> None:
    time_key = "walk_time_sec" if mode == "walk" else "car_time_sec"
    time_sec = int(leg.get(time_key) or 0)
    dist = leg.get("walk_distance_m") if mode == "walk" else leg.get("car_distance_m")
    segments.append(
        {
            "from_id": from_stop["id"],
            "to_id": to_stop["id"],
            "from_label": from_stop["label"],
            "to_label": to_stop["label"],
            "mode": mode,
            "time_sec": time_sec,
            "distance_m": dist or 0,
        }
    )


def build_parking_aware_route(
    order: list[int],
    nodes: list[dict[str, Any]],
    travel_matrix: list[list[dict[str, Any]]],
    start_idx: int,
    end_idx: int,
    travel_region: str,
    trip_start_minutes: int,
    cluster_plan: ClusterPlan | None = None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    legs = _split_order_into_legs(order, travel_matrix)
    candidates = get_parking_candidates(nodes, travel_region)
    used_parking_ids: set[str] = set()

    stops: list[dict[str, Any]] = []
    segments: list[dict[str, Any]] = []
    parkings_meta: list[dict[str, Any]] = []
    parking_stay: dict[str, int] = {}
    current_minutes = trip_start_minutes
    visit_num = 0
    parking_num = 0
    prev_stop: dict[str, Any] | None = None

    def add_travel(from_s: dict[str, Any], to_s: dict[str, Any], prefer_walk: bool = False) -> None:
        nonlocal current_minutes, prev_stop
        leg = get_travel_times(from_s["lat"], from_s["lng"], to_s["lat"], to_s["lng"])
        mode = "walk" if prefer_walk and leg.get("walk_allowed") else choose_segment_mode(leg)
        time_key = "walk_time_sec" if mode == "walk" else "car_time_sec"
        current_minutes += max(1, int(leg.get(time_key) or 0) // 60)
        _append_segment(segments, from_s, to_s, leg, mode)
        to_s["arrival_time"] = minutes_to_hhmm(current_minutes)
        stops.append(to_s)
        prev_stop = to_s

    def finalize_parking_stay(parking_id: str, depart_minutes: int) -> None:
        if parking_id not in parking_stay:
            return
        arrive = parking_stay.pop(parking_id)
        stay = max(1, depart_minutes - arrive)
        for meta in parkings_meta:
            if meta["id"] == parking_id:
                cost = calculate_parking_cost(meta, stay)
                meta["stay_minutes"] = stay
                meta["estimated_cost"] = cost["estimated_cost"]
                meta["cost_detail"] = cost
                break

    for leg in legs:
        if not leg:
            continue

        if len(leg) == 1:
            idx = leg[0]
            node = nodes[idx]
            if idx == start_idx and not stops:
                stops.append(_node_stop(node, "S", current_minutes))
                prev_stop = stops[-1]
                continue
            if prev_stop is None:
                continue
            if idx == end_idx:
                label = "E"
            else:
                visit_num += 1
                label = str(visit_num)
            add_travel(prev_stop, _node_stop(node, label))
            continue

        parking = None
        if cluster_plan:
            parking = parking_for_leg_indices(leg, cluster_plan)
        if not parking:
            parking = pick_parking_for_places(leg, nodes, candidates, used_parking_ids, get_travel_times)
        parking_num += 1
        p_label = f"P{parking_num}"

        if parking:
            parkings_meta.append({**parking, "label": p_label})
            p_stop = _parking_stop(parking, p_label)
            parking_stay[parking["id"]] = current_minutes

            if prev_stop is None:
                first = nodes[leg[0]]
                if leg[0] == start_idx:
                    stops.append(_node_stop(first, "S", current_minutes))
                    prev_stop = stops[-1]
                    leg = leg[1:]
                    if not leg:
                        continue

            if prev_stop and prev_stop.get("kind") != "parking":
                add_travel(prev_stop, p_stop)
            elif prev_stop is None:
                stops.append(p_stop)
                prev_stop = p_stop
                p_stop["arrival_time"] = minutes_to_hhmm(current_minutes)

            for idx in leg:
                node = nodes[idx]
                label = "E" if idx == end_idx else str(visit_num + 1)
                if label != "E":
                    visit_num += 1
                    label = str(visit_num)
                add_travel(prev_stop, _node_stop(node, label), prefer_walk=True)

            finalize_parking_stay(parking["id"], current_minutes)
        else:
            for idx in leg:
                node = nodes[idx]
                if prev_stop is None:
                    label = "S" if idx == start_idx else "1"
                    if label == "1":
                        visit_num = max(visit_num, 1)
                    stops.append(_node_stop(node, label, current_minutes))
                    prev_stop = stops[-1]
                    continue
                label = "E" if idx == end_idx else str(visit_num + 1)
                if label != "E":
                    visit_num += 1
                    label = str(visit_num)
                add_travel(prev_stop, _node_stop(node, label))

    return stops, segments, parkings_meta
