from __future__ import annotations

from typing import Any

import streamlit as st

from api.geocode_api import resolve_address, resolve_place_query
from api.tmap_api import TmapGeocodingError
from models.place import create_place, place_selection_label
from services import visit_rule_service
from utils.address_validator import (
    validate_address,
    validate_place_name,
    validate_reservation_time,
)

from models.visit_rule import PICK_NONE

CUSTOM_START_ID = "__custom_start__"
CUSTOM_END_ID = "__custom_end__"


def _clear_place_geocode(place: dict[str, Any]) -> None:
    place["lat"] = None
    place["lng"] = None
    place["normalized_address"] = ""
    place["geocode_error"] = None
    place["geocode_status"] = "pending"
    place["poi_candidates"] = []
    place["matched_name"] = ""
    place.pop("_geocoded_for", None)
    place.pop("_geocode_note", None)
    place.pop("_manual_coords", None)


def ensure_default_places() -> None:
    if not st.session_state.places:
        st.session_state.places = [create_place(), create_place()]


def ensure_widget_keys() -> None:
    for place in st.session_state.places:
        pid = place["id"]
        if f"raw_{pid}" not in st.session_state:
            st.session_state[f"raw_{pid}"] = place.get("raw_input", "")
        if f"type_{pid}" not in st.session_state:
            st.session_state[f"type_{pid}"] = place.get("type", "")
        if f"manual_{pid}" not in st.session_state:
            st.session_state[f"manual_{pid}"] = place.get("use_manual_address", False)


def sync_places_from_widgets() -> None:
    for place in st.session_state.places:
        pid = place["id"]
        manual = bool(st.session_state.get(f"manual_{pid}", False))
        if manual != place.get("use_manual_address"):
            place["use_manual_address"] = manual
            _clear_place_geocode(place)

        place["type"] = str(st.session_state.get(f"type_{pid}", place.get("type", ""))).strip()

        raw = str(st.session_state.get(f"raw_{pid}", "")).strip()
        if raw != place.get("raw_input", ""):
            place["raw_input"] = raw
            if manual:
                _clear_place_geocode(place)

        prev_name = place.get("_synced_name", "")
        if place["type"] != prev_name:
            place["_synced_name"] = place["type"]
            if not manual:
                _clear_place_geocode(place)


def batch_resolve_places() -> None:
    """「다음」 클릭 시 모든 장소를 TMAP으로 일괄 검색."""
    for place in st.session_state.places:
        _resolve_single_place(place)


def batch_resolve_place_at(index: int) -> None:
    places = st.session_state.places
    if 0 <= index < len(places):
        _resolve_single_place(places[index])


def _apply_confirmed_result(place: dict[str, Any], result: dict[str, Any]) -> None:
    place["lat"] = result["lat"]
    place["lng"] = result["lng"]
    place["normalized_address"] = result["normalized_address"]
    place["matched_name"] = result.get("matched_name") or result["normalized_address"]
    place["geocode_status"] = "confirmed"
    place["geocode_error"] = None
    place["poi_candidates"] = []
    place["_geocoded_for"] = place.get("type") or place.get("raw_input", "")


def _resolve_single_place(place: dict[str, Any]) -> None:
    manual = place.get("use_manual_address", False)
    name = place.get("type", "").strip()

    if manual:
        raw = place.get("raw_input", "").strip()
        if not raw:
            _clear_place_geocode(place)
            place["geocode_status"] = "failed"
            place["geocode_error"] = "주소를 입력하세요."
            return
        ok, msg = validate_address(raw)
        if not ok:
            _clear_place_geocode(place)
            place["geocode_status"] = "failed"
            place["geocode_error"] = msg
            return
        try:
            result = resolve_address(raw)
            _apply_confirmed_result(
                place,
                {
                    "lat": result["lat"],
                    "lng": result["lng"],
                    "normalized_address": result["normalized_address"],
                    "matched_name": name or result["normalized_address"],
                },
            )
        except TmapGeocodingError as exc:
            _clear_place_geocode(place)
            place["geocode_status"] = "failed"
            place["geocode_error"] = str(exc)
        return

    if not name:
        _clear_place_geocode(place)
        place["geocode_status"] = "failed"
        place["geocode_error"] = "장소명을 입력하세요."
        return

    outcome = resolve_place_query(name)
    status = outcome.get("status")
    if status == "confirmed":
        _apply_confirmed_result(place, outcome["result"])
    elif status == "pick":
        place["geocode_status"] = "needs_pick"
        place["poi_candidates"] = outcome.get("candidates", [])
        place["geocode_error"] = None
        place["lat"] = None
        place["lng"] = None
        place["normalized_address"] = ""
        place["matched_name"] = ""
    else:
        _clear_place_geocode(place)
        place["geocode_status"] = "failed"
        place["geocode_error"] = outcome.get("error") or "검색에 실패했습니다."


