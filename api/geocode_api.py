from __future__ import annotations

import hashlib
from typing import Any, Literal

import streamlit as st

from api.tmap_api import TmapApiError, geocode_address, search_pois
from utils.address_validator import validate_address

ResolveStatus = Literal["confirmed", "pick", "failed"]


def _cache() -> dict[str, dict[str, Any]]:
    if "geocode_cache" not in st.session_state:
        st.session_state.geocode_cache = {}
    return st.session_state.geocode_cache


def _cache_key(address: str) -> str:
    return hashlib.sha256(address.strip().encode("utf-8")).hexdigest()


def resolve_address(address: str) -> dict[str, Any]:
    """Geocoding with session cache and POI search fallback."""
    key = _cache_key(address)
    cached = _cache().get(key)
    if cached:
        return dict(cached)

    try:
        result = geocode_address(address)
        result["source"] = "geocoding"
    except TmapApiError as geo_exc:
        try:
            pois = search_pois(address, count=1)
            if not pois:
                raise TmapApiError("POI 검색 결과가 없습니다.") from geo_exc
            poi = pois[0]
            result = {
                "lat": poi["lat"],
                "lng": poi["lng"],
                "normalized_address": poi["normalized_address"],
                "source": "poi",
                "geocode_note": f"주소 검색 실패 → POI 검색 사용 ({geo_exc})",
            }
        except TmapApiError as poi_exc:
            raise TmapApiError(f"좌표 변환 실패: {geo_exc} / POI: {poi_exc}") from poi_exc

    _cache()[key] = result
    return dict(result)


def resolve_place_query(query: str, *, max_candidates: int = 5) -> dict[str, Any]:
    """
    장소명·주소·상호명 통합 검색.
    Returns:
      status: confirmed | pick | failed
      candidates: list (pick 시)
      result: dict with lat, lng, normalized_address, matched_name (confirmed 시)
      error: str (failed 시)
    """
    text = query.strip()
    if not text:
        return {"status": "failed", "error": "검색어가 비어 있습니다."}

    addr_ok, _ = validate_address(text)
    if addr_ok:
        try:
            result = resolve_address(text)
            return {
                "status": "confirmed",
                "result": {
                    "lat": result["lat"],
                    "lng": result["lng"],
                    "normalized_address": result["normalized_address"],
                    "matched_name": result["normalized_address"],
                },
            }
        except TmapApiError as exc:
            return {"status": "failed", "error": str(exc)}

    try:
        pois = search_pois(text, count=max_candidates)
    except TmapApiError as exc:
        return {"status": "failed", "error": str(exc)}

    if not pois:
        return {"status": "failed", "error": "검색 결과가 없습니다. 장소명을 다시 확인해 주세요."}
    if len(pois) == 1:
        poi = pois[0]
        return {
            "status": "confirmed",
            "result": {
                "lat": poi["lat"],
                "lng": poi["lng"],
                "normalized_address": poi["normalized_address"],
                "matched_name": poi["name"],
            },
        }
    return {"status": "pick", "candidates": pois}
