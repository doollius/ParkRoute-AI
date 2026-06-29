from __future__ import annotations

from typing import Any

from optimizer.multimodal_cost import _walk_order_from_parking
from optimizer.parking_graph import ClusterPlan, cluster_uses_parking, parking_for_leg_indices
from optimizer.scoring import choose_segment_mode
from services.map_service import get_travel_times
from services.parking_service import get_parking_candidates, pick_parking_for_places
from utils.parking_cost import calculate_parking_cost
from utils.parking_event import parking_event_minutes
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
    display_name = node.get("type") if node.get("is_custom_endpoint") else (
        node.get("normalized_address") or node.get("raw_input") or "장소"
    )
    stop = {
        "id": node["id"],
        "label": label,
        "name": display_name,
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


def _append_parking_event(
    segments: list[dict[str, Any]],
    place_stop: dict[str, Any],
    minutes: int,
) -> None:
    if minutes <= 0:
        return
    segments.append(
        {
            "from_id": place_stop["id"],
            "to_id": place_stop["id"],
            "from_label": place_stop["label"],
            "to_label": place_stop["label"],
            "mode": "parking_event",
            "time_sec": minutes * 60,
            "distance_m": 0,
        }
    )


def _place_stop_label(
    node_idx: int,
    *,
    start_idx: int,
    end_idx: int,
    mark_start: bool,
    mark_end: bool,
    visit_num: int,
    at_route_start: bool = False,
) -> tuple[str, int]:
    if at_route_start and mark_start and node_idx == start_idx:
        return "S", visit_num
    if mark_end and node_idx == end_idx:
        return "E", visit_num
    visit_num += 1
    return str(visit_num), visit_num


def build_parking_aware_route(
    order: list[int],
    nodes: list[dict[str, Any]],
    travel_matrix: list[list[dict[str, Any]]],
    start_idx: int,
    end_idx: int,
    travel_region: str,
    trip_start_minutes: int,
    cluster_plan: ClusterPlan | None = None,
    mark_start: bool = True,
    mark_end: bool = True,
    congestion_level: str = "normal",
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

    def add_travel(
        from_s: dict[str, Any],
        to_s: dict[str, Any],
        *,
        prefer_walk: bool = False,
        parking_event_node: dict[str, Any] | None = None,
    ) -> None:
        nonlocal current_minutes, prev_stop
        leg = get_travel_times(from_s["lat"], from_s["lng"], to_s["lat"], to_s["lng"])
        mode = "walk" if prefer_walk and leg.get("walk_allowed") else choose_segment_mode(leg)
        time_key = "walk_time_sec" if mode == "walk" else "car_time_sec"
        current_minutes += max(1, int(leg.get(time_key) or 0) // 60)
        _append_segment(segments, from_s, to_s, leg, mode)
        to_s["arrival_time"] = minutes_to_hhmm(current_minutes)
        stops.append(to_s)

        if parking_event_node and to_s.get("kind") == "place":
            evt_min = parking_event_minutes(parking_event_node, congestion_level)
            current_minutes += evt_min
            _append_parking_event(segments, to_s, evt_min)

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
                label, visit_num = _place_stop_label(
                    idx,
                    start_idx=start_idx,
                    end_idx=end_idx,
                    mark_start=mark_start,
                    mark_end=mark_end,
                    visit_num=visit_num,
                    at_route_start=True,
                )
                stops.append(_node_stop(node, label, current_minutes))
                prev_stop = stops[-1]
                continue
            if prev_stop is None:
                continue
            label, visit_num = _place_stop_label(
                idx,
                start_idx=start_idx,
                end_idx=end_idx,
                mark_start=mark_start,
                mark_end=mark_end,
                visit_num=visit_num,
            )
            add_travel(prev_stop, _node_stop(node, label))
            continue

        use_hub = cluster_plan and cluster_uses_parking(cluster_plan, leg)
        parking = None
        if cluster_plan and use_hub:
            parking = parking_for_leg_indices(leg, cluster_plan)
        if not parking and use_hub:
            parking = pick_parking_for_places(leg, nodes, candidates, used_parking_ids, get_travel_times)

        parking_num += 1
        p_label = f"P{parking_num}"

        if parking and use_hub:
            parkings_meta.append({**parking, "label": p_label})
            p_stop = _parking_stop(parking, p_label)
            parking_stay[parking["id"]] = current_minutes

            if prev_stop is None:
                first = nodes[leg[0]]
                if leg[0] == start_idx:
                    label, visit_num = _place_stop_label(
                        leg[0],
                        start_idx=start_idx,
                        end_idx=end_idx,
                        mark_start=mark_start,
                        mark_end=mark_end,
                        visit_num=visit_num,
                        at_route_start=True,
                    )
                    stops.append(_node_stop(first, label, current_minutes))
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

            visit_order = _walk_order_from_parking(parking, leg, nodes, get_travel_times) or leg

            for idx in visit_order:
                node = nodes[idx]
                label, visit_num = _place_stop_label(
                    idx,
                    start_idx=start_idx,
                    end_idx=end_idx,
                    mark_start=mark_start,
                    mark_end=mark_end,
                    visit_num=visit_num,
                )
                place_stop = _node_stop(node, label)
                add_travel(
                    prev_stop,
                    place_stop,
                    prefer_walk=True,
                    parking_event_node=node,
                )

            # D → A → B → C → D : 주차장 복귀 (도보)
            if prev_stop and prev_stop.get("id") != p_stop["id"]:
                leg = get_travel_times(
                    prev_stop["lat"], prev_stop["lng"], p_stop["lat"], p_stop["lng"]
                )
                current_minutes += max(1, int(leg.get("walk_time_sec") or 0) // 60)
                _append_segment(segments, prev_stop, p_stop, leg, "walk")
                prev_stop = p_stop

            finalize_parking_stay(parking["id"], current_minutes)
        else:
            for idx in leg:
                node = nodes[idx]
                if prev_stop is None:
                    label, visit_num = _place_stop_label(
                        idx,
                        start_idx=start_idx,
                        end_idx=end_idx,
                        mark_start=mark_start,
                        mark_end=mark_end,
                        visit_num=visit_num,
                        at_route_start=(idx == start_idx),
                    )
                    stops.append(_node_stop(node, label, current_minutes))
                    prev_stop = stops[-1]
                    continue
                label, visit_num = _place_stop_label(
                    idx,
                    start_idx=start_idx,
                    end_idx=end_idx,
                    mark_start=mark_start,
                    mark_end=mark_end,
                    visit_num=visit_num,
                )
                add_travel(prev_stop, _node_stop(node, label))

    return stops, segments, parkings_meta
