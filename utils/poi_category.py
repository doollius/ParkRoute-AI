from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_MAPPING_PATH = Path(__file__).resolve().parent.parent / "data" / "poi_category_mapping.json"


def normalize_biz_name(value: str | None) -> str:
    if not value:
        return ""
    return str(value).replace("\\/", "/").strip()


@lru_cache(maxsize=1)
def _load_mapping() -> dict[str, Any]:
    with open(_MAPPING_PATH, encoding="utf-8") as f:
        return json.load(f)


def default_parking_minutes() -> int:
    return int(_load_mapping().get("default_minutes", 5))


def middle_biz_minutes() -> dict[str, int]:
    return {normalize_biz_name(k): int(v) for k, v in _load_mapping().get("middle_biz_minutes", {}).items()}


def lower_biz_overrides() -> dict[str, int]:
    return {normalize_biz_name(k): int(v) for k, v in _load_mapping().get("lower_biz_overrides", {}).items()}


def congestion_extra_minutes(level: str) -> int:
    table = _load_mapping().get("congestion_extra_minutes", {})
    return int(table.get(level, table.get("normal", 3)))


def _match_from_haystack(haystack: str, table: dict[str, int]) -> int | None:
    if not haystack:
        return None
    for name in sorted(table, key=len, reverse=True):
        if name and name in haystack:
            return table[name]
    return None


def resolve_parking_base_minutes(
    *,
    lower_biz_name: str | None = None,
    middle_biz_name: str | None = None,
    poi_category: str | None = None,
) -> int:
    """
    Parking Event Base Time (분).
    1. lowerBizName override
    2. middleBizName base
    3. poi_category 문자열에서 lower → middle 순 부분 일치
    4. default
    """
    lower = normalize_biz_name(lower_biz_name)
    middle = normalize_biz_name(middle_biz_name)
    lowers = lower_biz_overrides()
    middles = middle_biz_minutes()

    if lower and lower in lowers:
        return lowers[lower]

    if middle and middle in middles:
        return middles[middle]

    haystack = normalize_biz_name(poi_category)
    if haystack:
        matched = _match_from_haystack(haystack, lowers)
        if matched is not None:
            return matched
        matched = _match_from_haystack(haystack, middles)
        if matched is not None:
            return matched

    return default_parking_minutes()


def parking_event_minutes(
    node: dict[str, Any],
    congestion_level: str = "normal",
) -> int:
    base = resolve_parking_base_minutes(
        lower_biz_name=node.get("lower_biz_name"),
        middle_biz_name=node.get("middle_biz_name"),
        poi_category=node.get("poi_category"),
    )
    return base + congestion_extra_minutes(congestion_level)
