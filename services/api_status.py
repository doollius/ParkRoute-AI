from __future__ import annotations

import requests

from utils.env_loader import get_env

SAMPLE_ADDRESS = "부산광역시 부산진구 중앙대로 749"


def keys_configured() -> dict[str, bool]:
    return {
        "TMAP": bool(get_env("TMAP_APP_KEY")),
        "DATA_GO_KR": bool(get_env("DATA_GO_KR_SERVICE_KEY")),
        "OPENAI": bool(get_env("OPENAI_API_KEY")),
    }


def test_tmap() -> tuple[bool, str]:
    key = get_env("TMAP_APP_KEY")
    if not key:
        return False, "TMAP_APP_KEY 없음"
    try:
        resp = requests.get(
            "https://apis.openapi.sk.com/tmap/geo/fullAddrGeo",
            params={
                "version": "1",
                "format": "json",
                "fullAddr": SAMPLE_ADDRESS,
                "coordType": "WGS84GEO",
            },
            headers={"appKey": key, "Accept": "application/json"},
            timeout=12,
        )
        if resp.status_code != 200:
            return False, f"HTTP {resp.status_code}"
        coords = resp.json().get("coordinateInfo", {}).get("coordinate", [])
        if not coords:
            return False, "좌표 없음"
        lat = coords[0].get("newLat") or coords[0].get("lat")
        return True, f"Geocoding OK (lat={lat})"
    except Exception as exc:
        return False, str(exc)


def test_parking() -> tuple[bool, str]:
    key = get_env("DATA_GO_KR_SERVICE_KEY")
    if not key:
        return False, "DATA_GO_KR_SERVICE_KEY 없음"
    try:
        resp = requests.get(
            "https://api.data.go.kr/openapi/tn_pubr_prkplce_info_api",
            params={
                "serviceKey": key,
                "pageNo": 1,
                "numOfRows": 1,
                "type": "json",
                "prkplceSe": "공영",
            },
            timeout=15,
        )
        data = resp.json()
        code = data.get("response", {}).get("header", {}).get("resultCode")
        if code != "00":
            msg = data.get("response", {}).get("header", {}).get("resultMsg", "")
            return False, f"{code} {msg}"
        return True, "주차장 API OK"
    except Exception as exc:
        return False, str(exc)


def test_openai() -> tuple[bool, str]:
    key = get_env("OPENAI_API_KEY")
    if not key:
        return False, "OPENAI_API_KEY 없음"
    try:
        from openai import OpenAI

        model = get_env("OPENAI_MODEL", "gpt-4o-mini")
        client = OpenAI(api_key=key)
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Reply with exactly: OK"}],
            max_tokens=5,
        )
        text = (resp.choices[0].message.content or "").strip()
        return True, f"OpenAI OK ({text!r})"
    except Exception as exc:
        return False, str(exc)
