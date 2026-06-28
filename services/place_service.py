from __future__ import annotations

from typing import Any

import streamlit as st

from api.tmap_api import TmapGeocodingError, geocode_address
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
            result = geocode_address(raw)
            place["lat"] = result["lat"]
            place["lng"] = result["lng"]
            place["normalized_address"] = result["normalized_address"]
            place["geocode_error"] = None
            place["_geocoded_for"] = raw
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


def validation_errors() -> list[str]:
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

    for i, place in enumerate(st.session_state.places):
        raw = place.get("raw_input", "").strip()
        if len(raw) < 2:
            errors.append(f"장소 {i + 1}: 주소를 입력하세요.")
            continue
        ok, msg = validate_address(raw)
        if not ok:
            errors.append(f"장소 {i + 1}: {msg}")
            continue
        if place.get("lat") is None or place.get("lng") is None:
            err = place.get("geocode_error") or "좌표 변환 중이거나 실패했습니다."
            errors.append(f"장소 {i + 1}: {err}")
        res_ok, res_msg = validate_reservation_time(place.get("reservation_time"))
        if not res_ok:
            errors.append(f"장소 {i + 1}: {res_msg}")

    start_id = st.session_state.get("start_place_id")
    end_id = st.session_state.get("end_place_id")
    if not start_id:
        errors.append("출발지를 선택하세요.")
    if not end_id:
        errors.append("도착지를 선택하세요.")
    if start_id and end_id and start_id == end_id:
        errors.append("출발지와 도착지는 달라야 합니다.")

    return errors


def can_complete() -> bool:
    return len(validation_errors()) == 0


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