def select_poi_candidate(place_id: str, candidate_index: int) -> None:
    place = get_place_by_id(place_id)
    if not place:
        return
    candidates = place.get("poi_candidates") or []
    if candidate_index < 0 or candidate_index >= len(candidates):
        return
    picked = candidates[candidate_index]
    _apply_confirmed_result(
        place,
        {
            "lat": picked["lat"],
            "lng": picked["lng"],
            "normalized_address": picked["normalized_address"],
            "matched_name": picked["name"],
        },
    )


def geocode_pending_places() -> None:
    """레거시 — 입력 중 실시간 geocoding 비활성화. 확인 단계에서만 처리."""
    return


def add_place() -> None:
    if len(st.session_state.places) >= 10:
        return
    place = create_place()
    st.session_state.places.append(place)
    st.session_state[f"raw_{place['id']}"] = ""
    st.session_state[f"type_{place['id']}"] = ""
    st.session_state[f"manual_{place['id']}"] = False


def move_place(place_id: str, direction: int) -> None:
    places = st.session_state.places
    idx = next((i for i, p in enumerate(places) if p["id"] == place_id), None)
    if idx is None:
        return
    new_idx = idx + direction
    if new_idx < 0 or new_idx >= len(places):
        return
    places[idx], places[new_idx] = places[new_idx], places[idx]


def reorder_places(ordered_ids: list[str]) -> None:
    id_to_place = {p["id"]: p for p in st.session_state.places}
    if set(ordered_ids) != set(id_to_place):
        return
    st.session_state.places = [id_to_place[pid] for pid in ordered_ids]


def set_manual_coords(place_id: str, lat: float, lng: float) -> str | None:
    if not (-90.0 <= lat <= 90.0):
        return "위도는 -90 ~ 90 범위여야 합니다."
    if not (-180.0 <= lng <= 180.0):
        return "경도는 -180 ~ 180 범위여야 합니다."
    place = get_place_by_id(place_id)
    if not place:
        return "장소를 찾을 수 없습니다."
    raw = place.get("raw_input", "").strip() or place.get("type", "").strip()
    place["lat"] = lat
    place["lng"] = lng
    place["normalized_address"] = raw or f"{lat:.5f}, {lng:.5f}"
    place["geocode_error"] = None
    place["geocode_status"] = "confirmed"
    place["_geocoded_for"] = raw
    place["_manual_coords"] = True
    place.pop("_geocode_note", None)
    return None


def delete_place(place_id: str) -> None:
    if len(st.session_state.places) <= 2:
        return
    st.session_state.places = [p for p in st.session_state.places if p["id"] != place_id]
    for key in (f"raw_{place_id}", f"type_{place_id}", f"manual_{place_id}"):
        st.session_state.pop(key, None)
    if st.session_state.get("start_place_id") == place_id:
        st.session_state.start_place_id = None
    if st.session_state.get("end_place_id") == place_id:
        st.session_state.end_place_id = None


def geocoded_places() -> list[dict[str, Any]]:
    return [p for p in st.session_state.places if p.get("lat") is not None and p.get("lng") is not None]


def failed_geocode_places() -> list[dict[str, Any]]:
    failed: list[dict[str, Any]] = []
    for place in st.session_state.places:
        if place.get("geocode_status") == "failed":
            failed.append(place)
        elif place.get("geocode_status") == "needs_pick":
            continue
        elif place.get("lat") is None and (place.get("type") or place.get("raw_input")):
            failed.append(place)
    return failed


def needs_pick_places() -> list[dict[str, Any]]:
    return [p for p in st.session_state.places if p.get("geocode_status") == "needs_pick"]


def _base_validation_errors() -> list[str]:
    errors: list[str] = []
    if len(st.session_state.places) < 2:
        errors.append("장소는 최소 2개 이상 필요합니다.")
    return errors


