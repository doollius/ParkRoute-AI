"""Diagnostic: Kakao PK6 parking candidates near a reference place / trip."""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv

load_dotenv(ROOT / ".env")

from api.tmap_api import search_pois
from constants.config import KAKAO_PARKING_SEARCH_RADIUS_M, PARKING_NEARBY_RADIUS_M
from services.parking_service import fetch_kakao_parking, trip_centroid
from utils.geo import haversine_m

QUERY = sys.argv[1] if len(sys.argv) > 1 else "부산진구청"


def main() -> None:
    pois = search_pois(QUERY, count=3)
    if not pois:
        print(f"POI not found: {QUERY}")
        sys.exit(1)

    p = pois[0]
    lat, lng = p["lat"], p["lng"]
    print("=== Reference POI (TMAP) ===")
    print(f"name: {p.get('name')}")
    print(f"address: {p.get('normalized_address')}")
    print(f"lat/lng: {lat}, {lng}")
    print()

    print(f"=== Kakao PK6 (center POI, radius={KAKAO_PARKING_SEARCH_RADIUS_M}m) ===")
    raw = fetch_kakao_parking(lat, lng)
    print(f"  total from Kakao: {len(raw)}")
    nearby = [
        x
        for x in raw
        if haversine_m(x["lat"], x["lng"], lat, lng) <= PARKING_NEARBY_RADIUS_M
    ]
    nearby.sort(key=lambda x: haversine_m(x["lat"], x["lng"], lat, lng))
    print(f"  within {PARKING_NEARBY_RADIUS_M}m (haversine): {len(nearby)}")
    for i, pk in enumerate(nearby[:20], 1):
        d = int(haversine_m(pk["lat"], pk["lng"], lat, lng))
        kakao_d = pk.get("distance_m", "?")
        addr = (pk.get("address") or "")[:55]
        print(f"  {i:2d}. {d:4d}m (kakao {kakao_d}m) | {pk['name']} | {addr}")
    print()

    extra = ["트레이더스 부산", "서면종합시장"]
    places = [{"lat": lat, "lng": lng, "name": p.get("name"), "id": "p0"}]
    for i, q in enumerate(extra, 1):
        r = search_pois(q, count=1)
        if r:
            places.append(
                {
                    "lat": r[0]["lat"],
                    "lng": r[0]["lng"],
                    "name": r[0].get("name"),
                    "id": f"p{i}",
                }
            )

    center = trip_centroid(places)
    assert center is not None
    clat, clng = center
    print("=== Trip centroid search (app logic) ===")
    for pl in places:
        print(f"  - {pl['name']}: {pl['lat']}, {pl['lng']}")
    print(f"  centroid: {clat:.5f}, {clng:.5f}")

    # Bypass streamlit cache — call fetch directly with centroid
    app_candidates = fetch_kakao_parking(clat, clng)
    print(f"  Kakao candidates at centroid: {len(app_candidates)}")

    within_any = [
        x
        for x in app_candidates
        if any(
            haversine_m(x["lat"], x["lng"], pl["lat"], pl["lng"]) <= PARKING_NEARBY_RADIUS_M
            for pl in places
        )
    ]
    within_any.sort(
        key=lambda x: min(
            haversine_m(x["lat"], x["lng"], pl["lat"], pl["lng"]) for pl in places
        )
    )
    print(f"  within {PARKING_NEARBY_RADIUS_M}m of ANY place: {len(within_any)}")
    for i, pk in enumerate(within_any[:25], 1):
        dists = [
            int(haversine_m(pk["lat"], pk["lng"], pl["lat"], pl["lng"])) for pl in places
        ]
        min_d = min(dists)
        addr = (pk.get("address") or "")[:50]
        pub = "공영" if pk.get("type") == "공영" else "    "
        print(f"  {i:2d}. min {min_d:4d}m | {pub} | {pk['name']} | {addr}")


if __name__ == "__main__":
    main()
