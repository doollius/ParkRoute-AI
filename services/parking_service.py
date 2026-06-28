from __future__ import annotations

from typing import Any

import requests
import streamlit as st

from constants.config import (
    PARKING_CANDIDATES_PER_CLUSTER,
    PARKING_SCORE_DIST_WEIGHT,
    PARKING_SCORE_FEE_WEIGHT,
)
from utils.env_loader import get_env
from utils.geo import haversine_m
from utils.parking_cost import parse_fee, parse_minutes

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
        "unit_fee": item.get("addParkingChrge") or item.get("addRate"),
        "base_time_minutes": parse_minutes(item.get("bscTime"), 30),
        "unit_time_minutes": parse_minutes(item.get("addUnitTime"), 10),
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


def get_parking_candidates(places: list[dict[str, Any]], region: str) -> list[dict[str, Any]]:
    if "parking_candidates_cache" in st.session_state:
        return st.session_state.parking_candidates_cache

    candidates = fetch_public_parking(region_hint=region.strip())
    if not candidates and region.strip():
        candidates = fetch_public_parking(region_hint="")

    if places:
        lats = [p["lat"] for p in places]
        lngs = [p["lng"] for p in places]
        pad = 0.08
        min_lat, max_lat = min(lats) - pad, max(lats) + pad
        min_lng, max_lng = min(lngs) - pad, max(lngs) + pad
        candidates = [
            p
            for p in candidates
            if min_lat <= p["lat"] <= max_lat and min_lng <= p["lng"] <= max_lng
        ]

    st.session_state.parking_candidates_cache = candidates
    return candidates


def score_parking(
    candidate: dict[str, Any],
    center_lat: float,
    center_lng: float,
) -> float:
    """Rules.md §6.2 — lower is better."""
    dist = haversine_m(center_lat, center_lng, candidate["lat"], candidate["lng"])
    fee = parse_fee(candidate.get("base_fee")) or 0
    dist_norm = min(dist, 2000) / 2000
    fee_norm = min(fee, 10000) / 10000
    return dist_norm * PARKING_SCORE_DIST_WEIGHT + fee_norm * PARKING_SCORE_FEE_WEIGHT


def select_parking_for_cluster(
    place_indices: list[int],
    nodes: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    used_ids: set[str],
    get_walk_leg,
) -> dict[str, Any] | None:
    if not candidates or not place_indices:
        return None

    center_lat = sum(nodes[i]["lat"] for i in place_indices) / len(place_indices)
    center_lng = sum(nodes[i]["lng"] for i in place_indices) / len(place_indices)

    ranked = sorted(
        candidates,
        key=lambda p: score_parking(p, center_lat, center_lng),
    )

    for candidate in ranked[:PARKING_CANDIDATES_PER_CLUSTER]:
        if candidate["id"] in used_ids:
            continue
        ok = True
        for idx in place_indices:
            leg = get_walk_leg(candidate["lat"], candidate["lng"], nodes[idx]["lat"], nodes[idx]["lng"])
            if not leg.get("walk_allowed"):
                ok = False
                break
        if ok:
            used_ids.add(candidate["id"])
            return {**candidate, "place_ids": [nodes[i]["id"] for i in place_indices]}
    return None


def pick_parking_for_places(
    place_indices: list[int],
    nodes: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    used_ids: set[str],
    get_walk_leg,
) -> dict[str, Any] | None:
    return select_parking_for_cluster(place_indices, nodes, candidates, used_ids, get_walk_leg)


def assign_parking_to_clusters(
    places: list[dict[str, Any]],
    cluster_indices: list[list[int]],
    region: str,
) -> list[dict[str, Any]]:
    candidates = get_parking_candidates(places, region)
    used_ids: set[str] = set()
    assignments: list[dict[str, Any]] = []

    from services.map_service import get_travel_times

    for indices in cluster_indices:
        if not indices:
            continue
        chosen = pick_parking_for_places(indices, places, candidates, used_ids, get_travel_times)
        if chosen:
            assignments.append(chosen)
    return assignments