def _endpoint_validation_errors() -> list[str]:
    errors: list[str] = []
    geocoded_ids = {p["id"] for p in geocoded_places()}

    if st.session_state.get("use_custom_start"):
        addr = str(st.session_state.get("custom_start_address", "")).strip()
        if not addr:
            errors.append("다른 출발지 주소를 입력하세요.")
        else:
            ok, msg = validate_address(addr)
            if not ok:
                errors.append(f"출발지 주소: {msg}")
            elif not st.session_state.get("custom_start_node", {}).get("lat"):
                err = st.session_state.get("custom_start_geocode_error") or "좌표 변환 중이거나 실패했습니다."
                errors.append(f"출발지: {err}")
    elif st.session_state.get("start_place_id") and st.session_state.start_place_id not in geocoded_ids:
        errors.append("출발지 좌표가 없습니다. 장소 확인을 완료하거나 다른 장소를 선택하세요.")

    if st.session_state.get("use_custom_end"):
        addr = str(st.session_state.get("custom_end_address", "")).strip()
        if not addr:
            errors.append("다른 도착지 주소를 입력하세요.")
        else:
            ok, msg = validate_address(addr)
            if not ok:
                errors.append(f"도착지 주소: {msg}")
            elif not st.session_state.get("custom_end_node", {}).get("lat"):
                err = st.session_state.get("custom_end_geocode_error") or "좌표 변환 중이거나 실패했습니다."
                errors.append(f"도착지: {err}")
    elif st.session_state.get("end_place_id") and st.session_state.end_place_id not in geocoded_ids:
        errors.append("도착지 좌표가 없습니다. 장소 확인을 완료하거나 다른 장소를 선택하세요.")

    start_id = _resolved_start_place_id()
    end_id = _resolved_end_place_id()
    if start_id and end_id and start_id == end_id:
        errors.append("출발지와 도착지는 달라야 합니다.")

    return errors


def _resolved_start_place_id() -> str | None:
    if st.session_state.get("use_custom_start"):
        return CUSTOM_START_ID
    start_id = st.session_state.get("start_place_id")
    return start_id if start_id and start_id != PICK_NONE else None


def _resolved_end_place_id() -> str | None:
    if st.session_state.get("use_custom_end"):
        return CUSTOM_END_ID
    end_id = st.session_state.get("end_place_id")
    return end_id if end_id and end_id != PICK_NONE else None


def infer_travel_region(places: list[dict[str, Any]] | None = None) -> str:
    region = str(st.session_state.get("travel_region", "")).strip()
    if region:
        return region
    from utils.address_validator import ADMIN_PATTERN

    for place in places or geocoded_places():
        addr = (place.get("normalized_address") or place.get("raw_input") or "").strip()
        match = ADMIN_PATTERN.search(addr)
        if match:
            return match.group(0)
    for key in ("custom_start_node", "custom_end_node"):
        node = st.session_state.get(key) or {}
        addr = (node.get("normalized_address") or node.get("raw_input") or "").strip()
        match = ADMIN_PATTERN.search(addr)
        if match:
            return match.group(0)
    return ""


def geocode_custom_endpoints() -> None:
    for kind, node_key, err_key, label in (
        ("start", "custom_start_node", "custom_start_geocode_error", "출발지"),
        ("end", "custom_end_node", "custom_end_geocode_error", "도착지"),
    ):
        use_key = f"use_custom_{kind}"
        addr_key = f"custom_{kind}_address"
        if not st.session_state.get(use_key):
            st.session_state.pop(node_key, None)
            st.session_state.pop(err_key, None)
            continue

        addr = str(st.session_state.get(addr_key, "")).strip()
        if not addr:
            st.session_state.pop(node_key, None)
            st.session_state.pop(err_key, None)
            continue

        existing = st.session_state.get(node_key) or {}
        if existing.get("raw_input") == addr and existing.get("lat") is not None:
            continue

        ok, msg = validate_address(addr)
        if not ok:
            st.session_state.pop(node_key, None)
            st.session_state[err_key] = msg
            continue

        try:
            result = resolve_address(addr)
            st.session_state[node_key] = {
                "id": CUSTOM_START_ID if kind == "start" else CUSTOM_END_ID,
                "raw_input": addr,
                "normalized_address": result["normalized_address"],
                "lat": result["lat"],
                "lng": result["lng"],
                "type": label,
                "reservation_time": None,
                "is_custom_endpoint": True,
            }
            st.session_state.pop(err_key, None)
        except TmapGeocodingError as exc:
            st.session_state.pop(node_key, None)
            st.session_state[err_key] = str(exc)


