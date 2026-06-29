from __future__ import annotations

from typing import Any

import streamlit as st

from api.kakao_api import KakaoApiError, search_parking_near
from constants.config import (
    KAKAO_PARKING_MAX_DISTANCE_M,
    KAKAO_PARKING_SEARCH_RADIUS_M,
    KAKAO_PUBLIC_NAME_BONUS,
    PARKING_CANDIDATES_PER_CLUSTER,
    PARKING_NEARBY_RADIUS_M,
    PARKING_SCORE_DIST_WEIGHT,
    PARKING_SCORE_FEE_WEIGHT,
    PARKING_TMAP_CANDIDATE_LIMIT,
)
from utils.geo import haversine_m
from utils.parking_cost import parse_fee


def trip_centroid(places: list[dict[str, Any]]) -> tuple[float, float] | None:
    """방문 장소들의 중심 좌표 (여행 범위 기준 주차장 검색용)."""
    if not places:
        return None
    lat = sum(p["lat"] for p in places) / len(places)
    lng = sum(p["lng"] for p in places) / len(places)
    return lat, lng


def fetch_kakao_parking(
    center_lat: float,
    center_lng: float,
    *,
    radius_m: int = KAKAO_PARKING_SEARCH_RADIUS_M,
) -> list[dict[str, Any]]:
    """카카오 Local PK6 — 중심 좌표 반경 주차장 검색."""
    try:
        return search_parking_near(
            center_lat,
            center_lng,
            radius_m=radius_m,
            max_distance_m=KAKAO_PARKING_MAX_DISTANCE_M,
        )
    except KakaoApiError:
        return []


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


def get_parking_candidates(places: list[dict[str, Any]], region: str = "") -> list[dict[str, Any]]:
    """
    여행 전체 범위 기준 주차장 후보.
    1) 방문지 중심 좌표 계산
    2) 카카오 PK6 반경 검색 (기본 2km)
    region 인자는 하위 호환용 (미사용).
    """
    del region  # legacy — Kakao는 좌표 반경 검색

    if "parking_candidates_cache" in st.session_state:
        return st.session_state.parking_candidates_cache

    center = trip_centroid(places)
    if not center:
        st.session_state.parking_candidates_cache = []
        return []

    center_lat, center_lng = center
    candidates = fetch_kakao_parking(center_lat, center_lng)

    st.session_state.parking_candidates_cache = candidates
    return candidates


def candidates_for_tmap_matching(candidates: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """TMAP 도보 정밀 검사 대상 — 중심에서 가까운 상위 N개만."""
    if not candidates:
        return []
    ranked = sorted(candidates, key=lambda p: p.get("distance_m", 999_999))
    return ranked[:PARKING_TMAP_CANDIDATE_LIMIT]


def score_parking(
    candidate: dict[str, Any],
    center_lat: float,
    center_lng: float,
) -> float:
    """낮을수록 좋음 — 거리 우선, 공영주차장 이름 가산."""
    dist = candidate.get("distance_m")
    if dist is None:
        dist = haversine_m(center_lat, center_lng, candidate["lat"], candidate["lng"])
    fee = parse_fee(candidate.get("base_fee")) or 0
    dist_norm = min(dist, KAKAO_PARKING_SEARCH_RADIUS_M) / KAKAO_PARKING_SEARCH_RADIUS_M
    fee_norm = min(fee, 10000) / 10000
    score = dist_norm * PARKING_SCORE_DIST_WEIGHT + fee_norm * PARKING_SCORE_FEE_WEIGHT
    if candidate.get("type") == "공영" or "공영" in (candidate.get("name") or ""):
        score -= KAKAO_PUBLIC_NAME_BONUS
    return score


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
            dist = haversine_m(
                candidate["lat"],
                candidate["lng"],
                nodes[idx]["lat"],
                nodes[idx]["lng"],
            )
            if dist > PARKING_NEARBY_RADIUS_M:
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
