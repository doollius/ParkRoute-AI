from __future__ import annotations

import re

import requests

from api.kakao_api import KakaoApiError, search_parking_near
from utils.env_loader import get_env

SAMPLE_ADDRESS = "부산광역시 부산진구 중앙대로 749"
# 부산진구청 근처 좌표 (Kakao PK6 테스트)
SAMPLE_LAT = 35.1629
SAMPLE_LNG = 129.0532

_PLACEHOLDER_VALUES = frozenset(
    {
        "",
        "your_key",
        "your_tmap_key",
        "your_openai_key",
        "your_kakao_key",
        "발급받은_키",
        "sk-...",
    }
)


def _mask_key(value: str) -> str:
    if len(value) <= 8:
        return "(too short)"
    return f"{value[:4]}...{value[-4:]}"


def key_detail(env_name: str) -> dict[str, str | bool]:
    value = get_env(env_name)
    lowered = value.lower().strip()
    is_placeholder = lowered in _PLACEHOLDER_VALUES or lowered.startswith("your_")
    looks_ok = bool(value) and not is_placeholder
    return {
        "configured": bool(value),
        "looks_ok": looks_ok,
        "masked": _mask_key(value) if value else "(empty)",
        "is_placeholder": is_placeholder,
    }


def keys_configured() -> dict[str, bool]:
    return {
        "TMAP": key_detail("TMAP_APP_KEY")["looks_ok"],
        "KAKAO": key_detail("KAKAO_REST_API_KEY")["looks_ok"],
        "OPENAI": key_detail("OPENAI_API_KEY")["looks_ok"],
    }


def keys_validation_message() -> str | None:
    issues: list[str] = []
    mapping = {
        "TMAP_APP_KEY": "TMAP",
        "KAKAO_REST_API_KEY": "KAKAO",
        "OPENAI_API_KEY": "OPENAI",
    }
    for env_name, label in mapping.items():
        detail = key_detail(env_name)
        if not detail["configured"]:
            issues.append(f"{label}: 값 없음")
        elif detail["is_placeholder"]:
            issues.append(f"{label}: 예시 텍스트(your_key 등)가 그대로 들어있음")
    if not issues:
        return None
    return " / ".join(issues)


def test_tmap() -> tuple[bool, str]:
    detail = key_detail("TMAP_APP_KEY")
    if not detail["configured"]:
        return False, "TMAP_APP_KEY 없음"
    if detail["is_placeholder"]:
        return False, "예시 키(your_key)가 입력됨 — .env의 실제 appKey로 교체"
    key = get_env("TMAP_APP_KEY")
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
            hint = resp.text[:120] if resp.text else ""
            return False, f"HTTP {resp.status_code} (키={detail['masked']}) {hint}"
        coords = resp.json().get("coordinateInfo", {}).get("coordinate", [])
        if not coords:
            return False, "좌표 없음"
        lat = coords[0].get("newLat") or coords[0].get("lat")
        return True, f"Geocoding OK (lat={lat})"
    except Exception as exc:
        return False, str(exc)


def test_parking() -> tuple[bool, str]:
    detail = key_detail("KAKAO_REST_API_KEY")
    if not detail["configured"]:
        return (
            False,
            "KAKAO_REST_API_KEY 없음 — 로컬: .env / Cloud: Streamlit Secrets에 추가",
        )
    if detail["is_placeholder"]:
        return False, "예시 키가 입력됨 — .env의 실제 REST API 키로 교체"
    try:
        results = search_parking_near(SAMPLE_LAT, SAMPLE_LNG, radius_m=1000)
        if not results:
            return False, "주차장 0건 (키는 유효할 수 있음 — 반경·좌표 확인)"
        sample = results[0]
        return True, f"카카오 Local API OK — PK6 {len(results)}건 (예: {sample['name'][:20]})"
    except KakaoApiError as exc:
        return False, f"{exc} (키={detail['masked']})"
    except Exception as exc:
        return False, str(exc)


def test_openai() -> tuple[bool, str]:
    detail = key_detail("OPENAI_API_KEY")
    if not detail["configured"]:
        return False, "OPENAI_API_KEY 없음"
    if detail["is_placeholder"]:
        return False, "예시 키(your_key)가 입력됨 — .env의 sk-proj-... 키로 교체"
    key = get_env("OPENAI_API_KEY")
    if not re.match(r"^sk-", key):
        return False, f"형식 오류 — sk- 로 시작해야 함 (키={detail['masked']})"
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
        return False, f"{exc} (키={detail['masked']})"
