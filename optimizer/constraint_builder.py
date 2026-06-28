from __future__ import annotations

from typing import Any

from models.visit_rule import RULE_BEFORE, RULE_IMMEDIATE


def validate_visit_rules(
    rules: list[dict[str, Any]],
    place_ids: set[str],
    start_id: str | None,
    end_id: str | None,
) -> list[str]:
    errors: list[str] = []
    for i, rule in enumerate(rules):
        prefix = f"규칙 {i + 1}"
        from_id = rule.get("from_id")
        to_id = rule.get("to_id")
        rtype = rule.get("rule_type")

        if from_id not in place_ids or to_id not in place_ids:
            errors.append(f"{prefix}: 존재하지 않는 장소가 포함되어 있습니다.")
            continue
        if from_id == to_id:
            errors.append(f"{prefix}: 같은 장소끼리 규칙을 설정할 수 없습니다.")
            continue
        if rtype not in (RULE_IMMEDIATE, RULE_BEFORE):
            errors.append(f"{prefix}: 알 수 없는 규칙 유형입니다.")
            continue
        if end_id and from_id == end_id:
            errors.append(f"{prefix}: 도착지 뒤에는 장소를 배치할 수 없습니다.")
        if start_id and to_id == start_id and rtype == RULE_IMMEDIATE:
            errors.append(f"{prefix}: 출발지 바로 앞 규칙은 설정할 수 없습니다.")

    immediate_next: dict[str, str] = {}
    for rule in rules:
        if rule.get("rule_type") != RULE_IMMEDIATE:
            continue
        f, t = rule["from_id"], rule["to_id"]
        if f in immediate_next and immediate_next[f] != t:
            errors.append("바로 다음 규칙 충돌: 한 장소에서 두 개의 바로 다음을 지정할 수 없습니다.")
        immediate_next[f] = t

    return errors


def map_rules_to_indices(
    rules: list[dict[str, Any]],
    id_to_index: dict[str, int],
) -> list[dict[str, Any]]:
    mapped: list[dict[str, Any]] = []
    for rule in rules:
        from_id = rule.get("from_id")
        to_id = rule.get("to_id")
        if from_id not in id_to_index or to_id not in id_to_index:
            continue
        mapped.append(
            {
                "from_index": id_to_index[from_id],
                "to_index": id_to_index[to_id],
                "rule_type": rule["rule_type"],
            }
        )
    return mapped
