from __future__ import annotations

import re

URL_PATTERN = re.compile(r"https?://|www\.|naver\.me|map\.naver", re.IGNORECASE)
ADMIN_PATTERN = re.compile(
    r"(특별자치)?[가-힣]+(특별시|광역시|특별자치시|특별자치도|도|[가-힣]+시|[가-힣]+군|[가-힣]+구)"
)


def validate_address(text: str) -> tuple[bool, str]:
    """도로명/지번 주소만 허용. URL·네이버 링크 거부."""
    value = text.strip()
    if len(value) < 5:
        return False, "주소는 5글자 이상 입력하세요."
    if URL_PATTERN.search(value):
        return False, "URL은 지원하지 않습니다. 도로명 또는 지번 주소를 입력하세요."
    if not ADMIN_PATTERN.search(value):
        return False, "시·도 또는 시·군·구가 포함된 한국 주소를 입력하세요."
    return True, ""


def validate_place_name(value: str | None) -> tuple[bool, str]:
    name = (value or "").strip()
    if len(name) < 1:
        return False, "장소명을 입력하세요."
    if len(name) > 50:
        return False, "장소명은 50자 이하로 입력하세요."
    return True, ""


def validate_reservation_time(value: str | None) -> tuple[bool, str]:
    if not value:
        return True, ""
    if not re.fullmatch(r"\d{2}:\d{2}", value.strip()):
        return False, "예약 시간은 HH:MM 형식이어야 합니다."
    hour, minute = value.strip().split(":")
    if int(hour) > 23 or int(minute) > 59:
        return False, "올바른 시간을 입력하세요."
    return True, ""
