from __future__ import annotations

from typing import Any

from api.openai_api import generate_chat_completion
from utils.env_loader import get_env
from utils.optimization_mode import MODE_MINIMIZE_PARKING, mode_label, normalize_optimization_mode


def generate_explanation(route: dict[str, Any]) -> str:
    try:
        return _generate_openai(route)
    except Exception:
        return _generate_template(route)


def _generate_template(route: dict[str, Any]) -> str:
    summary = route.get("summary", {})
    parkings = route.get("parkings", [])
    mode = normalize_optimization_mode(route.get("optimization_mode"))

    if mode == MODE_MINIMIZE_PARKING:
        intro = (
            "주차 횟수를 줄이기 위해 주차장을 거점으로 두고 "
            "여러 장소를 도보로 방문하는 동선을 구성했습니다."
        )
    else:
        intro = "도보 이동시간을 줄이고 차량·주차 중심으로 방문 순서를 재구성했습니다."

    lines = [
        intro,
        f"총 이동 시간은 약 {summary.get('total_time_sec', 0) // 60}분 "
        f"(차량 {summary.get('car_time_sec', 0) // 60}분, "
        f"도보 {summary.get('walk_time_sec', 0) // 60}분)입니다.",
    ]
    if parkings:
        names = ", ".join(p["name"] for p in parkings[:3])
        lines.append(f"근처 주차장({names})을 기준으로 동선을 묶었습니다.")
    parking_cost = summary.get("parking_cost_won")
    if parking_cost:
        lines.append(f"예상 주차비는 약 {parking_cost:,}원입니다.")
    for warning in route.get("warnings") or []:
        lines.append(warning)
    return " ".join(lines)


def _generate_openai(route: dict[str, Any]) -> str:
    key = get_env("OPENAI_API_KEY")
    if not key or key.lower().startswith("your"):
        return _generate_template(route)

    summary = route.get("summary", {})
    mode = mode_label(route.get("optimization_mode"))
    stop_lines = []
    for s in route.get("stops", []):
        stop_lines.append(f"- {s.get('label', '?')}: {s.get('name', '')}")

    prompt = (
        f"다음 여행 경로를 3~4문장으로 친절하게 설명해줘. "
        f"최적화 모드는 「{mode}」이며, 이 모드의 의도를 반영해.\n\n"
        f"방문 순서:\n" + "\n".join(stop_lines) + "\n\n"
        f"차량 {summary.get('car_time_sec', 0) // 60}분, "
        f"도보 {summary.get('walk_time_sec', 0) // 60}분, "
        f"주차 {summary.get('parking_count', 0)}회"
    )
    if summary.get("parking_cost_won"):
        prompt += f", 예상 주차비 {summary['parking_cost_won']:,}원"

    return generate_chat_completion(
        prompt,
        "You are a Korean travel route assistant for ParkRoute AI.",
    )
