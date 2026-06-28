from __future__ import annotations

from typing import Any

import streamlit as st

from api.geocode_api import resolve_address
from api.tmap_api import TmapGeocodingError
from models.place import create_place, place_label
from utils.address_validator import validate_address, validate_reservation_time


def ensure_default_places() -> None:
    if not st.session_state.places:
        st.session_state.places = [create_place(), create_place()]


def ensure_widget_keys() -> None:
    for place in st.session_state.places:
        pid = place["id"]
        if f"raw_{pid}" not in st.session_state:
            st.session_state[f"raw_{pid}"] = place.get("raw_input", "")
        if f"type_{pid}" not in st.session_state:
            st.session_state[f"type_{pid}"] = place.get("type", "맛집")
        if f"res_{pid}" not in st.session_state:
            st.session_state[f"res_{pid}"] = place.get("reservation_time") or ""


def sync_places_from_widgets() -> None:
    for place in st.session_state.places:
        pid = place["id"]
        raw = str(st.session_state.get(f"raw_{pid}", "")).strip()
        if raw != place.get("raw_input", ""):
            place["raw_input"] = raw
            place["lat"] = None
            place["lng"] = None
            place["normalized_address"] = ""
            place["geocode_error"] = None
            place["_geocoded_for"] = ""

        place["type"] = st.session_state.get(f"type_{pid}", place.get("type", "맛집"))
        res_raw = str(st.session_state.get(f"res_{pid}", "")).strip()
        place["reservation_time"] = res_raw or None


def _should_geocode(raw: str) -> bool:
    ok, _ = validate_address(raw)
    if not ok:
        return False
    if len(raw) >= 12:
        return True
    return any(token in raw for token in ("로 ", "길 ", "동 ", "읍 ", "면 ", "리 ", "번길"))


def geocode_pending_places() -> None:
    for place in st.session_state.places:
        raw = place.get("raw_input", "").strip()
        if not raw:
            place["geocode_error"] = None
            place["lat"] = None
            place["lng"] = None
            continue

        if place.get("_geocoded_for") == raw and place.get("lat") is not None:
            continue

        ok, msg = validate_address(raw)
        if not ok:
            place["geocode_error"] = msg
            place["lat"] = None
            place["lng"] = None
            place["normalized_address"] = ""
            continue

        if not _should_geocode(raw) and not place.pop("_force_geocode", False):
            place["geocode_error"] = None
            continue

        try:
            result = resolve_address(raw)
            place["lat"] = result["lat"]
            place["lng"] = result["lng"]
            place["normalized_address"] = result["normalized_address"]
            place["geocode_error"] = None
            place["_geocoded_for"] = raw
            if result.get("source") == "poi":
                note = result.get("geocode_note") or "POI 검색으로 좌표를 확인했습니다."
                place["_geocode_note"] = note
            else:
                place.pop("_geocode_note", None)
        except TmapGeocodingError as exc:
            place["geocode_error"] = str(exc)
            place["lat"] = None
            place["lng"] = None
            place["normalized_address"] = ""


def add_place() -> None:
    if len(st.session_state.places) >= 10:
        return
    place = create_place()
    st.session_state.places.append(place)
    st.session_state[f"raw_{place['id']}"] = ""
    st.session_state[f"type_{place['id']}"] = place["type"]
    st.session_state[f"res_{place['id']}"] = ""


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
    raw = place.get("raw_input", "").strip()
    place["lat"] = lat
    place["lng"] = lng
    place["normalized_address"] = raw or f"{lat:.5f}, {lng:.5f}"
    place["geocode_error"] = None
    place["_geocoded_for"] = raw
    place["_manual_coords"] = True
    place.pop("_geocode_note", None)
    return None


def delete_place(place_id: str) -> None:
    if len(st.session_state.places) <= 2:
        return
    st.session_state.places = [p for p in st.session_state.places if p["id"] != place_id]
    for key in (f"raw_{place_id}", f"type_{place_id}", f"res_{place_id}"):
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
        raw = place.get("raw_input", "").strip()
        if not raw:
            continue
        if place.get("lat") is None or place.get("lng") is None:
            failed.append(place)
    return failed


