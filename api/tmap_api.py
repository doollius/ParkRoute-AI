from __future__ import annotations

import time
from typing import Any

import requests

from constants.config import TMAP_REQUEST_DELAY_SEC
from utils.env_loader import get_env
from utils.poi_category import normalize_biz_name


class TmapApiError(Exception):
    pass


_last_route_request_at: float = 0.0


def _throttle_route_request() -> None:
    """경로 API 연속 호출 간 최소 간격 유지 (HTTP 429 완화)."""
    global _last_route_request_at
    if TMAP_REQUEST_DELAY_SEC <= 0:
        return
    now = time.monotonic()
    wait = TMAP_REQUEST_DELAY_SEC - (now - _last_route_request_at)
    if wait > 0:
        time.sleep(wait)
    _last_route_request_at = time.monotonic()


def _headers() -> dict[str, str]:
    key = get_env("TMAP_APP_KEY")
    if not key:
        raise TmapApiError("TMAP_APP_KEY가 설정되지 않았습니다.")
    return {
        "appKey": key,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }


def _extract_route_metrics(data: dict[str, Any]) -> dict[str, int]:
    for feature in data.get("features", []):
        props = feature.get("properties", {})
        if props.get("totalTime") is not None:
            return {
                "time_sec": int(props["totalTime"]),
                "distance_m": int(props.get("totalDistance") or 0),
            }
    raise TmapApiError("경로 정보를 찾을 수 없습니다.")


def geocode_address(address: str) -> dict[str, Any]:
    """TMAP fullAddrGeo: 주소 → 좌표."""
    resp = requests.get(
        "https://apis.openapi.sk.com/tmap/geo/fullAddrGeo",
        params={
            "version": "1",
            "format": "json",
            "fullAddr": address.strip(),
            "coordType": "WGS84GEO",
        },
        headers=_headers(),
        timeout=15,
    )
    if resp.status_code != 200:
        raise TmapApiError(f"TMAP Geocoding 실패 (HTTP {resp.status_code})")

    data = resp.json()
    coords = data.get("coordinateInfo", {}).get("coordinate", [])
    if not coords:
        raise TmapApiError("좌표를 찾을 수 없습니다.")

    row = coords[0]
    lat = row.get("newLat") or row.get("lat")
    lon = row.get("newLon") or row.get("lon")
    if not lat or not lon:
        raise TmapApiError("유효한 좌표가 반환되지 않았습니다.")

    road = (row.get("newRoadName") or "").strip()
    building = (row.get("newBuildingIndex") or "").strip()
    city = (row.get("city_do") or "").strip()
    gu = (row.get("gu_gun") or "").strip()
    normalized_parts = [p for p in [city, gu, road, building] if p]
    normalized = " ".join(normalized_parts) if normalized_parts else address.strip()

    return {
        "lat": float(lat),
        "lng": float(lon),
        "normalized_address": normalized,
        "poi_category": address.strip(),
    }


def _parse_poi_row(poi: dict[str, Any], fallback_name: str = "") -> dict[str, Any] | None:
    lat = poi.get("frontLat") or poi.get("noorLat")
    lon = poi.get("frontLon") or poi.get("noorLon")
    if not lat or not lon:
        return None

    name = (poi.get("name") or fallback_name).strip()
    road = None
    new_addr = poi.get("newAddressList")
    if isinstance(new_addr, dict):
        rows = new_addr.get("newAddress", [])
        if isinstance(rows, dict):
            rows = [rows]
        if rows:
            road = (rows[0].get("fullAddressStreet") or "").strip()
    if not road:
        road = " ".join(
            p
            for p in [
                poi.get("upperAddrName") or "",
                poi.get("middleAddrName") or "",
                poi.get("lowerAddrName") or "",
            ]
            if p
        ).strip()
    normalized = road or name

    middle_biz = normalize_biz_name(poi.get("middleBizName"))
    lower_biz = normalize_biz_name(poi.get("lowerBizName"))
    category_parts = [
        poi.get("upperBizName") or "",
        middle_biz,
        lower_biz,
        poi.get("bizName") or "",
        poi.get("className") or "",
    ]
    poi_category = " ".join(p for p in category_parts if p).strip() or name

    return {
        "name": name,
        "lat": float(lat),
        "lng": float(lon),
        "normalized_address": normalized,
        "poi_category": poi_category,
        "middle_biz_name": middle_biz,
        "lower_biz_name": lower_biz,
    }


def search_pois(keyword: str, count: int = 5) -> list[dict[str, Any]]:
    """TMAP POI 검색 — 최대 count개 후보 반환."""
    resp = requests.get(
        "https://apis.openapi.sk.com/tmap/pois",
        params={
            "version": "1",
            "searchKeyword": keyword.strip(),
            "count": max(1, min(count, 10)),
            "reqCoordType": "WGS84GEO",
            "resCoordType": "WGS84GEO",
        },
        headers={"appKey": get_env("TMAP_APP_KEY"), "Accept": "application/json"},
        timeout=15,
    )
    if resp.status_code != 200:
        raise TmapApiError(f"TMAP POI 검색 실패 (HTTP {resp.status_code})")

    data = resp.json()
    pois = data.get("searchPoiInfo", {}).get("pois", {}).get("poi", [])
    if isinstance(pois, dict):
        pois = [pois]
    if not pois:
        return []

    results: list[dict[str, Any]] = []
    for poi in pois:
        parsed = _parse_poi_row(poi, keyword)
        if parsed:
            results.append(parsed)
    return results


def search_poi(keyword: str, count: int = 1) -> dict[str, Any]:
    """TMAP POI search fallback when fullAddrGeo fails."""
    results = search_pois(keyword, count=count)
    if not results:
        raise TmapApiError("POI 검색 결과가 없습니다.")
    first = results[0]
    return {
        "lat": first["lat"],
        "lng": first["lng"],
        "normalized_address": first["normalized_address"],
    }


def get_car_route(start_lng: float, start_lat: float, end_lng: float, end_lat: float) -> dict[str, int]:
    _throttle_route_request()
    resp = requests.post(
        "https://apis.openapi.sk.com/tmap/routes",
        params={"version": "1", "format": "json"},
        headers=_headers(),
        json={
            "startX": start_lng,
            "startY": start_lat,
            "endX": end_lng,
            "endY": end_lat,
            "reqCoordType": "WGS84GEO",
            "resCoordType": "WGS84GEO",
            "searchOption": "0",
        },
        timeout=20,
    )
    if resp.status_code != 200:
        raise TmapApiError(f"차량 경로 실패 (HTTP {resp.status_code})")
    return _extract_route_metrics(resp.json())


def get_walk_route(start_lng: float, start_lat: float, end_lng: float, end_lat: float) -> dict[str, int]:
    _throttle_route_request()
    resp = requests.post(
        "https://apis.openapi.sk.com/tmap/routes/pedestrian",
        params={"version": "1", "format": "json"},
        headers=_headers(),
        json={
            "startX": start_lng,
            "startY": start_lat,
            "endX": end_lng,
            "endY": end_lat,
            "reqCoordType": "WGS84GEO",
            "resCoordType": "WGS84GEO",
            "searchOption": "0",
            "startName": "start",
            "endName": "end",
        },
        timeout=20,
    )
    if resp.status_code != 200:
        raise TmapApiError(f"보행 경로 실패 (HTTP {resp.status_code})")
    return _extract_route_metrics(resp.json())


# Backward compatibility
TmapGeocodingError = TmapApiError
