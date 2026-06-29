from __future__ import annotations

from typing import Any, Callable

import streamlit as st

from api.kakao_api import KakaoApiError, search_parking_near
from constants.config import (
    KAKAO_HUB_CANDIDATES_PER_GROUP,
    KAKAO_PARKING_MAX_DISTANCE_M,
    KAKAO_PARKING_PER_POI_LIMIT,
    KAKAO_PARKING_PER_POI_RADIUS_M,
    KAKAO_PARKING_SEARCH_RADIUS_M,
    KAKAO_PUBLIC_NAME_BONUS,
    PARKING_CANDIDATES_PER_CLUSTER,
    PARKING_NEARBY_RADIUS_M,
    PARKING_SCORE_DIST_WEIGHT,
    PARKING_SCORE_FEE_WEIGHT,
    PARKING_TMAP_VALIDATE_LIMIT,
)
from utils.geo import haversine_m
from utils.parking_cost import parse_fee
from utils.walk_limits import walk_leg_ok_distance

# POI별 카카오 검색 + 겹침 인덱스
ParkingCoverage = dict[str, Any]


def trip_centroid(places: list[dict[str, Any]]) -> tuple[float, float] | None:
    """방문 장소들의 중심 좌표 (진단 스크립트 등)."""
    if not places:
        return None
    lat = sum(p["lat"] for p in places) / len(places)
    lng = sum(p["lng"] for p in places) / len(places)
    return lat, lng


def fetch_kakao_parking_for_poi(lat: float, lng: float) -> list[dict[str, Any]]:
    """POI 좌표 기준 카카오 PK6 — 반경 1km, 상위 20건."""
    try:
        return search_parking_near(
            lat,
            lng,
            radius_m=KAKAO_PARKING_PER_POI_RADIUS_M,
            max_distance_m=KAKAO_PARKING_PER_POI_RADIUS_M,
            max_results=KAKAO_PARKING_PER_POI_LIMIT,
        )
    except KakaoApiError:
        return []


def fetch_kakao_parking(
    center_lat: float,
    center_lng: float,
    *,
    radius_m: int = KAKAO_PARKING_SEARCH_RADIUS_M,
) -> list[dict[str, Any]]:
    """(legacy) 중심 좌표 반경 검색 — 진단 스크립트용."""
    try:
        return search_parking_near(
            center_lat,
            center_lng,
            radius_m=radius_m,
            max_distance_m=KAKAO_PARKING_MAX_DISTANCE_M,
        )
    except KakaoApiError:
        return []


def build_parking_coverage(
    places: list[dict[str, Any]],
    on_progress: Callable[[str], None] | None = None,
) -> ParkingCoverage:
    """
    POI마다 카카오 주차장 상위 N건 조회 후 겹침 인덱스 구축.
    by_id[parking_id] = {parking, poi_indices: set[int]}
    """
    per_poi: list[list[dict[str, Any]]] = []
    by_id: dict[str, dict[str, Any]] = {}
    total = len(places)

    for poi_idx, place in enumerate(places):
        if on_progress and total:
            on_progress(f"2/4 POI별 주차장 검색 ({poi_idx + 1}/{total})…")
        parks = fetch_kakao_parking_for_poi(place["lat"], place["lng"])
        per_poi.append(parks)
        for p in parks:
            pid = p["id"]
            if pid not in by_id:
                by_id[pid] = {"parking": dict(p), "poi_indices": set()}
            by_id[pid]["poi_indices"].add(poi_idx)
            if p.get("distance_m", 0) < by_id[pid]["parking"].get("distance_m", 999_999):
                by_id[pid]["parking"] = dict(p)

    union = [entry["parking"] for entry in by_id.values()]
    return {"per_poi": per_poi, "by_id": by_id, "union": union}


def get_parking_coverage(
    places: list[dict[str, Any]],
    on_progress: Callable[[str], None] | None = None,
) -> ParkingCoverage:
    if "parking_coverage_cache" in st.session_state:
        return st.session_state.parking_coverage_cache

    coverage = build_parking_coverage(places, on_progress=on_progress)
    st.session_state.parking_coverage_cache = coverage
    st.session_state.parking_candidates_cache = coverage["union"]
    return coverage


def get_parking_candidates(places: list[dict[str, Any]], region: str = "") -> list[dict[str, Any]]:
    """전체 후보(POI별 검색 합집합). region은 하위 호환용."""
    del region
    return get_parking_coverage(places)["union"]


def tmap_parking_validate_limit(place_count: int) -> int:
    n = max(2, place_count)
    return min(PARKING_TMAP_VALIDATE_LIMIT, max(6, 2 + n))


def shared_hub_candidates(
    poi_indices: list[int],
    coverage: ParkingCoverage,
    *,
    limit: int = KAKAO_HUB_CANDIDATES_PER_GROUP,
) -> list[dict[str, Any]]:
    """클러스터 POI 전원의 카카오 목록에 공통 등장하는 주차장 (겹침 상위)."""
    if not poi_indices:
        return []
    idx_set = set(poi_indices)
    hits: list[tuple[int, float, dict[str, Any]]] = []

    for entry in coverage.get("by_id", {}).values():
        covered: set[int] = entry["poi_indices"]
        if not idx_set <= covered:
            continue
        parking = entry["parking"]
        overlap = len(idx_set)
        hits.append((overlap, -parking.get("distance_m", 0), parking))

    hits.sort(key=lambda row: (-row[0], row[1]))
    seen: set[str] = set()
    result: list[dict[str, Any]] = []
    for _, _, parking in hits:
        if parking["id"] in seen:
            continue
        seen.add(parking["id"])
        result.append(parking)
        if len(result) >= limit:
            break
    return result