def build_optimization_graph(
    visit_places: list[dict[str, Any]],
) -> tuple[list[dict[str, Any]], int | None, int | None]:
    nodes = [dict(p) for p in visit_places]
    start_idx: int | None = None
    end_idx: int | None = None

    if st.session_state.get("use_custom_start"):
        custom = st.session_state.get("custom_start_node")
        if custom and custom.get("lat") is not None:
            nodes.insert(0, dict(custom))
            start_idx = 0
    else:
        start_id = st.session_state.get("start_place_id")
        if start_id and start_id != PICK_NONE:
            start_idx = next((i for i, p in enumerate(nodes) if p["id"] == start_id), None)

    if st.session_state.get("use_custom_end"):
        custom = st.session_state.get("custom_end_node")
        if custom and custom.get("lat") is not None:
            nodes.append(dict(custom))
            end_idx = len(nodes) - 1
    else:
        end_id = st.session_state.get("end_place_id")
        if end_id and end_id != PICK_NONE:
            end_idx = next((i for i, p in enumerate(nodes) if p["id"] == end_id), None)

    return nodes, start_idx, end_idx


def get_route_endpoint_label(kind: str) -> str:
    if kind == "start":
        if st.session_state.get("use_custom_start"):
            node = st.session_state.get("custom_start_node") or {}
            return node.get("type") or node.get("normalized_address") or node.get("raw_input") or "(미입력)"
        place = get_place_by_id(st.session_state.get("start_place_id"))
        if place:
            places = st.session_state.places
            idx = next((i for i, p in enumerate(places) if p["id"] == place["id"]), 0)
            return place_selection_label(place, idx, places)
        return "(미지정)"
    if st.session_state.get("use_custom_end"):
        node = st.session_state.get("custom_end_node") or {}
        return node.get("type") or node.get("normalized_address") or node.get("raw_input") or "(미입력)"
    place = get_place_by_id(st.session_state.get("end_place_id"))
    if place:
        places = st.session_state.places
        idx = next((i for i, p in enumerate(places) if p["id"] == place["id"]), 0)
        return place_selection_label(place, idx, places)
    return "(미지정)"


def get_review_start_text() -> str:
    if st.session_state.get("use_custom_start"):
        node = st.session_state.get("custom_start_node") or {}
        return (node.get("normalized_address") or node.get("raw_input") or "").strip() or "(미입력)"
    start_id = st.session_state.get("start_place_id")
    if start_id and start_id != PICK_NONE:
        place = get_place_by_id(start_id)
        if place:
            return str(place.get("type", "")).strip() or "-"
    return "미지정"


def get_review_end_text() -> str:
    if st.session_state.get("use_custom_end"):
        node = st.session_state.get("custom_end_node") or {}
        return (node.get("normalized_address") or node.get("raw_input") or "").strip() or "(미입력)"
    end_id = st.session_state.get("end_place_id")
    if end_id and end_id != PICK_NONE:
        place = get_place_by_id(end_id)
        if place:
            return str(place.get("type", "")).strip() or "-"
    return "미지정"


def get_review_visit_types() -> list[str]:
    exclude_ids: set[str] = set()
    if not st.session_state.get("use_custom_start"):
        start_id = st.session_state.get("start_place_id")
        if start_id and start_id != PICK_NONE:
            exclude_ids.add(start_id)
    if not st.session_state.get("use_custom_end"):
        end_id = st.session_state.get("end_place_id")
        if end_id and end_id != PICK_NONE:
            exclude_ids.add(end_id)

    types: list[str] = []
    for place in st.session_state.places:
        if place["id"] in exclude_ids:
            continue
        name = str(place.get("type", "")).strip()
        if name:
            types.append(name)
    return types


def get_review_optimization_goal() -> str:
    mode = st.session_state.get("optimization_mode", "minimize_walk")
    return "도보 최소화" if mode == "minimize_walk" else "총 이동시간 최소화"


def route_endpoint_status() -> str:
    has_start = bool(_resolved_start_place_id())
    has_end = bool(_resolved_end_place_id())
    if has_start and has_end:
        return "출발·도착 설정됨"
    if has_start:
        return "출발만 설정"
    if has_end:
        return "도착만 설정"
    return "미설정 (자동)"


def resolved_start_place_id() -> str | None:
    return _resolved_start_place_id()


def resolved_end_place_id() -> str | None:
    return _resolved_end_place_id()


def _place_text_errors() -> list[str]:
    errors: list[str] = []
    for i, place in enumerate(st.session_state.places):
        type_ok, type_msg = validate_place_name(place.get("type"))
        if not type_ok:
            errors.append(f"장소 {i + 1}: {type_msg}")
        if place.get("use_manual_address"):
            raw = place.get("raw_input", "").strip()
            if len(raw) < 2:
                errors.append(f"장소 {i + 1}: 주소를 입력하세요.")
            else:
                ok, msg = validate_address(raw)
                if not ok:
                    errors.append(f"장소 {i + 1}: {msg}")
    return errors