def _base_validation_errors() -> list[str]:
    errors: list[str] = []
    region = str(st.session_state.get("travel_region", "")).strip()
    if not region:
        errors.append("여행 지역을 입력하세요.")

    from utils.time_utils import hhmm_to_minutes

    trip_start = str(st.session_state.get("trip_start_time", "")).strip()
    if not hhmm_to_minutes(trip_start):
        errors.append("출발 시각은 HH:MM 형식이어야 합니다.")

    if len(st.session_state.places) < 2:
        errors.append("장소는 최소 2개 이상 필요합니다.")
    return errors


def _place_input_errors(strict_geocode: bool) -> list[str]:
    errors: list[str] = []
    for i, place in enumerate(st.session_state.places):
        raw = place.get("raw_input", "").strip()
        if len(raw) < 2:
            errors.append(f"장소 {i + 1}: 주소를 입력하세요.")
            continue
        ok, msg = validate_address(raw)
        if not ok:
            errors.append(f"장소 {i + 1}: {msg}")
            continue
        if strict_geocode and (place.get("lat") is None or place.get("lng") is None):
            err = place.get("geocode_error") or "좌표 변환 중이거나 실패했습니다."
            errors.append(f"장소 {i + 1}: {err}")
        res_ok, res_msg = validate_reservation_time(place.get("reservation_time"))
        if not res_ok:
            errors.append(f"장소 {i + 1}: {res_msg}")
    return errors


def _route_point_errors(valid_ids: set[str]) -> list[str]:
    errors: list[str] = []
    start_id = st.session_state.get("start_place_id")
    end_id = st.session_state.get("end_place_id")
    if not start_id:
        errors.append("출발지를 선택하세요.")
    elif start_id not in valid_ids:
        errors.append("출발지 좌표가 없습니다. 좌표 변환을 완료하거나 다른 장소를 선택하세요.")
    if not end_id:
        errors.append("도착지를 선택하세요.")
    elif end_id not in valid_ids:
        errors.append("도착지 좌표가 없습니다. 좌표 변환을 완료하거나 다른 장소를 선택하세요.")
    if start_id and end_id and start_id == end_id:
        errors.append("출발지와 도착지는 달라야 합니다.")
    return errors


def validation_errors() -> list[str]:
    errors = _base_validation_errors()
    errors.extend(_place_input_errors(strict_geocode=True))
    valid_ids = {p["id"] for p in geocoded_places()}
    errors.extend(_route_point_errors(valid_ids))
    return errors


def partial_validation_errors() -> list[str]:
    """ER-005 — validate geocoded subset only."""
    errors = _base_validation_errors()
    geocoded = geocoded_places()
    if len(geocoded) < 2:
        errors.append("좌표 변환이 완료된 장소가 2곳 이상 필요합니다.")
    valid_ids = {p["id"] for p in geocoded}
    errors.extend(_route_point_errors(valid_ids))
    for i, place in enumerate(geocoded):
        res_ok, res_msg = validate_reservation_time(place.get("reservation_time"))
        if not res_ok:
            errors.append(f"장소 {i + 1}: {res_msg}")
    return errors


def uses_partial_geocoding() -> bool:
    return bool(failed_geocode_places()) and len(geocoded_places()) >= 2


def can_complete() -> bool:
    if not validation_errors():
        return True
    if uses_partial_geocoding() and not partial_validation_errors():
        return True
    return False


def prepare_optimization_input() -> tuple[list[dict[str, Any]], list[str], list[dict[str, Any]]]:
    """Return (places, warnings, excluded_places) for route optimization."""
    geocoded = geocoded_places()
    excluded = failed_geocode_places()
    warnings: list[str] = []

    if excluded:
        warnings.append(
            f"좌표 변환 실패 {len(excluded)}곳은 제외하고 최적화합니다. (ER-005)"
        )
        for place in excluded:
            addr = place.get("raw_input", "")
            reason = place.get("geocode_error") or "좌표 없음"
            warnings.append(f"· 제외 — {addr}: {reason}")

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
    reserved = sum(1 for p in places if p.get("reservation_time"))
    return {
        "place_count": len(places),
        "geocoded_count": geocoded,
        "reservation_count": reserved,
    }


def place_options() -> list[tuple[str, str]]:
    return [(p["id"], place_label(p, i)) for i, p in enumerate(st.session_state.places)]
