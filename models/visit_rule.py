from __future__ import annotations

import uuid
from typing import Any

RULE_IMMEDIATE = "immediate"  # 바로 다음: B = A + 1
RULE_BEFORE = "before"  # 다음: A before B


def create_visit_rule(from_id: str, to_id: str, rule_type: str) -> dict[str, Any]:
    return {
        "id": uuid.uuid4().hex[:8],
        "from_id": from_id,
        "to_id": to_id,
        "rule_type": rule_type,
    }


def rule_label(rule: dict[str, Any], place_labels: dict[str, str]) -> str:
    type_label = "바로 다음" if rule["rule_type"] == RULE_IMMEDIATE else "다음"
    from_name = place_labels.get(rule["from_id"], "?")
    to_name = place_labels.get(rule["to_id"], "?")
    return f"{from_name} → {to_name} ({type_label})"