def _place_input_errors(strict_geocode: bool) -> list[str]:
    errors = _place_text_errors()
    if strict_geocode:
        for i, place in enumerate(st.session_state.places):
            if place.get("lat") is None or place.get("lng") is None:
                err = place.get("geocode_error") or "좌표가 확정되지 않았습니다."
                errors.append(f"장소 {i + 1}: {err}")
        for i, place in enumerate(st.session_state.places):
            res_ok, res_msg = validate_reservation_time(place.get("reservation_time"))
            if not res_ok:
                errors.append(f"장소 {i + 1}: {res_msg}")
    return errors


def validation_errors() -> list[str]:
    errors = _base_validation_errors()
    errors.extend(_place_input_errors(strict_geocode=True))
    errors.extend(_endpoint_validation_errors())
    place_ids = {p["id"] for p in st.session_state.places}
    start_ref = _resolved_start_place_id()
    end_ref = _resolved_end_place_id()
    errors.extend(
        visit_rule_service.validation_errors(
            place_ids,
            start_ref if start_ref in place_ids else None,
            end_ref if end_ref in place_ids else None,
        )
    )
    return errors


def partial_validation_errors() -> list[str]:
    errors = _base_validation_errors()
    geocoded = geocoded_places()
    if len(geocoded) < 2:
        errors.append("좌표가 확정된 장소가 2곳 이상 필요합니다.")
    errors.extend(_endpoint_validation_errors())
    return errors


def uses_partial_geocoding() -> bool:
    return bool(failed_geocode_places()) and len(geocoded_places()) >= 2


def places_step_errors() -> list[str]:
    """Step 1 (방문 장소) — 텍스트 입력만 검증 (API 호출 없음)."""
    errors = _base_validation_errors()
    errors.extend(_place_text_errors())
    return errors


def places_confirm_errors() -> list[str]:
    errors: list[str] = []
    for i, place in enumerate(st.session_state.places):
        status = place.get("geocode_status")
        if status == "needs_pick":
            errors.append(f"장소 {i + 1}: 후보 중 올바른 장소를 선택하세요.")
        elif status == "failed":
            errors.append(f"장소 {i + 1}: {place.get('geocode_error') or '검색 실패'}")
        elif place.get("lat") is None:
            errors.append(f"장소 {i + 1}: 위치 확인이 완료되지 않았습니다.")
    if len(geocoded_places()) < 2:
        errors.append("확정된 장소가 2곳 이상 필요합니다.")
    return errors


def can_proceed_to_places_confirm() -> bool:
    return not places_step_errors()


def can_proceed_to_trip_step() -> bool:
    return not places_confirm_errors()


def can_complete() -> bool:
    if not validation_errors():
        return True
    if uses_partial_geocoding() and not partial_validation_errors():
        return True
    return False


def prepare_optimization_input() -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    geocoded = geocoded_places()
    excluded = failed_geocode_places()
    warnings: list[str] = []

    if excluded:
        warnings.append(
            f"좌표 변환 실패 {len(excluded)}곳은 제외하고 최적화합니다. (ER-005)"
        )
        for place in excluded:
            label = place.get("type") or place.get("raw_input", "")
            reason = place.get("geocode_error") or "좌표 없음"
            warnings.append(f"· 제외 — {label}: {reason}")

    valid_ids = {p["id"] for p in geocoded}
    pruned_rules = [
        r
        for r in st.session_state.get("visit_rules", [])
        if r.get("from_id") in valid_ids and r.get("to_id") in valid_ids
    ]
    dropped = len(st.session_state.get("visit_rules", [])) - len(pruned_rules)
    if dropped:
        warnings.append(f"제외된 장소와 연결된 방문 규칙 {dropped}건을 무시합니다.")

    return geocoded, warnings, excluded, pruned_rules


def get_place_by_id(place_id: str | None) -> dict[str, Any] | None:
    if not place_id:
        return None
    for place in st.session_state.places:
        if place["id"] == place_id:
            return place
    return None


def progress_summary() -> dict[str, int]:
    places = st.session_state.places
    geocoded = sum(1 for p in places if p.get("lat") is not None)
    return {
        "place_count": len(places),
        "geocoded_count": geocoded,
        "reservation_count": 0,
    }


def place_options() -> list[tuple[str, str]]:
    places = st.session_state.places
    return [(p["id"], place_selection_label(p, i, places)) for i, p in enumerate(places)]
