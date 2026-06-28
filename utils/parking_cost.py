from __future__ import annotations

import re
from typing import Any


def parse_fee(value: Any) -> int | None:
    if value in (None, "", " "):
        return None
    if isinstance(value, (int, float)):
        return int(value)
    digits = re.sub(r"[^\d]", "", str(value).strip())
    return int(digits) if digits else None


def parse_minutes(value: Any, default: int) -> int:
    parsed = parse_fee(value)
    return parsed if parsed is not None and parsed > 0 else default


def calculate_parking_cost(parking: dict[str, Any], stay_minutes: int) -> dict[str, Any]:
    """Rules.md: parking_cost = base_fee + (time_over * unit_fee)."""
    base_fee = parse_fee(parking.get("base_fee")) or 0
    unit_fee = parse_fee(parking.get("unit_fee")) or 0
    base_time = parse_minutes(parking.get("base_time_minutes"), 30)
    unit_time = parse_minutes(parking.get("unit_time_minutes"), 10)

    over_minutes = max(0, stay_minutes - base_time)
    extra_units = (over_minutes + unit_time - 1) // unit_time if unit_time > 0 else 0
    estimated = base_fee + extra_units * unit_fee

    return {
        "base_fee": base_fee,
        "unit_fee": unit_fee,
        "base_time_minutes": base_time,
        "unit_time_minutes": unit_time,
        "stay_minutes": stay_minutes,
        "extra_units": extra_units,
        "estimated_cost": estimated,
    }


def format_won(amount: int | None) -> str:
    if amount is None:
        return "-"
    return f"{amount:,}원"
