from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any

_MAPPING_PATH = Path(__file__).resolve().parent.parent / "data" / "poi_category_mapping.json"


@lru_cache(maxsize=1)
def _load_mapping() -> dict[str, Any]:
    with open(_MAPPING_PATH, encoding="utf-8") as f:
        return json.load(f)


def service_category_defaults() -> dict[str, int]:
    return dict(_load_mapping().get("service_defaults", {}))


def congestion_extra_minutes(level: str) -> int:
    table = _load_mapping().get("congestion_extra_minutes", {})
    return int(table.get(level, table.get("normal", 3)))


def resolve_service_category(
    tmap_category: str | None = None,
    place_name: str | None = None,
    explicit: str | None = None,
) -> str:
    if explicit and explicit in service_category_defaults():
        return explicit

    haystack = " ".join(
        p for p in [tmap_category or "", place_name or ""] if p
    ).lower()

    for row in _load_mapping().get("tmap_keywords", []):
        for kw in row.get("keywords", []):
            if kw.lower() in haystack:
                return row["category"]
    return "기타"


def base_parking_event_minutes(service_category: str) -> int:
    return int(service_category_defaults().get(service_category, 5))