def score_parking(
    candidate: dict[str, Any],
    center_lat: float,
    center_lng: float,
) -> float:
    """낮을수록 좋음 — 거리 우선, 공영주차장 이름 가산."""
    dist = haversine_m(center_lat, center_lng, candidate["lat"], candidate["lng"])
    fee = parse_fee(candidate.get("base_fee")) or 0
    dist_norm = min(dist, KAKAO_PARKING_PER_POI_RADIUS_M) / KAKAO_PARKING_PER_POI_RADIUS_M
    fee_norm = min(fee, 10000) / 10000
    score = dist_norm * PARKING_SCORE_DIST_WEIGHT + fee_norm * PARKING_SCORE_FEE_WEIGHT
    if candidate.get("type") == "공영" or "공영" in (candidate.get("name") or ""):
        score -= KAKAO_PUBLIC_NAME_BONUS
    return score


def pick_hub_for_cluster(
    poi_indices: list[int],
    nodes: list[dict[str, Any]],
    coverage: ParkingCoverage,
    used_ids: set[str],
    get_walk_leg: Callable[..., dict[str, Any]],
    *,
    parking_mode: bool = False,
) -> dict[str, Any] | None:
    """겹치는 hub 후보 상위 N개 중 TMAP(또는 직선) 검증 후 1곳 선택."""
    if not poi_indices:
        return None

    center_lat = sum(nodes[i]["lat"] for i in poi_indices) / len(poi_indices)
    center_lng = sum(nodes[i]["lng"] for i in poi_indices) / len(poi_indices)

    hubs = shared_hub_candidates(poi_indices, coverage)
    ranked = sorted(hubs, key=lambda p: score_parking(p, center_lat, center_lng))

    for candidate in ranked[:KAKAO_HUB_CANDIDATES_PER_GROUP]:
        if candidate["id"] in used_ids:
            continue
        if parking_mode:
            ok = True
            for idx in poi_indices:
                leg = get_walk_leg(
                    candidate["lat"],
                    candidate["lng"],
                    nodes[idx]["lat"],
                    nodes[idx]["lng"],
                    walk_only=True,
                )
                if not walk_leg_ok_distance(leg):
                    ok = False
                    break
            if ok:
                used_ids.add(candidate["id"])
                return {**candidate, "place_ids": [nodes[i]["id"] for i in poi_indices]}
        else:
            ok = all(
                haversine_m(
                    candidate["lat"],
                    candidate["lng"],
                    nodes[idx]["lat"],
                    nodes[idx]["lng"],
                )
                <= PARKING_NEARBY_RADIUS_M
                for idx in poi_indices
            )
            if ok:
                used_ids.add(candidate["id"])
                return {**candidate, "place_ids": [nodes[i]["id"] for i in poi_indices]}

    return None


def find_nearby_parking(
    lat: float,
    lng: float,
    candidates: list[dict[str, Any]],
    limit: int = 3,
    max_radius_m: float = 2000,
) -> list[dict[str, Any]]:
    scored: list[tuple[float, dict[str, Any]]] = []
    for p in candidates:
        dist = p.get("distance_m")
        if dist is None:
            dist = int(haversine_m(lat, lng, p["lat"], p["lng"]))
        if dist <= max_radius_m:
            scored.append((dist, {**p, "distance_m": int(dist)}))
    scored.sort(key=lambda x: x[0])
    return [p for _, p in scored[:limit]]


def select_parking_for_cluster(
    place_indices: list[int],
    nodes: list[dict[str, Any]],
    candidates: list[dict[str, Any]],
    used_ids: set[str],
    get_walk_leg,
    coverage: ParkingCoverage | None = None,
) -> dict[str, Any] | None:
    if coverage:
        hub = pick_hub_for_cluster(
            place_indices, nodes, coverage, used_ids, get_walk_leg, parking_mode=False
        )
        if hub:
            return hub

    if not candidates or not place_indices:
        return None

    center_lat = sum(nodes[i]["lat"] for i in place_indices) / len(place_indices)
    center_lng = sum(nodes[i]["lng"] for i in place_indices) / len(place_indices)
    ranked = sorted(candidates, key=lambda p: score_parking(p, center_lat, center_lng))

    for candidate in ranked[:PARKING_CANDIDATES_PER_CLUSTER]:
        if candidate["id"] in used_ids:
            continue
        ok = all(
            haversine_m(
                candidate["lat"],
                candidate["lng"],
                nodes[idx]["lat"],
                nodes[idx]["lng"],
            )
            <= PARKING_NEARBY_RADIUS_M
            for idx in place_indices
        )
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
    coverage: ParkingCoverage | None = None,
) -> dict[str, Any] | None:
    return select_parking_for_cluster(
        place_indices, nodes, candidates, used_ids, get_walk_leg, coverage=coverage
    )


def assign_parking_to_clusters(
    places: list[dict[str, Any]],
    cluster_indices: list[list[int]],
    region: str,
) -> list[dict[str, Any]]:
    coverage = get_parking_coverage(places)
    candidates = coverage["union"]
    used_ids: set[str] = set()
    assignments: list[dict[str, Any]] = []

    from services.map_service import get_travel_times

    for indices in cluster_indices:
        if not indices:
            continue
        chosen = pick_parking_for_places(
            indices, places, candidates, used_ids, get_travel_times, coverage=coverage
        )
        if chosen:
            assignments.append(chosen)
    return assignments
