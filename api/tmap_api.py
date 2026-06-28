from __future__ import annotations

from typing import Any

import requests

from utils.env_loader import get_env


class TmapApiError(Exception):
    pass


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
    }


def get_car_route(start_lng: float, start_lat: float, end_lng: float, end_lat: float) -> dict[str, int]:
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
