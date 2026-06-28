from __future__ import annotations

from typing import Any

import requests

from utils.env_loader import get_env
from utils.geo import haversine_m

PARKING_API_URL = "https://api.data.go.kr/openapi/tn_pubr_prkplce_info_api"


def _parse_float(value: Any) -> float | None:
    if value in (None, "", " "):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_item(item: dict[str, Any]) -> dict[str, Any] | None:
    lat = _parse_float(item.get("latitude") or item.get("lat"))
    lng = _parse_float(item.get("longitude") or item.get("lot") or item.get("lng"))
    if lat is None or lng is None:
        return None
    return {
        "id": str(item.get("prkplceNo") or item.get("prkplceNm") or f"{lat},{lng}"),
        "name": item.get("prkplceNm") or "공영주차장",
        "address": item.get("rdnmadr") or item.get("lnmadr") or "",
        "type": item.get("prkplceSe") or "공영",
        "lat": lat,
        "lng": lng,
        "capacity": item.get("prkcmprt") or item.get("parkingSpace"),
        "base_fee": item.get("bscParkingChrge") or item.get("baseRate"),
    }


def fetch_public_parking(region_hint: str = "", max_pages: int = 2, page_size: int = 200) -> list[dict[str, Any]]:
    key = get_env("DATA_GO_KR_SERVICE_KEY")
    if not key:
        return []

    results: list[dict[str, Any]] = []
    for page in range(1, max_pages + 1):
        try:
            resp = requests.get(
                PARKING_API_URL,
                params={
                    "serviceKey": key,
                    "pageNo": page,
                    "numOfRows": page_size,
                    "type": "json",
                    "prkplceSe": "공영",
                },
                timeout=15,
            )
            data = resp.json()
        except requests.RequestException:
            break
        code = data.get("response", {}).get("header", {}).get("resultCode")
        if code != "00":
            break
        items = data.get("response", {}).get("body", {}).get("items", [])
        if isinstance(items, dict):
            items = [items]
        if not items:
            break
        for item in items:
            parsed = _normalize_item(item)
            if not parsed:
                continue
            if region_hint and region_hint not in (parsed["address"] or ""):
                continue
            results.append(parsed)
    return results


def find_nearby_parking(
    lat: float,
    lng: float,
    candidates: list[dict[str, Any]],
    limit: int = 3,
    max_radius_m: float = 2000,
) -> list[dict[str, Any]]:
    scored: list[tuple[float, dict[str, Any]]] = []
    for p in candidates:
        dist = haversine_m(lat, lng, p["lat"], p["lng"])
        if dist <= max_radius_m:
            scored.append((dist, {**p, "distance_m": int(dist)}))
    scored.sort(key=lambda x: x[0])
    return [p for _, p in scored[:limit]]


def assign_parking_to_clusters(
    places: list[dict[str, Any]],
    cluster_indices: list[list[int]],
    region: str,
) -> list[dict[str, Any]]:
    region_key = region.strip()
    all_parking = fetch_public_parking(region_hint=region_key)
    if not all_parking and region_key:
        all_parking = fetch_public_parking(region_hint="")

    # Bbox filter when region fetch returns too few
    if places and len(all_parking) > 50:
        lats = [p["lat"] for p in places]
        lngs = [p["lng"] for p in places]
        pad = 0.05
        min_lat, max_lat = min(lats) - pad, max(lats) + pad
        min_lng, max_lng = min(lngs) - pad, max(lngs) + pad
        all_parking = [
            p
            for p in all_parking
            if min_lat <= p["lat"] <= max_lat and min_lng <= p["lng"] <= max_lng
        ]

    assignments: list[dict[str, Any]] = []
    used_ids: set[str] = set()

    for indices in cluster_indices:
        if not indices:
            continue
        pts = [places[i] for i in indices]
        center_lat = sum(p["lat"] for p in pts) / len(pts)
        center_lng = sum(p["lng"] for p in pts) / len(pts)
        nearby = find_nearby_parking(center_lat, center_lng, all_parking, limit=5)
        chosen = None
        for candidate in nearby:
            if candidate["id"] not in used_ids:
                chosen = candidate
                used_ids.add(candidate["id"])
                break
        if chosen:
            assignments.append(
                {
                    **chosen,
                    "place_ids": [places[i]["id"] for i in indices],
                }
            )
    return assignments
