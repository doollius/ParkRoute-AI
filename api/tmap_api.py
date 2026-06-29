from __future__ import annotations

import logging
import time
from typing import Any

import requests

from constants.config import (
    TMAP_REQUEST_DELAY_SEC,
    TMAP_ROUTE_MAX_RETRIES,
    TMAP_ROUTE_RETRY_BASE_SEC,
)
from utils.env_loader import get_env
from utils.geo import is_trivial_route, prepare_route_coords, zero_route_metrics
from utils.poi_category import normalize_biz_name

logger = logging.getLogger(__name__)


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
    _raise_if_tmap_error_payload(data)
    for feature in data.get("features", []):
        props = feature.get("properties", {})
        if props.get("totalTime") is not None:
            return {
                "time_sec": int(props["totalTime"]),
                "distance_m": int(props.get("totalDistance") or 0),
            }
    raise TmapApiError(_format_tmap_error_message(data, "경로 정보를 찾을 수 없습니다."))


def _raise_if_tmap_error_payload(data: dict[str, Any]) -> None:
    err = data.get("error")
    if isinstance(err, dict):
        code = err.get("code") or err.get("id") or ""
        msg = err.get("message") or err.get("detail") or str(err)
        raise TmapApiError(f"TMAP 오류 ({code}): {msg}".strip())
    error_code = data.get("errorCode") or data.get("errorId")
    error_msg = data.get("errorMessage") or data.get("errorMsg")
    if error_code or error_msg:
        raise TmapApiError(f"TMAP 오류 ({error_code or 'unknown'}): {error_msg or error_code}")


def _format_tmap_error_message(data: dict[str, Any], fallback: str) -> str:
    try:
        _raise_if_tmap_error_payload(data)
    except TmapApiError as exc:
        return str(exc)
    return fallback


def _log_route_request(
    mode: str,
    start_lat: float,
    start_lng: float,
    end_lat: float,
    end_lng: float,
    body: dict[str, Any],
) -> None:
    if get_env("TMAP_DEBUG", "").lower() in ("1", "true", "yes"):
        logger.warning(
            "TMAP %s route request start=(%.6f,%.6f) end=(%.6f,%.6f) body=%s",
            mode,
            start_lat,
            start_lng,
            end_lat,
            end_lng,
            body,
        )


def _post_route(
    url: str,
    body: dict[str, Any],
    *,
    mode: str,
    start_lat: float,
    start_lng: float,
    end_lat: float,
    end_lng: float,
) -> dict[str, int]:
    _log_route_request(mode, start_lat, start_lng, end_lat, end_lng, body)
    last_error: TmapApiError | None = None

    for attempt in range(TMAP_ROUTE_MAX_RETRIES):
        _throttle_route_request()
        resp = requests.post(
            url,
            params={"version": "1", "format": "json"},
            headers=_headers(),
            json=body,
            timeout=20,
        )

        if resp.status_code == 429:
            wait = TMAP_ROUTE_RETRY_BASE_SEC * (2**attempt)
            logger.warning("TMAP %s route HTTP 429 — %.1fs 후 재시도 (%d/%d)", mode, wait, attempt + 1, TMAP_ROUTE_MAX_RETRIES)
            time.sleep(wait)
            last_error = TmapApiError(f"{mode} 경로 실패 (HTTP 429)")
            continue

        if resp.status_code >= 500:
            wait = TMAP_ROUTE_RETRY_BASE_SEC * (2**attempt)
            logger.warning(
                "TMAP %s route HTTP %s — %.1fs 후 재시도 (%d/%d)",
                mode,
                resp.status_code,
                wait,
                attempt + 1,
                TMAP_ROUTE_MAX_RETRIES,
            )
            time.sleep(wait)
            last_error = TmapApiError(f"{mode} 경로 실패 (HTTP {resp.status_code})")
            continue

        if resp.status_code != 200:
            detail = resp.text[:300] if resp.text else ""
            raise TmapApiError(f"{mode} 경로 실패 (HTTP {resp.status_code}): {detail}")

        try:
            data = resp.json()
        except ValueError as exc:
            raise TmapApiError(f"{mode} 경로 응답 파싱 실패") from exc

        if get_env("TMAP_DEBUG", "").lower() in ("1", "true", "yes"):
            logger.warning("TMAP %s route response: %s", mode, str(data)[:500])

        return _extract_route_metrics(data)

    raise last_error or TmapApiError(f"{mode} 경로 실패 (재시도 초과)")


def _route_body(start_lng: float, start_lat: float, end_lng: float, end_lat: float, *, pedestrian: bool) -> dict[str, Any]:
    body: dict[str, Any] = {
        "startX": start_lng,
        "startY": start_lat,
        "endX": end_lng,
        "endY": end_lat,
        "reqCoordType": "WGS84GEO",
        "resCoordType": "WGS84GEO",
        "searchOption": "0",
    }
    if pedestrian:
        body["startName"] = "start"
        body["endName"] = "end"
    return body


def _get_route(
    start_lat: float,
    start_lng: float,
    end_lat: float,
    end_lng: float,
    *,
    mode: str,
    url: str,
    pedestrian: bool,
) -> dict[str, int]:
    s_lat, s_lng, e_lat, e_lng, invalid_reason = prepare_route_coords(
        start_lat, start_lng, end_lat, end_lng
    )
    if invalid_reason:
        raise TmapApiError(invalid_reason)

    if is_trivial_route(s_lat, s_lng, e_lat, e_lng):
        return zero_route_metrics()

    body = _route_body(s_lng, s_lat, e_lng, e_lat, pedestrian=pedestrian)
    return _post_route(
        url,
        body,
        mode=mode,
        start_lat=s_lat,
        start_lng=s_lng,
        end_lat=e_lat,
        end_lng=e_lng,
    )


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
    return _get_route(
        start_lat,
        start_lng,
        end_lat,
        end_lng,
        mode="car",
        url="https://apis.openapi.sk.com/tmap/routes",
        pedestrian=False,
    )


def get_walk_route(start_lng: float, start_lat: float, end_lng: float, end_lat: float) -> dict[str, int]:
    return _get_route(
        start_lat,
        start_lng,
        end_lat,
        end_lng,
        mode="walk",
        url="https://apis.openapi.sk.com/tmap/routes/pedestrian",
        pedestrian=True,
    )


# Backward compatibility
TmapGeocodingError = TmapApiError
