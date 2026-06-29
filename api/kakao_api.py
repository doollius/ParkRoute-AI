from __future__ import annotations

from typing import Any

import requests

from constants.config import (
    KAKAO_PARKING_CATEGORY_CODE,
    KAKAO_PARKING_MAX_RESULTS,
    KAKAO_PARKING_PAGE_SIZE,
)
from utils.env_loader import get_env

KAKAO_CATEGORY_SEARCH_URL = "https://dapi.kakao.com/v2/local/search/category.json"


class KakaoApiError(Exception):
    pass


def _headers() -> dict[str, str]:
    key = get_env("KAKAO_REST_API_KEY")
    if not key:
        raise KakaoApiError("KAKAO_REST_API_KEY가 설정되지 않았습니다.")
    return {"Authorization": f"KakaoAK {key}"}


def _normalize_document(doc: dict[str, Any]) -> dict[str, Any] | None:
    try:
        lat = float(doc["y"])
        lng = float(doc["x"])
    except (KeyError, TypeError, ValueError):
        return None

    name = (doc.get("place_name") or "").strip() or "주차장"
    category = (doc.get("category_name") or "주차장").strip()
    is_public = "공영" in name or "공영" in category

    try:
        distance_m = int(doc.get("distance") or 0)
    except (TypeError, ValueError):
        distance_m = 0

    return {
        "id": f"kakao_{doc.get('id', f'{lat},{lng}')}",
        "name": name,
        "address": (doc.get("road_address_name") or doc.get("address_name") or "").strip(),
        "type": "공영" if is_public else category,
        "lat": lat,
        "lng": lng,
        "phone": (doc.get("phone") or "").strip(),
        "distance_m": distance_m,
        "category_name": category,
        "base_fee": None,
        "unit_fee": None,
        "base_time_minutes": 30,
        "unit_time_minutes": 10,
        "capacity": None,
        "source": "kakao",
    }


def search_parking_near(
    lat: float,
    lng: float,
    *,
    radius_m: int,
    max_distance_m: int | None = None,
    max_results: int | None = None,
) -> list[dict[str, Any]]:
    """
    카카오 Local API — category_group_code=PK6 (주차장).
    x=경도, y=위도, radius=미터.
    """
    if radius_m <= 0:
        return []

    result_cap = max_results if max_results is not None else KAKAO_PARKING_MAX_RESULTS
    seen: set[str] = set()
    results: list[dict[str, Any]] = []
    max_pages = max(1, (result_cap + KAKAO_PARKING_PAGE_SIZE - 1) // KAKAO_PARKING_PAGE_SIZE)

    for page in range(1, max_pages + 1):
        try:
            resp = requests.get(
                KAKAO_CATEGORY_SEARCH_URL,
                headers=_headers(),
                params={
                    "category_group_code": KAKAO_PARKING_CATEGORY_CODE,
                    "x": lng,
                    "y": lat,
                    "radius": radius_m,
                    "size": KAKAO_PARKING_PAGE_SIZE,
                    "page": page,
                    "sort": "distance",
                },
                timeout=12,
            )
        except requests.RequestException as exc:
            raise KakaoApiError(f"카카오 API 요청 실패: {exc}") from exc

        if resp.status_code == 401:
            raise KakaoApiError("카카오 API 인증 실패 (REST API 키 확인)")
        if resp.status_code != 200:
            raise KakaoApiError(f"카카오 API HTTP {resp.status_code}: {resp.text[:120]}")

        payload = resp.json()
        meta = payload.get("meta", {})
        documents = payload.get("documents", [])
        if not documents:
            break

        for doc in documents:
            parsed = _normalize_document(doc)
            if not parsed or parsed["id"] in seen:
                continue
            if max_distance_m is not None and parsed["distance_m"] > max_distance_m:
                continue
            seen.add(parsed["id"])
            results.append(parsed)

        if meta.get("is_end", True):
            break
        if len(results) >= result_cap:
            break

    results.sort(key=lambda p: p.get("distance_m", 0))
    return results[:result_cap]
