"""
Local API key verification script.

Usage (from project root):
    pip install -r requirements.txt
    copy .env.example .env   # then fill keys
    python scripts/test_api_keys.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

TMAP_APP_KEY = os.getenv("TMAP_APP_KEY", "").strip()
KAKAO_REST_API_KEY = os.getenv("KAKAO_REST_API_KEY", "").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()

# Sample address for geocoding (Busan)
SAMPLE_ADDRESS = "부산광역시 부산진구 중앙대로 749"
# Known coordinates near sample address for route test
START = (129.059, 35.158)
END = (129.065, 35.162)


def ok(label: str, detail: str = "") -> None:
    suffix = f" — {detail}" if detail else ""
    print(f"  [OK] {label}{suffix}")


def fail(label: str, detail: str = "") -> None:
    suffix = f" — {detail}" if detail else ""
    print(f"  [FAIL] {label}{suffix}")


def check_env() -> bool:
    print("\n=== 1. Environment variables ===")
    all_ok = True
    for name, value in [
        ("TMAP_APP_KEY", TMAP_APP_KEY),
        ("KAKAO_REST_API_KEY", KAKAO_REST_API_KEY),
        ("OPENAI_API_KEY", OPENAI_API_KEY),
    ]:
        if value:
            masked = value[:4] + "..." + value[-4:] if len(value) > 12 else "(set)"
            ok(name, masked)
        else:
            fail(name, "missing in .env")
            all_ok = False
    return all_ok


def test_tmap_geocoding() -> bool:
    print("\n=== 2. TMAP Geocoding ===")
    url = "https://apis.openapi.sk.com/tmap/geo/fullAddrGeo"
    params = {
        "version": "1",
        "format": "json",
        "fullAddr": SAMPLE_ADDRESS,
        "coordType": "WGS84GEO",
    }
    headers = {"appKey": TMAP_APP_KEY, "Accept": "application/json"}
    try:
        resp = requests.get(url, params=params, headers=headers, timeout=15)
        data = resp.json()
        if resp.status_code != 200:
            fail("Geocoding", f"HTTP {resp.status_code}: {data}")
            return False
        coords = data.get("coordinateInfo", {}).get("coordinate", [])
        if not coords:
            fail("Geocoding", f"no coordinates: {json.dumps(data, ensure_ascii=False)[:200]}")
            return False
        c0 = coords[0]
        lat = c0.get("newLat") or c0.get("lat")
        lon = c0.get("newLon") or c0.get("lon")
        ok("Geocoding", f"{SAMPLE_ADDRESS} → lat={lat}, lon={lon}")
        return True
    except Exception as exc:
        fail("Geocoding", str(exc))
        return False


def test_tmap_car_route() -> bool:
    print("\n=== 3. TMAP Car route ===")
    url = "https://apis.openapi.sk.com/tmap/routes"
    params = {"version": "1", "format": "json"}
    headers = {
        "appKey": TMAP_APP_KEY,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    body = {
        "startX": START[0],
        "startY": START[1],
        "endX": END[0],
        "endY": END[1],
        "reqCoordType": "WGS84GEO",
        "resCoordType": "WGS84GEO",
        "searchOption": "0",
    }
    try:
        resp = requests.post(url, params=params, headers=headers, json=body, timeout=15)
        data = resp.json()
        if resp.status_code != 200:
            fail("Car route", f"HTTP {resp.status_code}: {str(data)[:200]}")
            return False
        features = data.get("features", [])
        props = next(
            (f.get("properties", {}) for f in features if f.get("properties", {}).get("totalTime")),
            {},
        )
        total_time = props.get("totalTime")
        if total_time is None:
            fail("Car route", "totalTime not found in response")
            return False
        ok("Car route", f"totalTime={total_time} sec (~{int(total_time) // 60} min)")
        return True
    except Exception as exc:
        fail("Car route", str(exc))
        return False


def test_tmap_walk_route() -> bool:
    print("\n=== 4. TMAP Pedestrian route ===")
    url = "https://apis.openapi.sk.com/tmap/routes/pedestrian"
    params = {"version": "1", "format": "json"}
    headers = {
        "appKey": TMAP_APP_KEY,
        "Accept": "application/json",
        "Content-Type": "application/json",
    }
    body = {
        "startX": START[0],
        "startY": START[1],
        "endX": END[0],
        "endY": END[1],
        "reqCoordType": "WGS84GEO",
        "resCoordType": "WGS84GEO",
        "searchOption": "0",
        "startName": "start",
        "endName": "end",
    }
    try:
        resp = requests.post(url, params=params, headers=headers, json=body, timeout=15)
        data = resp.json()
        if resp.status_code != 200:
            fail("Pedestrian route", f"HTTP {resp.status_code}: {str(data)[:200]}")
            return False
        features = data.get("features", [])
        props = next(
            (f.get("properties", {}) for f in features if f.get("properties", {}).get("totalTime")),
            {},
        )
        total_time = props.get("totalTime")
        if total_time is None:
            fail("Pedestrian route", "totalTime not found")
            return False
        ok("Pedestrian route", f"totalTime={total_time} sec (~{int(total_time) // 60} min)")
        return True
    except Exception as exc:
        fail("Pedestrian route", str(exc))
        return False


def test_kakao_parking() -> bool:
    print("\n=== 5. Kakao Local API (PK6 주차장) ===")
    url = "https://dapi.kakao.com/v2/local/search/category.json"
    headers = {"Authorization": f"KakaoAK {KAKAO_REST_API_KEY}"}
    params = {
        "category_group_code": "PK6",
        "x": 129.0532,
        "y": 35.1629,
        "radius": 1000,
        "size": 5,
    }
    try:
        resp = requests.get(url, headers=headers, params=params, timeout=15)
        if resp.status_code == 401:
            fail("Kakao parking", "HTTP 401 — REST API 키 확인")
            return False
        if resp.status_code != 200:
            fail("Kakao parking", f"HTTP {resp.status_code}: {resp.text[:120]}")
            return False
        docs = resp.json().get("documents", [])
        if not docs:
            fail("Kakao parking", "documents empty (키는 유효할 수 있음)")
            return False
        name = docs[0].get("place_name", "?")
        ok("Kakao parking", f"{len(docs)}건, sample={name}")
        return True
    except Exception as exc:
        fail("Kakao parking", str(exc))
        return False


def test_openai() -> bool:
    print("\n=== 6. OpenAI API ===")
    try:
        from openai import OpenAI

        client = OpenAI(api_key=OPENAI_API_KEY)
        resp = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{"role": "user", "content": "Reply with exactly: OK"}],
            max_tokens=5,
        )
        text = (resp.choices[0].message.content or "").strip()
        ok("OpenAI chat", f"model={OPENAI_MODEL}, reply={text!r}")
        return True
    except Exception as exc:
        fail("OpenAI", str(exc))
        return False


def main() -> int:
    print("ParkRoute AI - API key verification")
    print(f"Project root: {PROJECT_ROOT}")

    if not check_env():
        print("\nCreate .env from .env.example and add your keys, then re-run.")
        return 1

    results = [
        test_tmap_geocoding(),
        test_tmap_car_route(),
        test_tmap_walk_route(),
        test_kakao_parking(),
        test_openai(),
    ]

    passed = sum(results)
    total = len(results)
    print(f"\n=== Summary: {passed}/{total} API tests passed ===")
    if passed == total:
        print("All keys work locally. Streamlit Secrets can be added after first deploy.")
        return 0
    print("Fix failed items above (product subscription, key encoding, billing, etc.).")
    return 1


if __name__ == "__main__":
    sys.exit(main())
